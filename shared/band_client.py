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

#: Maximum number of @mention hops the simulated cascade will follow.
#: Guarantees termination even if agents mention each other in a cycle.
#: Depth 5 covers the longest chain: system -> specialist -> reviewer
#: -> coordinator, plus the emergency variant (system -> ER -> ground-ops
#: -> ER -> reviewer -> coordinator).
_MAX_CASCADE_DEPTH: int = 5


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


def _extract_mention_handles(metadata: object, mentions_field: object) -> list[str]:
    """Pull @mention handles out of a Band ChatMessage payload.

    Band stores mentions inside ``metadata`` rather than as a top-level
    field, and they may be plain handles (``"weather-analyst"``), dicts
    (``{"id": "...", "handle": "...", "name": "..."}``), or ``@[[uuid]]``
    tokens embedded in content. This helper normalises all of those into
    a flat list of handle strings.

    Args:
        metadata: The message ``metadata`` value (often a dict).
        mentions_field: A legacy top-level ``mentions`` array, if present.

    Returns:
        A list of mention handles (without the leading ``@``).
    """
    handles: list[str] = []
    seen: set[str] = set()

    def _add(candidate: object) -> None:
        if isinstance(candidate, str):
            value = candidate.strip().lstrip("@")
        elif isinstance(candidate, dict):
            value = str(
                candidate.get("handle") or candidate.get("name") or candidate.get("id") or ""
            ).strip()
        else:
            return
        # Band sometimes embeds mentions as @[[uuid]] in content; strip
        # those wrappers down to whatever sits between the brackets.
        if value.startswith("[[") and value.endswith("]]"):
            value = value[2:-2]
        if value and value not in seen:
            seen.add(value)
            handles.append(value)

    candidates: list[object] = []
    if isinstance(mentions_field, list):
        candidates.extend(mentions_field)
    if isinstance(metadata, dict):
        raw_mentions = metadata.get("mentions")
        if isinstance(raw_mentions, list):
            candidates.extend(raw_mentions)

    for candidate in candidates:
        _add(candidate)
    return handles


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

        Agent replies that themselves @mention another registered agent
        are cascaded transitively (mirroring how real Band routes
        @mentions between agents), up to ``_MAX_CASCADE_DEPTH`` hops to
        guarantee termination.

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

        # Seed the cascade with the original outbound message.
        await self._cascade(message, echo, depth=0)

        return posted_id

    async def _cascade(
        self,
        outbound: BandOutboundMessage,
        inbound: BandInboundMessage,
        depth: int,
    ) -> None:
        """Recursively dispatch a message to mentioned agents.

        Each mentioned agent's reply is buffered and, if it mentions
        further registered agents, dispatched in turn.

        Args:
            outbound: The outbound message to hand to handlers.
            inbound: The buffered inbound echo/reply these mentions came from.
            depth: Current cascade depth (0 = original post).
        """
        if depth > _MAX_CASCADE_DEPTH:
            logger.debug("Cascade depth limit reached at depth %d", depth)
            return

        for agent_name in outbound.mentions:
            handler = self._handlers.get(agent_name)
            if handler is None:
                logger.debug("No simulated handler for '%s'", agent_name)
                continue
            try:
                replies = await handler(outbound)
            except Exception:
                logger.exception(
                    "Simulated agent '%s' raised while handling message",
                    agent_name,
                )
                continue

            for reply in replies:
                async with self._lock:
                    self._counter += 1
                    reply_id = f"sim-{self._counter}"
                reply = reply.model_copy(update={"message_id": reply_id})
                self._buffer.append(reply)
                logger.debug(
                    "Simulated '%s' replied: %s",
                    agent_name,
                    reply.content[:80],
                )
                # If the reply mentions more agents, cascade further.
                if reply.mentions:
                    nested = BandOutboundMessage(
                        sender=reply.sender,
                        content=reply.content,
                        mentions=list(reply.mentions),
                        message_type=reply.message_type,
                        metadata=reply.metadata,
                        correlation_id=reply.correlation_id,
                    )
                    await self._cascade(nested, reply, depth=depth + 1)

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

