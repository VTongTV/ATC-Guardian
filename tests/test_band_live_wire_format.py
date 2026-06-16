"""Integration test: verify LiveBandClient wire format matches the Band SDK contract.

Uses httpx.MockTransport to intercept outgoing requests and assert that
the exact JSON bodies, query params, headers, and response parsing all
conform to the thenvoi_rest SDK types (ChatMessageRequest, ChatMessage,
ChatEventRequest, MessageSentResponse, ListAgentMessagesResponse, etc.).

These tests require no network — every HTTP exchange is faked in-process.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx
import pytest

from shared.band_client import (
    LIVE_BAND_BASE_URL,
    BandInboundMessage,
    BandLiveError,
    BandOutboundMessage,
    LiveBandClient,
)

CHAT_ID = "chat-aaaa-bbbb-cccc-ddddeeeeffff"
API_KEY = "band_a_test_key"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Run a coroutine to completion in a fresh event loop."""
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_route(routes: dict[str, tuple[int, dict]]):
    """Build a simple mock handler from a {path_regex: (status, body)} map."""

    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        for pattern, (status, body) in routes.items():
            if re.search(pattern, path):
                return httpx.Response(
                    status,
                    content=json.dumps(body).encode(),
                    headers={"content-type": "application/json"},
                    request=request,
                )
        return httpx.Response(
            404,
            content=json.dumps({"error": "no mock route"}).encode(),
            headers={"content-type": "application/json"},
            request=request,
        )

    return handler


def _make_client(routes: dict[str, tuple[int, dict]]) -> LiveBandClient:
    """Create a LiveBandClient backed by a mock transport."""
    transport = httpx.MockTransport(_make_route(routes))
    http_client = httpx.AsyncClient(
        transport=transport,
        base_url=LIVE_BAND_BASE_URL,
        headers={"X-API-Key": API_KEY},
    )
    client = LiveBandClient(api_key=API_KEY, chat_id=CHAT_ID)
    client._client = http_client  # noqa: SLF001
    return client


def _make_capturing_client():
    """Create a LiveBandClient whose transport captures the last request."""
    captured: dict[str, httpx.Request] = {}

    async def capturing_handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200,
            content=json.dumps(
                {"data": {"id": "msg-captured", "success": True, "recipients": []}}
            ).encode(),
            headers={"content-type": "application/json"},
            request=request,
        )

    transport = httpx.MockTransport(capturing_handler)
    http_client = httpx.AsyncClient(
        transport=transport,
        base_url=LIVE_BAND_BASE_URL,
        headers={"X-API-Key": API_KEY},
    )
    client = LiveBandClient(api_key=API_KEY, chat_id=CHAT_ID)
    client._client = http_client  # noqa: SLF001
    return client, captured


def _body(request: httpx.Request) -> dict[str, Any]:
    """Parse JSON body from an httpx Request."""
    return json.loads(request.content)


# ---------------------------------------------------------------------------
# POST /messages — envelope & field contract
# ---------------------------------------------------------------------------


def test_post_message_wraps_in_message_envelope() -> None:
    """Body must be {"message": {content, mentions}} — not flat."""
    msg_id = "msg-001"
    routes = {
        r"/api/v1/agent/chats/.*/messages$": (
            200,
            {"data": {"id": msg_id, "success": True, "recipients": []}},
        ),
    }
    client = _make_client(routes)
    sent_id = _run(
        client.post_message(
            BandOutboundMessage(
                sender="system-ingest",
                content="@conflict-detector Conflict UAL123/DAL456 CPA 3nm",
                mentions=["conflict-detector"],
            )
        )
    )
    assert sent_id == msg_id
    _run(client.close())


def test_post_message_mentions_are_objects_with_id() -> None:
    """Mentions must be [{id, handle, name}] objects, not bare strings."""
    client, captured = _make_capturing_client()
    _run(
        client.post_message(
            BandOutboundMessage(
                sender="system-ingest",
                content="@weather-analyst SIGMET affects UAL123",
                mentions=["weather-analyst"],
            )
        )
    )
    msg_obj = _body(captured["request"])["message"]
    assert len(msg_obj["mentions"]) == 1
    m = msg_obj["mentions"][0]
    assert m["id"] == "weather-analyst"
    assert "handle" in m
    assert "name" in m
    _run(client.close())


