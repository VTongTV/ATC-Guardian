"""Unit tests for the BandClient abstraction (shared/band_client.py).

Verifies that the offline simulation transport routes @mentions to
registered handlers, buffers replies, honours the watermark on
fetch_replies, and that the factory rejects invalid modes. No network
and no LLM calls are made.

These tests use synchronous wrappers around the async API
(``asyncio.run``) so the project needs no extra pytest plugins.
"""

import asyncio

import pytest

from shared.band_client import (
    LIVE_BAND_BASE_URL,
    BandInboundMessage,
    BandOutboundMessage,
    LiveBandClient,
    SimulatedBandClient,
    create_band_client,
)


def _run(coro):
    """Run a coroutine to completion in a fresh event loop.

    Args:
        coro: The awaitable to execute.

    Returns:
        Whatever the coroutine returns.
    """
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# SimulatedBandClient
# ---------------------------------------------------------------------------


def test_simulated_client_reports_sim_mode() -> None:
    """mode property returns 'sim'."""
    client = SimulatedBandClient()
    assert client.mode == "sim"
    _run(client.close())


def test_post_message_echoes_into_room() -> None:
    """A posted message is echoed back via fetch_replies."""
    client = SimulatedBandClient()
    msg = BandOutboundMessage(
        sender="system-ingest",
        content="hello @conflict-detector",
        mentions=["conflict-detector"],
    )
    msg_id = _run(client.post_message(msg))
    assert msg_id.startswith("sim-")

    replies = _run(client.fetch_replies())
    assert len(replies) == 1
    assert replies[0].sender == "system-ingest"
    assert replies[0].content == "hello @conflict-detector"
    _run(client.close())


def test_post_message_dispatches_to_registered_handler() -> None:
    """A mentioned agent with a registered handler receives the message."""

    received: list[BandOutboundMessage] = []

    async def handler(inbound: BandOutboundMessage) -> list[BandInboundMessage]:
        received.append(inbound)
        return [
            BandInboundMessage(
                message_id="reply",
                timestamp="2026-01-01T00:00:00Z",
                sender="conflict-detector",
                content="CONFLICT: UAL123 / DAL456 CPA 3.1nm",
            )
        ]

    client = SimulatedBandClient()
    client.register_agent("conflict-detector", handler)

    msg = BandOutboundMessage(
        sender="system-ingest",
        content="@conflict-detector analyze UAL123 vs DAL456",
        mentions=["conflict-detector"],
    )
    _run(client.post_message(msg))

    assert len(received) == 1
    assert received[0].mentions == ["conflict-detector"]

    # Echo + reply are both in the buffer
    replies = _run(client.fetch_replies())
    assert len(replies) == 2
    senders = [r.sender for r in replies]
    assert "system-ingest" in senders
    assert "conflict-detector" in senders
    _run(client.close())


def test_unregistered_mention_is_silently_skipped() -> None:
    """Mentioning an agent with no handler does not raise."""
    client = SimulatedBandClient()
    msg = BandOutboundMessage(
        sender="system-ingest",
        content="@nobody-home do something",
        mentions=["nobody-home"],
    )
    msg_id = _run(client.post_message(msg))
    assert msg_id.startswith("sim-")
    # Only the echo is buffered
    replies = _run(client.fetch_replies())
    assert len(replies) == 1
    _run(client.close())


def test_handler_exception_is_caught_not_propagated() -> None:
    """A handler that raises must not break the post."""

    async def bad_handler(inbound: BandOutboundMessage) -> list[BandInboundMessage]:
        raise RuntimeError("boom")

    client = SimulatedBandClient()
    client.register_agent("bad-agent", bad_handler)
    msg = BandOutboundMessage(
        sender="system-ingest",
        content="@bad-agent go",
        mentions=["bad-agent"],
    )
    # Must not raise
    _run(client.post_message(msg))
    _run(client.close())


def test_fetch_replies_watermark() -> None:
    """since_id excludes messages at or below the watermark."""
    client = SimulatedBandClient()
    _run(
        client.post_message(
            BandOutboundMessage(sender="a", content="first", mentions=[])
        )
    )
    second_id = _run(
        client.post_message(
            BandOutboundMessage(sender="a", content="second", mentions=[])
        )
    )
    _run(
        client.post_message(
            BandOutboundMessage(sender="a", content="third", mentions=[])
        )
    )

    after_second = _run(client.fetch_replies(since_id=second_id))
    assert [r.content for r in after_second] == ["third"]
    _run(client.close())


def test_post_event_is_buffered_with_type() -> None:
    """Structured events are buffered with their event_type."""
    client = SimulatedBandClient()
    event_id = _run(
        client.post_event(
            agent="conflict-detector",
            event_type="tool_call",
            content="ran compute_cpa",
            metadata={"cpa_nm": 3.2},
        )
    )
    assert event_id.startswith("sim-")
    replies = _run(client.fetch_replies())
    assert len(replies) == 1
    assert replies[0].message_type == "tool_call"
    assert replies[0].sender == "conflict-detector"
    assert replies[0].metadata == {"cpa_nm": 3.2}
    _run(client.close())


def test_correlation_id_round_trips() -> None:
    """A correlation_id on the outbound message is preserved on the echo."""
    client = SimulatedBandClient()
    _run(
        client.post_message(
            BandOutboundMessage(
                sender="system-ingest",
                content="@x",
                mentions=["x"],
                correlation_id="req-42",
            )
        )
    )
    replies = _run(client.fetch_replies())
    assert replies[0].correlation_id == "req-42"
    _run(client.close())


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_factory_returns_sim_client_by_default() -> None:
    """create_band_client('sim') returns a SimulatedBandClient."""
    client = create_band_client("sim")
    assert isinstance(client, SimulatedBandClient)
    assert client.mode == "sim"


def test_factory_rejects_unknown_mode() -> None:
    """Unknown modes raise ValueError."""
    with pytest.raises(ValueError, match="BAND_MODE"):
        create_band_client("magic")


def test_factory_live_requires_credentials() -> None:
    """Live mode without credentials raises ValueError."""
    with pytest.raises(ValueError, match="BAND_MODE=live requires"):
        create_band_client("live", api_key=None, chat_id=None)


def test_factory_live_builds_live_client() -> None:
    """Live mode with credentials returns a LiveBandClient."""
    client = create_band_client("live", api_key="k", chat_id="room-1")
    assert isinstance(client, LiveBandClient)
    assert client.mode == "live"


def test_live_client_uses_default_base_url() -> None:
    """LiveBandClient defaults to the production Band base URL."""
    client = LiveBandClient(api_key="k", chat_id="room-1")
    assert client._base_url == LIVE_BAND_BASE_URL  # noqa: SLF001