LIVE_BAND_BASE_URL: str = "https://app.band.ai"
LIVE_BAND_MESSAGES_PATH: str = "/api/v1/agent/chats/{chat_id}/messages"
LIVE_BAND_EVENTS_PATH: str = "/api/v1/agent/chats/{chat_id}/events"
LIVE_BAND_CHATS_PATH: str = "/api/v1/agent/chats"
LIVE_BAND_PARTICIPANTS_PATH: str = "/api/v1/agent/chats/{chat_id}/participants"
LIVE_BAND_TIMEOUT_SECONDS: int = 10

#: Supported structured event types for the /events endpoint, per the
#: Band API's ChatEventMessageType. The text message type goes through
#: the /messages endpoint instead.
LIVE_BAND_EVENT_TYPES: tuple[str, ...] = (
    "thought",
    "task",
    "tool_call",
    "tool_result",
    "error",
)


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
        mention_map: dict[str, str] | None = None,
        owner_user_id: str | None = None,
    ) -> None:
        """Initialise the live client.

        Args:
            api_key: Band API key for the ``system-ingest`` identity.
            chat_id: Band room/chat id where agents collaborate.
            base_url: Band API base URL.
            mention_map: Optional mapping of agent handle (e.g.
                ``"conflict-detector"``) to Band agent UUID. The
                ``/messages`` endpoint requires ``mentions[].id`` to be the
                agent's UUID, so each outbound mention handle is resolved
                through this map before posting. Handles absent from the
                map are passed through verbatim (Band will reject them
                with a 422, surfacing a missing mapping loudly).
            owner_user_id: Optional Band user UUID for the human owner.
                When a room is rotated, the new room is populated with all
                agents + this user so every participant sees messages.
        """
        self._api_key = api_key
        self._chat_id = chat_id
        self._base_url = base_url.rstrip("/")
        self._mention_map = dict(mention_map) if mention_map else {}
        self._owner_user_id = owner_user_id
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

        Band's ``/messages`` endpoint enforces ``minItems: 1`` on
        ``mentions`` — a message *must* address at least one agent (and
        cannot mention the poster itself). When ``message.mentions`` is
        empty — e.g. the veto/system notes emitted by
        ``BandPoster._post_vetoed_lower_priority`` — there is no agent
        to address, so the post is routed to the ``/events`` endpoint as
        a ``task`` event instead. That endpoint has no mention
        requirement and still carries ``metadata``, so structured veto
        payloads survive the round-trip.

        If the room has hit its message limit (Band returns a 403 with
        ``limit_reached``), the oldest messages are pruned automatically
        and the post is retried once.

        Args:
            message: Outbound message with content and @mentions.

        Returns:
            The Band-assigned message id.

        Raises:
            BandLiveError: If the Band API returns a non-2xx status
                (other than a recoverable limit_reached).
        """
        # No agent to address -> /messages would 422 (minItems: 1).
        # Route to /events as a structured note instead.
        if not message.mentions:
            return await self.post_event(
                agent=message.sender,
                event_type="task",
                content=message.content,
                metadata={
                    **(dict(message.metadata) if message.metadata else {}),
                    **(
                        {"correlation_id": message.correlation_id}
                        if message.correlation_id is not None
                        else {}
                    ),
                },
            )

        client = self._get_client()
        url = f"{self._base_url}{LIVE_BAND_MESSAGES_PATH.format(chat_id=self._chat_id)}"

        # Band's ChatMessageRequest accepts only `content` and `mentions` —
        # there is no metadata field on the /messages endpoint.  Any
        # structured metadata (correlation_id, advisory payload, etc.) is
        # appended as a JSON trailer inside the content so that the
        # ingester can extract it back on the reply path.
        content = message.content
        metadata: dict = dict(message.metadata) if message.metadata else {}
        if message.correlation_id is not None:
            metadata["correlation_id"] = message.correlation_id
        if metadata:
            import json as _json

            content = f"{content}\n```json\n{_json.dumps(metadata)}\n```"

        payload: dict = {
            "message": {
                "content": content,
                # Band's ChatMessageRequest requires each mention's `id`
                # to be the agent's UUID (not its handle string). Resolve
                # every handle through the mention map; unknown handles
                # are passed through so Band rejects them visibly rather
                # than silently mis-routing the @mention.
                "mentions": [
                    {
                        "id": self._mention_map.get(name, name),
                        "handle": name,
                        "name": name,
                    }
                    for name in message.mentions
                ],
            }
        }

        response = await client.post(url, json=payload)
        if response.status_code >= 400:
            # Auto-rotate room on limit_reached.
            if self._is_limit_reached(response):
                logger.warning(
                    "Band room hit message limit — auto-rotating to a new room"
                )
                await self._rotate_room()
                # Retry with the new room id.
                url = f"{self._base_url}{LIVE_BAND_MESSAGES_PATH.format(chat_id=self._chat_id)}"
                response = await client.post(url, json=payload)
            if response.status_code >= 400:
                raise BandLiveError(
                    f"Band POST messages failed ({response.status_code}): {response.text[:200]}"
                )
        data = response.json()
        # Successful responses are wrapped as {"data": {"id": ...}}.
        sent = data.get("data") if isinstance(data, dict) else None
        sent_id = sent.get("id") if isinstance(sent, dict) else None
        return str(sent_id or data.get("id") or uuid.uuid4().hex)

    @staticmethod
    def _is_limit_reached(response: httpx.Response) -> bool:
        """Check whether a failed response is the room message-limit error."""
        if response.status_code != 403:
            return False
        try:
            body = response.json()
            return body.get("error", {}).get("code") == "limit_reached"
        except Exception:
            return False

    async def _rotate_room(self) -> None:
        """Create a new Band chat room, add all agents + owner, and switch.

        Called automatically when the current room hits the message limit
        (``limit_reached`` 403). The old room remains for reference; all
        future posts go to the new room. The new room is populated with
        every agent from the mention map plus the human owner (if configured)
        so that all participants can see messages immediately.

        Raises:
            BandLiveError: If the room creation or participant addition fails.
        """
        client = self._get_client()
        url = f"{self._base_url}{LIVE_BAND_CHATS_PATH}"
        old_chat_id = self._chat_id
        try:
            # Step 1: Create the room.
            response = await client.post(url, json={})
            if response.status_code >= 400:
                raise BandLiveError(
                    f"Band room creation failed ({response.status_code}): "
                    f"{response.text[:200]}"
                )
            data = response.json()
            created = data.get("data") if isinstance(data, dict) else None
            new_chat_id = created.get("id") if isinstance(created, dict) else None
            if not new_chat_id:
                raise BandLiveError(
                    f"Band room creation returned no id: {response.text[:200]}"
                )
            self._chat_id = str(new_chat_id)
            logger.warning(
                "Room rotated: %s -> %s (old room preserved at limit)",
                old_chat_id,
                self._chat_id,
            )

            # Step 2: Add all agents + human owner as participants.
            await self._populate_room(self._chat_id)

        except BandLiveError:
            raise
        except Exception as exc:
            raise BandLiveError(
                f"Band room creation error: {exc}"
            ) from exc

    async def _populate_room(self, chat_id: str) -> None:
        """Add all agents and the human owner to a chat room.

        Uses the mention_map (handle → UUID) to add each agent, then
        adds the owner user if configured. Failures to add individual
        participants are logged but do not block room rotation — the
        room is still usable, just without that participant.

        Args:
            chat_id: The chat room to populate.
        """
        client = self._get_client()
        participants_url = f"{self._base_url}{LIVE_BAND_PARTICIPANTS_PATH.format(chat_id=chat_id)}"

        # Collect all unique UUIDs: agents from mention map + owner.
        uuids_to_add: list[str] = []
        seen: set[str] = set()
        for agent_uuid in self._mention_map.values():
            if agent_uuid and agent_uuid not in seen:
                seen.add(agent_uuid)
                uuids_to_add.append(agent_uuid)
        if self._owner_user_id and self._owner_user_id not in seen:
            uuids_to_add.append(self._owner_user_id)

        for participant_id in uuids_to_add:
            try:
                resp = await client.post(
                    participants_url,
                    json={"participant": {"participant_id": participant_id, "role": "member"}},
                )
                if resp.status_code >= 400:
                    logger.warning(
                        "Failed to add participant %s to room %s (%s): %s",
                        participant_id[:8],
                        chat_id[:8],
                        resp.status_code,
                        resp.text[:200],
                    )
                else:
                    logger.info(
                        "Added participant %s to room %s",
                        participant_id[:8],
                        chat_id[:8],
                    )
            except Exception:
                logger.exception(
                    "Error adding participant %s to room %s",
                    participant_id[:8],
                    chat_id[:8],
                )

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
        # Band's ChatEventRequest: {message_type, content, metadata?}.
        event: dict = {
            "message_type": event_type,
            "content": content,
        }
        if metadata is not None:
            event["metadata"] = metadata

        response = await client.post(url, json={"event": event})
        if response.status_code >= 400:
            raise BandLiveError(
                f"Band POST events failed ({response.status_code}): {response.text[:200]}"
            )
        data = response.json()
        created = data.get("data") if isinstance(data, dict) else None
        created_id = created.get("id") if isinstance(created, dict) else None
        return str(created_id or data.get("id") or uuid.uuid4().hex)

    async def fetch_replies(
        self, since_id: str | None = None, limit: int = BAND_MESSAGE_PAGE_SIZE
    ) -> list[BandInboundMessage]:
        """GET recent messages from the Band room.

        Polls ``GET /api/v1/agent/chats/{chat_id}/messages?status=all``.
        Band does not support cursoring by id, so ``since_id`` is applied
        client-side: any returned message whose id was already seen is
        filtered out (oldest-first ordering is preserved).

        Args:
            since_id: Watermark message id (last seen by the caller).
            limit: Page size (forwarded as ``page_size``).

        Returns:
            List of inbound messages newer than ``since_id`` (oldest-first).

        Raises:
            BandLiveError: If the Band API returns a non-2xx status.
        """
        client = self._get_client()
        url = f"{self._base_url}{LIVE_BAND_MESSAGES_PATH.format(chat_id=self._chat_id)}"
        # Band's list endpoint uses page_size (max 100) and a status filter.
        params: dict[str, str | int] = {
            "status": "all",
            "page_size": min(limit, 100),
        }

        response = await client.get(url, params=params)
        if response.status_code >= 400:
            raise BandLiveError(
                f"Band GET messages failed ({response.status_code}): {response.text[:200]}"
            )
        data = response.json()
        raw_messages: Iterable[dict] = data.get("data") or data.get("messages") or []

        inbound: list[BandInboundMessage] = []
        for raw in raw_messages:
            if not isinstance(raw, dict):
                continue
            message_id = str(raw.get("id", ""))
            if since_id is not None and message_id and message_id == since_id:
                continue

            metadata = raw.get("metadata")
            # ChatMessage exposes sender_name (preferred) then sender_id;
            # older/legacy shapes may carry a bare `role` instead.
            sender = (
                raw.get("sender_name")
                or raw.get("sender_id")
                or raw.get("role")
                or "unknown"
            )
            inbound.append(
                BandInboundMessage(
                    message_id=message_id,
                    timestamp=str(raw.get("inserted_at") or raw.get("created_at") or ""),
                    sender=str(sender),
                    content=str(raw.get("content", "")),
                    mentions=_extract_mention_handles(metadata, raw.get("mentions")),
                    message_type=str(raw.get("message_type") or raw.get("type") or "text"),
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
    mention_map: dict[str, str] | None = None,
    owner_user_id: str | None = None,
) -> BandClient:
    """Build the appropriate BandClient for the requested mode.

    Args:
        mode: ``sim`` for offline simulation, ``live`` for real Band.
        api_key: Band API key (required for ``live``).
        chat_id: Band room id (required for ``live``).
        mention_map: Optional handle→UUID map (required for ``live`` to
            post valid ``mentions[].id`` values). Ignored in ``sim`` mode.
        owner_user_id: Optional Band user UUID for the human owner.
            When a room is rotated, the new room is populated with all
            agents + this user. Ignored in ``sim`` mode.

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
        client = LiveBandClient(
            api_key=api_key,
            chat_id=chat_id,
            mention_map=mention_map,
            owner_user_id=owner_user_id,
        )
        logger.info(
            "BandClient created in live mode (chat=%s, %d agents mapped, owner=%s)",
            chat_id,
            len(mention_map or {}),
            "yes" if owner_user_id else "no",
        )
        return client

    raise ValueError(
        f"Unknown BAND_MODE '{mode}'. Must be one of: sim | live"
    )