def test_post_message_resolves_mention_handle_to_uuid() -> None:
    """With a mention_map, mentions[].id must be the agent UUID, not the handle.

    Band's /messages endpoint requires mentions[].id to be a UUID (422
    "Expected :uuid" otherwise). The LiveBandClient must resolve every
    handle through its mention map before posting.
    """
    captured: dict[str, httpx.Request] = {}

    async def capturing(req: httpx.Request) -> httpx.Response:
        captured["request"] = req
        return httpx.Response(
            200,
            content=json.dumps(
                {"data": {"id": "msg-uuid", "success": True, "recipients": []}}
            ).encode(),
            headers={"content-type": "application/json"},
            request=req,
        )

    client = LiveBandClient(
        api_key=API_KEY,
        chat_id=CHAT_ID,
        mention_map={
            "conflict-detector": "a5466c42-ff4c-423b-9de5-dbfbf3b85263",
            "weather-analyst": "d1ddadff-8174-46cf-9076-4b2a8a1e3326",
        },
    )
    client._client = httpx.AsyncClient(  # noqa: SLF001
        transport=httpx.MockTransport(capturing),
        base_url=LIVE_BAND_BASE_URL,
        headers={"X-API-Key": API_KEY},
    )

    _run(
        client.post_message(
            BandOutboundMessage(
                sender="system-ingest",
                content="@conflict-detector CPA 3nm",
                mentions=["conflict-detector", "weather-analyst"],
            )
        )
    )
    mentions = _body(captured["request"])["message"]["mentions"]
    assert mentions[0]["id"] == "a5466c42-ff4c-423b-9de5-dbfbf3b85263"
    assert mentions[0]["handle"] == "conflict-detector"
    assert mentions[1]["id"] == "d1ddadff-8174-46cf-9076-4b2a8a1e3326"
    assert mentions[1]["handle"] == "weather-analyst"
    _run(client.close())


def test_post_message_no_role_field() -> None:
    """Sender is implied by the API key; 'role' must not be sent."""
    client, captured = _make_capturing_client()
    _run(
        client.post_message(
            BandOutboundMessage(sender="s", content="@x go", mentions=["x"])
        )
    )
    msg_obj = _body(captured["request"])["message"]
    assert "role" not in msg_obj
    _run(client.close())


def test_post_message_no_metadata_field() -> None:
    """ChatMessageRequest has no metadata; it is embedded in content."""
    client, captured = _make_capturing_client()
    _run(
        client.post_message(
            BandOutboundMessage(
                sender="s",
                content="@x analyze",
                mentions=["x"],
                metadata={"kind": "conflict", "severity": "high"},
                correlation_id="corr-42",
            )
        )
    )
    msg_obj = _body(captured["request"])["message"]
    assert "metadata" not in msg_obj
    assert "```json" in msg_obj["content"]
    assert '"correlation_id": "corr-42"' in msg_obj["content"]
    assert '"kind": "conflict"' in msg_obj["content"]
    _run(client.close())


def test_post_message_uses_x_api_key_header() -> None:
    """Auth must use X-API-Key, not Bearer."""
    client, captured = _make_capturing_client()
    _run(
        client.post_message(
            BandOutboundMessage(sender="s", content="@x go", mentions=["x"])
        )
    )
    headers = captured["request"].headers
    assert headers.get("x-api-key") == API_KEY
    assert "Bearer" not in headers.get("authorization", "")
    _run(client.close())


# ---------------------------------------------------------------------------
# POST /events — envelope & field contract
# ---------------------------------------------------------------------------


def test_post_event_wraps_in_event_envelope() -> None:
    """Body must be {"event": {message_type, content}} — not flat."""
    client, captured = _make_capturing_client()
    _run(
        client.post_event(
            agent="conflict-detector",
            event_type="tool_call",
            content="ran compute_cpa",
            metadata={"cpa_nm": 3.2},
        )
    )
    body = _body(captured["request"])
    assert "event" in body
    assert body["event"]["message_type"] == "tool_call"
    assert body["event"]["content"] == "ran compute_cpa"
    assert body["event"]["metadata"] == {"cpa_nm": 3.2}
    assert "role" not in body["event"]
    assert "type" not in body["event"]
    _run(client.close())


# ---------------------------------------------------------------------------
# GET /messages — query params & response parsing
# ---------------------------------------------------------------------------


def test_fetch_replies_uses_page_size_not_limit() -> None:
    """Query param must be page_size, not limit."""
    captured: dict[str, httpx.Request] = {}

    async def capturing_handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200,
            content=json.dumps(
                {"data": [], "metadata": {"total_count": 0}}
            ).encode(),
            headers={"content-type": "application/json"},
            request=request,
        )

    transport = httpx.MockTransport(capturing_handler)
    http_client = httpx.AsyncClient(transport=transport, base_url=LIVE_BAND_BASE_URL)
    client = LiveBandClient(api_key=API_KEY, chat_id=CHAT_ID)
    client._client = http_client  # noqa: SLF001

    _run(client.fetch_replies(limit=50))

    params = dict(captured["request"].url.params)
    assert "page_size" in params
    assert "limit" not in params
    assert params["status"] == "all"
    _run(client.close())


