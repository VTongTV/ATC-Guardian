"""Integration tests for the Band collaboration loop.

Exercises BandPoster + AdvisoryIngester + SimulatedBandClient together
to confirm the full detect -> @mention -> agent reply -> audit log flow
works with zero credentials (BAND_MODE=sim). This is the loop that was
previously broken (agent outputs never reached the radar).
"""

import asyncio

from backend.app.services.advisory_ingester import AdvisoryIngester, _max_watermark
from backend.app.services.band_poster import BandPoster
from backend.app.services.sim_agents import SIM_AGENT_HANDLERS, register_sim_agents
from data.scenarios import (
    SCENARIO_SIGMETS,
    scenario_a_convergence,
    scenario_b_weather_deviation,
    scenario_c_emergency,
)
from data.generator import generate_radar_snapshot
from shared.band_client import SimulatedBandClient, create_band_client


def _run(coro):
    """Run a coroutine in a fresh event loop (no pytest-asyncio needed)."""
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Sim agent registry
# ---------------------------------------------------------------------------


def test_all_six_agents_have_sim_handlers() -> None:
    """Every required agent has a simulated handler registered."""
    expected = {
        "coordinator",
        "conflict-detector",
        "weather-analyst",
        "safety-reviewer",
        "emergency-response",
        "ground-ops",
    }
    assert set(SIM_AGENT_HANDLERS) == expected


def test_register_sim_agents_registers_all_handlers() -> None:
    """register_sim_agents wires every handler onto a SimulatedBandClient."""
    client = create_band_client("sim")
    register_sim_agents(client)
    # Internal registry mirrors SIM_AGENT_HANDLERS
    assert set(client._handlers) == set(SIM_AGENT_HANDLERS)  # noqa: SLF001


# ---------------------------------------------------------------------------
# BandPoster de-duplication
# ---------------------------------------------------------------------------


def test_poster_dispatches_conflict_once() -> None:
    """The same conflict is only dispatched on the first tick it appears."""
    client = create_band_client("sim")
    register_sim_agents(client)
    poster = BandPoster(client)

    scenario = scenario_a_convergence()
    snap = generate_radar_snapshot(scenario, elapsed_seconds=0)
    assert snap.conflicts, "scenario A should have a conflict at t=0"

    _run(poster.process_snapshot(snap))
    first_count = len(_run(client.fetch_replies()))

    # Second tick (same advisory ids) must not re-dispatch
    _run(poster.process_snapshot(snap))
    second_count = len(_run(client.fetch_replies()))

    assert second_count == first_count


def test_poster_reset_allows_redispatch() -> None:
    """After reset(), conditions dispatch again (e.g. on scenario change)."""
    client = create_band_client("sim")
    register_sim_agents(client)
    poster = BandPoster(client)

    scenario = scenario_a_convergence()
    snap = generate_radar_snapshot(scenario, elapsed_seconds=0)
    _run(poster.process_snapshot(snap))
    before = len(_run(client.fetch_replies()))

    poster.reset()
    _run(poster.process_snapshot(snap))
    after = len(_run(client.fetch_replies()))

    assert after > before


# ---------------------------------------------------------------------------
# Full loop per scenario
# ---------------------------------------------------------------------------


def test_conflict_scenario_triggers_detector_then_reviewer_then_coordinator() -> None:
    """SCN-A: conflict -> detector -> safety-reviewer -> coordinator."""
    client = create_band_client("sim")
    register_sim_agents(client)
    poster = BandPoster(client)

    snap = generate_radar_snapshot(scenario_a_convergence(), elapsed_seconds=0)
    _run(poster.process_snapshot(snap))

    messages = _run(client.fetch_replies())
    senders = [m.sender for m in messages]
    assert "system-ingest" in senders
    assert "conflict-detector" in senders
    assert "safety-reviewer" in senders
    assert "coordinator" in senders

    detector_reply = next(m for m in messages if m.sender == "conflict-detector")
    assert "CONFLICT ADVISORY" in detector_reply.content
    # Detector routes to the reviewer, not straight to coordinator
    assert "safety-reviewer" in detector_reply.mentions

    verdict = next(m for m in messages if m.sender == "safety-reviewer")
    assert "VERDICT" in verdict.content
    assert verdict.metadata["verdict"] in {"APPROVE", "REJECT", "MODIFY"}


def test_emergency_scenario_full_cascade() -> None:
    """SCN-C: emergency -> ER -> ground-ops -> ER -> reviewer -> coordinator."""
    client = create_band_client("sim")
    register_sim_agents(client)
    poster = BandPoster(client)

    snap = generate_radar_snapshot(scenario_c_emergency(), elapsed_seconds=0)
    _run(poster.process_snapshot(snap))

    messages = _run(client.fetch_replies())
    senders = [m.sender for m in messages]
    assert "emergency-response" in senders
    assert "ground-ops" in senders
    assert "safety-reviewer" in senders
    assert "coordinator" in senders

    er_reply = next(m for m in messages if m.sender == "emergency-response")
    assert "ground-ops" in er_reply.mentions


def test_weather_scenario_routes_through_reviewer() -> None:
    """SCN-B: weather analyst -> safety-reviewer -> coordinator."""
    client = create_band_client("sim")
    register_sim_agents(client)
    poster = BandPoster(client)

    snap = generate_radar_snapshot(
        scenario_b_weather_deviation(),
        elapsed_seconds=0,
        sigmets=SCENARIO_SIGMETS["SCN-B"],
    )
    _run(poster.process_snapshot(snap))

    messages = _run(client.fetch_replies())
    senders = [m.sender for m in messages]
    assert "weather-analyst" in senders
    assert "safety-reviewer" in senders

    wx_reply = next(m for m in messages if m.sender == "weather-analyst")
    assert "SIGM-001" in wx_reply.content or "SIGMET" in wx_reply.content
    assert "safety-reviewer" in wx_reply.mentions


# ---------------------------------------------------------------------------
# AdvisoryIngester
# ---------------------------------------------------------------------------


class _FakeAudit:
    """Minimal stand-in for AuditService capturing logged events."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def log_event(self, **kwargs) -> int:
        self.events.append(kwargs)
        return len(self.events)


def test_ingester_stores_replies_and_advances_watermark() -> None:
    """The ingester writes each reply to the audit log once."""
    client = create_band_client("sim")
    register_sim_agents(client)
    poster = BandPoster(client)
    audit = _FakeAudit()
    ingester = AdvisoryIngester(client, audit)  # type: ignore[arg-type]

    snap = generate_radar_snapshot(scenario_a_convergence(), elapsed_seconds=0)
    _run(poster.process_snapshot(snap))

    first = _run(ingester.ingest_new(scenario_id="SCN-A"))
    assert first > 0
    assert len(audit.events) == first
    # Every event tagged with the scenario
    assert all(e["scenario_id"] == "SCN-A" for e in audit.events)

    # Second ingest with no new messages returns 0
    second = _run(ingester.ingest_new(scenario_id="SCN-A"))
    assert second == 0


def test_max_watermark_picks_later_synthetic_id() -> None:
    """_max_watermark compares synthetic numeric suffixes correctly."""
    assert _max_watermark(None, "sim-3") == "sim-3"
    assert _max_watermark("sim-2", "sim-5") == "sim-5"
    assert _max_watermark("sim-9", "sim-1") == "sim-9"
