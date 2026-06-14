"""Band platform client abstraction.

Provides a single :class:`BandClient` protocol that the backend talks to
regardless of whether agents are running on the real Band platform or in
an in-process simulation. This lets the entire collaboration loop
(detect → @mention → respond → advisory) run and be tested with **zero
credentials**: flip ``BAND_MODE`` from ``sim`` to ``live`` once the Band
room and agents are provisioned.

Two implementations are provided:

- :class:`SimulatedBandClient` — an in-process async message bus. Posts
  are fanned out to registered agent handler callables. Used during
  development, tests, and the default offline demo.
- :class:`LiveBandClient` — real Band REST calls to
  ``POST /api/v1/agent/chats/{id}/messages`` (and ``/events``) using a
  dedicated "system-ingest" agent identity.

The backend never imports either class directly — it consumes the
:class:`BandClient` protocol via :func:`create_band_client`.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Awaitable, Callable, Iterable, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, Field

from shared.constants import BAND_MESSAGE_PAGE_SIZE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Band message / event models
# ---------------------------------------------------------------------------

#: Identifier used by the backend when it posts system data into Band.
SYSTEM_SENDER: str = "system-ingest"

#: Standard Band event types that the SDK reserves for ``send_event``.
BAND_EVENT_TYPES: tuple[str, ...] = (
    "thought",
    "task",
    "tool_call",
    "tool_result",
    "error",
)


class BandOutboundMessage(BaseModel):
    """A message the backend wants to post into the Band room.

    Attributes:
        sender: Agent identity posting the message (e.g. ``system-ingest``
            for backend-driven @mentions).
        content: Human-readable message body. Must contain ``@mentions``
            for any agent that should receive it — Band only delivers
            messages to mentioned participants.
        mentions: Agent names that appear as ``@mentions`` in content.
        message_type: Band message type (default ``text``).
        metadata: Optional structured payload serialised alongside the
            message (e.g. a ConflictAdvisory dict).
        correlation_id: Optional id linking a request to its response,
            used to match advisories back to the triggering event.
    """

    model_config = {"arbitrary_types_allowed": True}

    sender: str = Field(description="Agent identity posting the message")
    content: str = Field(description="Message body, including @mentions")
    mentions: list[str] = Field(
        default_factory=list, description="@mentioned agent names"
    )
    message_type: str = Field(default="text", description="Band message type")
    metadata: dict | None = Field(
        default=None, description="Optional structured payload"
    )
    correlation_id: str | None = Field(
        default=None, description="Optional id linking request → response"
    )


class BandInboundMessage(BaseModel):
    """A message observed in the Band room (agent reply or system echo).

    Attributes:
        message_id: Unique message identifier (Band-assigned or simulated).
        timestamp: UTC ISO timestamp the message was observed.
        sender: Agent identity that produced the message.
        content: Message body.
        mentions: Agent names mentioned in this message.
        message_type: Band message type (``text`` / ``thought`` / ...).
        metadata: Optional structured payload, if present.
        correlation_id: Optional correlation id carried from the request.
    """

    message_id: str = Field(description="Unique message identifier")
    timestamp: str = Field(description="UTC ISO timestamp")
    sender: str = Field(description="Agent identity that produced the message")
    content: str = Field(description="Message body")
    mentions: list[str] = Field(default_factory=list, description="Mentioned agents")
    message_type: str = Field(default="text", description="Band message type")
    metadata: dict | None = Field(default=None, description="Structured payload")
    correlation_id: str | None = Field(
        default=None, description="Correlation id linking request → response"
    )


# ---------------------------------------------------------------------------
# Agent handler signature (simulation mode)
# ---------------------------------------------------------------------------

#: Callable invoked by :class:`SimulatedBandClient` when a message
#: mentions a registered agent. It receives the inbound message and
#: returns zero or more outbound replies (advisories).
AgentHandler = Callable[[BandOutboundMessage], Awaitable[list[BandInboundMessage]]]


# ---------------------------------------------------------------------------
# Client protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class BandClient(Protocol):
    """Transport-agnostic Band collaboration client.

    The backend posts @mentions and reads agent replies through this
    interface, so the simulation and live transports are
    interchangeable.
    """

    @property
    def mode(self) -> str:
        """Return the transport mode (``sim`` or ``live``)."""
        ...

    async def post_message(self, message: BandOutboundMessage) -> str:
        """Post a message into the Band room.

        Args:
            message: Outbound message with content and @mentions.

        Returns:
            The message id assigned by the transport.
        """
        ...

    async def post_event(
        self, agent: str, event_type: str, content: str, metadata: dict | None = None
    ) -> str:
        """Post a structured Band event (thought/task/tool_call/tool_result/error).

        Args:
            agent: Agent identity that produced the event.
            event_type: One of :data:`BAND_EVENT_TYPES`.
            content: Human-readable description of the event.
            metadata: Optional structured payload.

        Returns:
            The event id assigned by the transport.
        """
        ...

    async def fetch_replies(
        self, since_id: str | None = None, limit: int = BAND_MESSAGE_PAGE_SIZE
    ) -> list[BandInboundMessage]:
        """Fetch agent replies posted to the room.

        Args:
            since_id: If provided, only return messages with id greater
                than this watermark.
            limit: Maximum number of messages to return.

        Returns:
            List of inbound messages ordered oldest-first.
        """
        ...

    async def close(self) -> None:
        """Release any transport resources."""
        ...


# ---------------------------------------------------------------------------
# Simulation transport
# ---------------------------------------------------------------------------


class SimulatedBandClient:
    """In-process Band client used for offline development and tests.

    Messages posted via :meth:`post_message` are fanned out synchronously
    to any registered :data:`AgentHandler` whose agent is mentioned.
    Replies are appended to an internal buffer and surfaced via
    :meth:`fetch_replies`. No network and no LLM calls are made.

    This is what makes the radar light up with conflict lines, blinking
    7700s, and a populated agent chat panel without any Band credentials.
    """

    def __init__(self) -> None:
        """Initialise an empty simulated room."""
        self._handlers: dict[str, AgentHandler] = {}
        self._buffer: list[BandInboundMessage] = []
        self._counter: int = 0
        self._lock: asyncio.Lock = asyncio.Lock()

    @property
    def mode(self) -> str:
        """Return ``sim``."""
        return "sim"

    def register_agent(self, agent_name: str, handler: AgentHandler) -> None:
        """Register a handler that simulates an agent's responses.

        Args:
            agent_name: Agent identity (without ``@``).
            handler: Async callable invoked when the agent is mentioned.
        """
        self._handlers[agent_name] = handler
        logger.debug("Registered simulated agent '%s'", agent_name)

    async def post_message(self, message: BandOutboundMessage) -> str:
        """Fan the message out to any mentioned simulated agents.

        Args:
            message: Outbound message. Each mentioned agent with a
                registered handler is invoked; its replies are buffered.

        Returns:
            The synthetic message id assigned to the posted message.
        """
        async with self._lock:
            self._counter += 1
            posted_id = f"sim-{self._counter}"

        # Echo the system post into the room so the audit/chat view sees it.
        echo = BandInboundMessage(
            message_id=posted_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            sender=message.sender,
            content=message.content,
            mentions=list(message.mentions),
            message_type=message.message_type,
            metadata=message.metadata,
            correlation_id=message.correlation_id,
        )
        self._buffer.append(echo)

        # Dispatch to each mentioned agent that has a registered handler.
        for agent_name in message.mentions:
            handler = self._handlers.get(agent_name)
            if handler is None:
                logger.debug("No simulated handler for '%s'", agent_name)
                continue
            try:
                replies = await handler(message)
            except Exception:
                logger.exception(
                    "Simulated agent '%s' raised while handling message %s",
                    agent_name,
                    posted_id,
                )
                continue
            for reply in replies:
                self._buffer.append(reply)
                logger.debug(
                    "Simulated '%s' replied to %s: %s",
                    agent_name,
                    posted_id,
                    reply.content[:80],
                )

        return posted_id

    async def post_event(
        self, agent: str, event_type: str, content: str, metadata: dict | None = None
    ) -> str:
        """Buffer a structured event as an inbound message.

        Args:
            agent: Agent identity that produced the event.
            event_type: One of :data:`BAND_EVENT_TYPES`.
            content: Human-readable description.
            metadata: Optional structured payload.

        Returns:
            The synthetic event id.
        """
        async with self._lock:
            self._counter += 1
            event_id = f"sim-{self._counter}"

        self._buffer.append(
            BandInboundMessage(
                message_id=event_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                sender=agent,
                content=content,
                message_type=event_type,
                metadata=metadata,
            )
        )
        return event_id

    async def fetch_replies(
        self, since_id: str | None = None, limit: int = BAND_MESSAGE_PAGE_SIZE
    ) -> list[BandInboundMessage]:
        """Return buffered messages after the watermark (oldest-first).

        Args:
            since_id: Watermark id. Messages with a strictly greater
                synthetic counter are returned.
            limit: Maximum number of messages to return.

        Returns:
            List of inbound messages in the order they were produced.
        """
        if since_id is None:
            return list(self._buffer[-limit:])

        try:
            watermark = int(since_id.split("-")[-1])
        except (IndexError, ValueError):
            watermark = -1

        out: list[BandInboundMessage] = []
        for msg in self._buffer:
            try:
                msg_num = int(msg.message_id.split("-")[-1])
            except (IndexError, ValueError):
                msg_num = 0
            if msg_num > watermark:
                out.append(msg)
        return out[-limit:] if len(out) > limit else out

    async def close(self) -> None:
        """No resources to release in simulation mode."""
        return


# ---------------------------------------------------------------------------
# Live transport
# ---------------------------------------------------------------------------

LIVE_BAND_BASE_URL: str = "https://api.band.ai"
LIVE_BAND_MESSAGES_PATH: str = "/api/v1/agent/chats/{chat_id}/messages"
LIVE_BAND_EVENTS_PATH: str = "/api/v1/agent/chats/{chat_id}/events"
LIVE_BAND_TIMEOUT_SECONDS: int = 10


class BandLiveError(Exception):
    """Raised when a live Band REST call fails."""


class LiveBandClient:
    """Real Band REST client backed by an httpx.AsyncClient.

    Posts messages and events to the Band room using the ``system-ingest``
    agent identity. Replies from remote agents are fetched via the
    messages endpoint. This transport is only used when ``BAND_MODE=live``
    and Band credentials are configured.
    """

    def __init__(
        self,
        api_key: str,
        chat_id: str,
        base_url: str = LIVE_BAND_BASE_URL,
    ) -> None:
        """Initialise the live client.

        Args:
            api_key: Band API key for the ``system-ingest`` identity.
            chat_id: Band room/chat id where agents collaborate.
            base_url: Band API base URL.
        """
        self._api_key = api_key
        self._chat_id = chat_id
        self._base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    @property
    def mode(self) -> str:
        """Return ``live``."""
        return "live"

    def _get_client(self) -> httpx.AsyncClient:
        """Lazily create the shared httpx client.

        Returns:
            A configured httpx.AsyncClient with the Band API key header.
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"X-API-Key": self._api_key},
                timeout=LIVE_BAND_TIMEOUT_SECONDS,
            )
        return self._client

    async def post_message(self, message: BandOutboundMessage) -> str:
        """POST a message to the Band room.

        Args:
            message: Outbound message with content and @mentions.

        Returns:
            The Band-assigned message id.

        Raises:
            BandLiveError: If the Band API returns a non-2xx status.
        """
        client = self._get_client()
        url = f"{self._base_url}{LIVE_BAND_MESSAGES_PATH.format(chat_id=self._chat_id)}"
        body: dict = {
            "role": message.sender,
            "content": message.content,
            "mentions": list(message.mentions),
        }
        if message.metadata is not None:
            body["metadata"] = message.metadata
        if message.correlation_id is not None:
            body["metadata"] = {**(body.get("metadata") or {}), "correlation_id": message.correlation_id}

        response = await client.post(url, json=body)
        if response.status_code >= 400:
            raise BandLiveError(
                f"Band POST messages failed ({response.status_code}): {response.text[:200]}"
            )
        data = response.json()
        return str(data.get("id", uuid.uuid4().hex))

    async def post_event(
        self, agent: str, event_type: str, content: str, metadata: dict | None = None
    ) -> str:
        """POST a structured event to the Band room.

        Args:
            agent: Agent identity that produced the event.
            event_type: One of :data:`BAND_EVENT_TYPES`.
            content: Human-readable description.
            metadata: Optional structured payload.

        Returns:
            The Band-assigned event id.

        Raises:
            BandLiveError: If the Band API returns a non-2xx status.
        """
        client = self._get_client()
        url = f"{self._base_url}{LIVE_BAND_EVENTS_PATH.format(chat_id=self._chat_id)}"
        body: dict = {
            "role": agent,
            "type": event_type,
            "content": content,
        }
        if metadata is not None:
            body["metadata"] = metadata

        response = await client.post(url, json=body)
        if response.status_code >= 400:
            raise BandLiveError(
                f"Band POST events failed ({response.status_code}): {response.text[:200]}"
            )
        data = response.json()
        return str(data.get("id", uuid.uuid4().hex))

    async def fetch_replies(
        self, since_id: str | None = None, limit: int = BAND_MESSAGE_PAGE_SIZE
    ) -> list[BandInboundMessage]:
        """GET recent messages from the Band room.

        Args:
            since_id: Watermark message id (forwarded to Band if supported).
            limit: Page size.

        Returns:
            List of inbound messages (oldest-first).

        Raises:
            BandLiveError: If the Band API returns a non-2xx status.
        """
        client = self._get_client()
        url = f"{self._base_url}{LIVE_BAND_MESSAGES_PATH.format(chat_id=self._chat_id)}"
        params: dict[str, object] = {"status": "all", "limit": limit}
        if since_id is not None:
            params["after"] = since_id

        response = await client.get(url, params=params)
        if response.status_code >= 400:
            raise BandLiveError(
                f"Band GET messages failed ({response.status_code}): {response.text[:200]}"
            )
        data = response.json()
        raw_messages: Iterable[dict] = data.get("messages") or data.get("data") or []

        inbound: list[BandInboundMessage] = []
        for raw in raw_messages:
            metadata = raw.get("metadata")
            inbound.append(
                BandInboundMessage(
                    message_id=str(raw.get("id", "")),
                    timestamp=str(raw.get("created_at", "")),
                    sender=str(raw.get("role", "unknown")),
                    content=str(raw.get("content", "")),
                    mentions=list(raw.get("mentions") or []),
                    message_type=str(raw.get("type", "text")),
                    metadata=metadata if isinstance(metadata, dict) else None,
                    correlation_id=(
                        metadata.get("correlation_id")
                        if isinstance(metadata, dict)
                        else None
                    ),
                )
            )
        return inbound

    async def close(self) -> None:
        """Close the underlying httpx client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_band_client(
    mode: str,
    api_key: str | None = None,
    chat_id: str | None = None,
) -> BandClient:
    """Build the appropriate BandClient for the requested mode.

    Args:
        mode: ``sim`` for offline simulation, ``live`` for real Band.
        api_key: Band API key (required for ``live``).
        chat_id: Band room id (required for ``live``).

    Returns:
        A :class:`BandClient` implementation.

    Raises:
        ValueError: If ``mode`` is unknown or ``live`` is requested
            without credentials.
    """
    if mode == "sim":
        client: BandClient = SimulatedBandClient()
        logger.info("BandClient created in simulation mode (no network)")
        return client

    if mode == "live":
        if not api_key or not chat_id:
            raise ValueError(
                "BAND_MODE=live requires BAND_API_KEY and BAND_ROOM_ID"
            )
        client = LiveBandClient(api_key=api_key, chat_id=chat_id)
        logger.info("BandClient created in live mode (chat=%s)", chat_id)
        return client

    raise ValueError(
        f"Unknown BAND_MODE '{mode}'. Must be one of: sim | live"
    )
