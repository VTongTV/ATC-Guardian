"""Band REST API poller service.

Periodically polls the Band REST API for room messages and stores
new messages in the audit service. Runs as a background task.
Gracefully skips polling when Band credentials are not configured.
"""

import asyncio
import json
import logging
import re
from typing import Any

import httpx
from pydantic import BaseModel, Field

from shared.constants import BAND_POLL_INTERVAL_SECONDS, BAND_MESSAGE_PAGE_SIZE

from backend.app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Band REST API constants
# ---------------------------------------------------------------------------

BAND_BASE_URL = "https://app.band.ai"
BAND_MESSAGES_ENDPOINT = "/agent/chats/{chat_id}/messages"
BAND_REQUEST_TIMEOUT_SECONDS = 10
BAND_RETRY_ATTEMPTS = 2


class BandAPIError(Exception):
    """Raised when the Band API returns an error or is unreachable."""


class BandMessage(BaseModel):
    """Pydantic model for a Band room message.

    Represents a single message or event fetched from the Band REST API.
    The polling service stores these in the audit log for agent
    coordination history.
    """

    message_id: str = Field(description="Unique message identifier from Band")
    timestamp: str = Field(description="ISO 8601 timestamp of the message")
    sender: str = Field(description="Agent name or 'user' for human messages")
    message_type: str = Field(
        description="Message type: text, thought, task, tool_call, tool_result, error"
    )
    content: str = Field(description="Message text content")
    metadata_json: str | None = Field(
        default=None, description="Optional JSON metadata from the Band message"
    )
    mentions: list[str] = Field(
        default_factory=list, description="@mentioned agent names in this message"
    )