def test_fetch_replies_parses_chat_message_shape() -> None:
    """Response uses ChatMessage fields: sender_name, inserted_at, message_type."""
    routes = {
        r"/api/v1/agent/chats/.*/messages$": (
            200,
            {
                "data": [
                    {
                        "id": "msg-100",
                        "content": "@coordinator Conflict resolved",
                        "sender_type": "Agent",
                        "sender_id": "agent-uuid-1",
                        "sender_name": "conflict-detector",
                        "message_type": "text",
                        "metadata": {
                            "mentions": [
                                {
                                    "id": "agent-uuid-coord",
                                    "handle": "coordinator",
                                    "name": "Coordinator",
                                }
                            ]
                        },
                        "inserted_at": "2026-06-15T12:00:00Z",
                    },
                    {
                        "id": "msg-101",
                        "content": "Weather clear",
                        "sender_type": "Agent",
                        "sender_id": "agent-uuid-2",
                        "sender_name": "weather-analyst",
                        "message_type": "thought",
                        "inserted_at": "2026-06-15T12:00:05Z",
                    },
                ],
                "metadata": {"total_count": 2, "page_size": 100},
            },
        ),
    }
    client = _make_client(routes)
    replies = _run(client.fetch_replies())

    assert len(replies) == 2

    # First message — ChatMessage shape with metadata.mentions
    assert replies[0].message_id == "msg-100"
    assert replies[0].sender == "conflict-detector"
    assert replies[0].content == "@coordinator Conflict resolved"
    assert replies[0].message_type == "text"
    assert replies[0].timestamp == "2026-06-15T12:00:00Z"
    assert "coordinator" in replies[0].mentions

    # Second message — no metadata.mentions
    assert replies[1].message_id == "msg-101"
    assert replies[1].sender == "weather-analyst"
    assert replies[1].message_type == "thought"
    assert replies[1].mentions == []

    _run(client.close())


def test_fetch_replies_watermark_excludes_seen() -> None:
    """Messages with id == since_id are excluded."""
    routes = {
        r"/api/v1/agent/chats/.*/messages$": (
            200,
            {
                "data": [
                    {"id": "old-msg", "content": "old", "sender_name": "a",
                     "sender_id": "x", "sender_type": "Agent",
                     "message_type": "text", "inserted_at": "2026-01-01T00:00:00Z"},
                    {"id": "new-msg", "content": "new", "sender_name": "b",
                     "sender_id": "y", "sender_type": "Agent",
                     "message_type": "text", "inserted_at": "2026-01-01T00:01:00Z"},
                ],
                "metadata": {"total_count": 2},
            },
        ),
    }
    client = _make_client(routes)
    replies = _run(client.fetch_replies(since_id="old-msg"))
    assert len(replies) == 1
    assert replies[0].message_id == "new-msg"
    _run(client.close())


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_post_message_422_raises_live_error() -> None:
    """Non-2xx responses raise BandLiveError."""
    routes = {
        r"/api/v1/agent/chats/.*/messages$": (
            422,
            {"error": {"code": "validation_error", "message": "bad request"}},
        ),
    }
    client = _make_client(routes)
    with pytest.raises(BandLiveError, match="422"):
        _run(
            client.post_message(
                BandOutboundMessage(sender="s", content="@x go", mentions=["x"])
            )
        )
    _run(client.close())


def test_fetch_replies_403_raises_live_error() -> None:
    """403 (forbidden) raises BandLiveError."""
    routes = {
        r"/api/v1/agent/chats/.*/messages$": (
            403,
            {"error": {"code": "forbidden", "message": "requires agent auth"}},
        ),
    }
    client = _make_client(routes)
    with pytest.raises(BandLiveError, match="403"):
        _run(client.fetch_replies())
    _run(client.close())


# ---------------------------------------------------------------------------
# band_poller.py — auth header & path
# ---------------------------------------------------------------------------


def test_band_poller_uses_x_api_key_and_api_v1_path() -> None:
    """BandPoller must use X-API-Key auth and /api/v1/ agent path."""
    from backend.app.services.band_poller import BandPoller

    captured: dict[str, httpx.Request] = {}

    async def capturing_handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200,
            content=json.dumps(
                {"data": [], "metadata": {"total_count": 0}}
            ).encode(),
            headers={"content-type": "application/json"},
            request=request,
        )

    poller = BandPoller(
        api_key="test-key",
        chat_id=CHAT_ID,
    )
    # Override the internal client with our mock
    transport = httpx.MockTransport(capturing_handler)
    poller._client = httpx.AsyncClient(  # noqa: SLF001
        transport=transport, base_url="https://app.band.ai"
    )

    _run(poller.fetch_messages())

    req = captured["request"]
    assert "/api/v1/agent/chats/" in req.url.path, "path must include /api/v1/agent/"
    assert req.headers.get("x-api-key") == "test-key"
    assert "Bearer" not in req.headers.get("authorization", "")
    _run(poller.close())
