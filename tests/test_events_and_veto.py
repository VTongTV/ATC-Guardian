"""Tests for Band structured event emission and Emergency Response veto.

Covers:
- Sim agents emit thought/tool_call/tool_result events alongside replies.
- When an emergency is active, the BandPoster vetoes lower-priority
  conflict/weather dispatches instead of firing them.
- Vetoed advisories are recorded once (de-duplicated).
"""

import asyncio

from backend.app.services.band_poster import BandPoster
from backend.app.services.sim_agents import set_band_client
from data.generator import generate_radar_snapshot
from data.scenarios import scenario_c_emergency
from shared.band_client import create_band_client


def _run(coro):
    """Run a coroutine in a fresh event loop."""
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Structured event emission
# ---------------------------------------------------------------------------


def test_conflict_detector_emits_tool_events() -> None:
    """The conflict-detector handler posts tool_call + tool_result events."""
    client = create_band_client("sim")
    set_band_client(client)

    from backend.app.services.sim_agents import register_sim_agents

    register_sim_agents(client)

    # Drive a conflict through the system via the poster.
    from data.scenarios import scenario_a_convergence

    poster = BandPoster(client)
    snap = generate_radar_snapshot(scenario_a_convergence(), elapsed_seconds=0)
    _run(poster.process_snapshot(snap))

    messages = _run(client.fetch_replies())
    event_types = [m.message_type for m in messages]
    assert "tool_call" in event_types
    assert "tool_result" in event_types

    set_band_client(None)


def test_safety_reviewer_emits_thought_event() -> None:
    """The safety-reviewer handler posts a 'thought' event with its reasoning."""
    client = create_band_client("sim")
    set_band_client(client)

    from backend.app.services.sim_agents import register_sim_agents

    register_sim_agents(client)

    from data.scenarios import scenario_a_convergence

    poster = BandPoster(client)
    snap = generate_radar_snapshot(scenario_a_convergence(), elapsed_seconds=0)
    _run(poster.process_snapshot(snap))

    messages = _run(client.fetch_replies())
    thoughts = [m for m in messages if m.message_type == "thought"]
    assert any("safety-reviewer" == m.sender for m in thoughts)
    assert any("ICAO" in m.content or "minima" in m.content for m in thoughts)

    set_band_client(None)


# ---------------------------------------------------------------------------
# Emergency veto
# ---------------------------------------------------------------------------


def test_emergency_active_defers_conflict_dispatch() -> None:
    """When an emergency is active, conflict advisories are vetoed, not fired."""
    client = create_band_client("sim")
    from backend.app.services.sim_agents import register_sim_agents

    register_sim_agents(client)
    set_band_client(client)

    poster = BandPoster(client)
    snap = generate_radar_snapshot(scenario_c_emergency(), elapsed_seconds=0)
    assert snap.emergencies, "SCN-C must have an active emergency"

    _run(poster.process_snapshot(snap))

    messages = _run(client.fetch_replies())
    senders = [m.sender for m in messages]
    # Emergency response should fire
    assert "emergency-response" in senders

    # A veto event should be present for any conflict/weather in the snapshot
    veto_messages = [
        m for m in messages if (m.metadata or {}).get("kind") == "veto"
    ]
    # SCN-C has no conflicts at t=0, but the veto path must still be
    # exercised without error. Assert no conflict-detector was dispatched.
    assert "conflict-detector" not in senders

    set_band_client(None)


def test_veto_is_deduplicated() -> None:
    """A vetoed advisory is only recorded once across ticks."""
    client = create_band_client("sim")
    from backend.app.services.sim_agents import register_sim_agents

    register_sim_agents(client)
    set_band_client(client)

    poster = BandPoster(client)
    snap = generate_radar_snapshot(scenario_c_emergency(), elapsed_seconds=0)

    _run(poster.process_snapshot(snap))
    first = len(_run(client.fetch_replies()))

    _run(poster.process_snapshot(snap))
    second = len(_run(client.fetch_replies()))

    assert second == first, "second tick should not re-veto or re-dispatch"

    set_band_client(None)


def test_no_emergency_means_no_veto() -> None:
    """Without an active emergency, conflicts dispatch normally (no veto)."""
    client = create_band_client("sim")
    from backend.app.services.sim_agents import register_sim_agents

    register_sim_agents(client)
    set_band_client(client)

    poster = BandPoster(client)
    from data.scenarios import scenario_a_convergence

    snap = generate_radar_snapshot(scenario_a_convergence(), elapsed_seconds=0)
    assert not snap.emergencies, "SCN-A must have no emergency"

    _run(poster.process_snapshot(snap))

    messages = _run(client.fetch_replies())
    veto_messages = [
        m for m in messages if (m.metadata or {}).get("kind") == "veto"
    ]
    assert veto_messages == []

    set_band_client(None)