class BandPoller:
    """Periodically polls the Band REST API for room messages.

    Polls ``GET /agent/chats/{chat_id}/messages`` every
    ``BAND_POLL_INTERVAL_SECONDS`` and stores new messages in the
    audit service. Runs as a background asyncio task.

    If Band credentials are not configured, polling is skipped gracefully
    with a warning log on startup.

    Attributes:
        is_configured: Whether Band credentials are available for polling.
    """

    def __init__(
        self,
        api_key: str | None = None,
        chat_id: str | None = None,
        base_url: str = BAND_BASE_URL,
        audit_service: AuditService | None = None,
    ) -> None:
        """Initialize with optional Band credentials.

        Args:
            api_key: Band API bearer token. If None, polling is disabled.
            chat_id: Band room/chat ID to poll messages from. If None, polling
                is disabled.
            base_url: Band API base URL. Defaults to the production endpoint.
            audit_service: Optional audit service instance for storing messages.
                If None, messages are only logged.
        """
        self._api_key = api_key
        self._chat_id = chat_id
        self._base_url = base_url.rstrip("/")
        self._audit_service = audit_service
        self._client: httpx.AsyncClient | None = None
        self._poll_task: asyncio.Task | None = None
        self._last_message_id: str | None = None

    @property
    def is_configured(self) -> bool:
        """Whether Band credentials are available for polling.

        Returns:
            True if both api_key and chat_id are non-empty strings.
        """
        return bool(self._api_key and self._chat_id)

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create the shared httpx.AsyncClient.

        Returns:
            A configured httpx.AsyncClient with bearer token auth.

        Raises:
            BandAPIError: If credentials are not configured.
        """
        if self._client is None or self._client.is_closed:
            if not self.is_configured:
                raise BandAPIError(
                    "Band credentials not configured. "
                    "Set BAND_API_KEY and BAND_ROOM_ID."
                )
            self._client = httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=BAND_REQUEST_TIMEOUT_SECONDS,
            )
        return self._client

    def _parse_message(self, raw: dict) -> BandMessage:
        """Convert a raw Band API message dict to a BandMessage model.

        Args:
            raw: A single message object from the Band API response.

        Returns:
            A BandMessage instance parsed from the raw dict.
        """
        content = raw.get("content", "")
        message_type = raw.get("type", "text")
        role = raw.get("role", "unknown")
        status = raw.get("status", "")
        metadata = raw.get("metadata")
        created_at = raw.get("created_at", "")
        message_id = raw.get("id", "")

        # Extract @mentions from content
        mentions: list[str] = []
        if content:
            mention_pattern = re.compile(r"@(\w+)")
            mentions = mention_pattern.findall(content)

        # Build metadata JSON string if metadata dict is present
        metadata_json: str | None = None
        if metadata:
            metadata_json = json.dumps(metadata)

        # Determine sender from role
        sender = role if role != "system" else "system"

        return BandMessage(
            message_id=str(message_id),
            timestamp=str(created_at),
            sender=sender,
            message_type=str(message_type),
            content=str(content),
            metadata_json=metadata_json,
            mentions=mentions,
        )

    async def fetch_messages(self) -> list[BandMessage]:
        """Fetch messages from Band REST API.

        Sends a GET request to ``/agent/chats/{chat_id}/messages`` and
        parses the response into BandMessage models.

        Returns:
            List of BandMessage parsed from the API response.

        Raises:
            BandAPIError: If the API call fails or credentials are invalid.
        """
        if not self.is_configured:
            raise BandAPIError(
                "Band credentials not configured. "
                "Set BAND_API_KEY and BAND_ROOM_ID."
            )

        client = self._get_client()
        endpoint = BAND_MESSAGES_ENDPOINT.format(chat_id=self._chat_id)
        url = f"{self._base_url}{endpoint}"

        params = {
            "status": "all",
            "limit": BAND_MESSAGE_PAGE_SIZE,
        }

        last_error: Exception | None = None

        for attempt in range(BAND_RETRY_ATTEMPTS):
            try:
                response = await client.get(url, params=params)

                if response.status_code == 401:
                    raise BandAPIError(
                        "Band authentication failed. Check BAND_API_KEY."
                    )
                if response.status_code == 404:
                    raise BandAPIError(
                        f"Band chat not found: {self._chat_id}. "
                        "Check BAND_ROOM_ID."
                    )
                if response.status_code == 429:
                    raise BandAPIError(
                        "Band rate limit exceeded (429). "
                        "Wait before retrying."
                    )
                if response.status_code != 200:
                    raise BandAPIError(
                        f"Band API returned HTTP {response.status_code}: "
                        f"{response.text[:200]}"
                    )

                data = response.json()
                raw_messages = data.get("messages") or data.get("data") or []

                messages = []
                for raw_msg in raw_messages:
                    try:
                        parsed = self._parse_message(raw_msg)
                        messages.append(parsed)
                    except Exception:
                        logger.warning(
                            "Failed to parse Band message: %s",
                            raw_msg,
                            exc_info=True,
                        )

                logger.info(
                    "Band: fetched %d messages from chat %s",
                    len(messages),
                    self._chat_id,
                )
                return messages

            except BandAPIError:
                raise
            except httpx.TimeoutException as exc:
                last_error = exc
                logger.warning(
                    "Band request timed out (attempt %d/%d)",
                    attempt + 1,
                    BAND_RETRY_ATTEMPTS,
                )
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning(
                    "Band HTTP error (attempt %d/%d): %s",
                    attempt + 1,
                    BAND_RETRY_ATTEMPTS,
                    exc,
                )

            # Brief backoff before retry
            if attempt < BAND_RETRY_ATTEMPTS - 1:
                await asyncio.sleep(0.5)

        raise BandAPIError(
            f"Band API unreachable after {BAND_RETRY_ATTEMPTS} attempts: "
            f"{last_error}"
        )

    async def _poll_loop(self) -> None:
        """Internal polling loop.

        Calls fetch_messages() at BAND_POLL_INTERVAL_SECONDS intervals
        and stores new messages in the audit service. Runs until
        stop_polling() is called or the task is cancelled.
        """
        logger.info(
            "Band poll loop started (interval=%.1fs, chat=%s)",
            BAND_POLL_INTERVAL_SECONDS,
            self._chat_id,
        )

        while True:
            try:
                messages = await self.fetch_messages()

                for msg in messages:
                    # Track last seen message for deduplication
                    if self._last_message_id and msg.message_id <= self._last_message_id:
                        continue

                    # Store in audit service if available
                    if self._audit_service is not None:
                        try:
                            metadata_dict: dict[str, Any] = {"mentions": msg.mentions}
                            if msg.metadata_json:
                                try:
                                    metadata_dict.update(json.loads(msg.metadata_json))
                                except (json.JSONDecodeError, TypeError):
                                    metadata_dict["raw_metadata"] = msg.metadata_json

                            await self._audit_service.log_event(
                                agent_name=msg.sender,
                                event_type=msg.message_type,
                                content=msg.content,
                                metadata=metadata_dict,
                                target_agent=msg.mentions[0] if msg.mentions else None,
                            )
                            logger.debug(
                                "Stored message %s in audit log",
                                msg.message_id,
                            )
                        except Exception:
                            logger.exception(
                                "Failed to store message %s in audit log",
                                msg.message_id,
                            )
                    else:
                        logger.debug(
                            "Band message [%s] %s: %s",
                            msg.message_type,
                            msg.sender,
                            msg.content[:100] if msg.content else "",
                        )

                    # Update watermark
                    if msg.message_id:
                        self._last_message_id = msg.message_id

            except BandAPIError as exc:
                logger.warning("Band poll error: %s", exc)
            except asyncio.CancelledError:
                logger.info("Band poll loop cancelled")
                break
            except Exception:
                logger.exception("Unexpected error in Band poll loop")

            await asyncio.sleep(BAND_POLL_INTERVAL_SECONDS)

    async def start_polling(self) -> None:
        """Start the background polling loop.

        No-op if Band credentials are not configured (logs a warning).
        The polling loop runs as a background asyncio task.
        """
        if not self.is_configured:
            logger.warning(
                "Band polling disabled: credentials not configured. "
                "Set BAND_API_KEY and BAND_ROOM_ID."
            )
            return

        if self._poll_task is not None and not self._poll_task.done():
            logger.warning("Band poll loop already running")
            return

        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("Band polling task started")

    async def stop_polling(self) -> None:
        """Stop the polling loop.

        Cancels the background task and waits for it to finish.
        Safe to call multiple times or when not running.
        """
        if self._poll_task is None or self._poll_task.done():
            logger.debug("Band poll loop not running, nothing to stop")
            return

        self._poll_task.cancel()
        try:
            await self._poll_task
        except asyncio.CancelledError:
            pass

        self._poll_task = None
        logger.info("Band polling task stopped")

    async def close(self) -> None:
        """Close the HTTP client and stop polling.

        Safe to call multiple times. After close, the client will be
        recreated on the next request.
        """
        await self.stop_polling()
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            logger.debug("Band client session closed")
