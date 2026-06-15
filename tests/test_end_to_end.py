"""End-to-end integration test — the full ATC Guardian loop, offline.

Exercises the complete collaboration chain in one test so it can be
verified before submission:

  simulation tick -> detector (conflict/emergency/weather)
  -> band_poster @mentions specialist
  -> cascade through safety-reviewer -> coordinator
  -> coordinator creates a pending controller decision
  -> controller resolves it (APPROVED/REJECTED/MODIFIED)
  -> resolution logged to audit

No network, no Band credentials, no LLM. This is the test that proves
the demo works.
"""

import asyncio

from backend.app.services.advisory_ingester import AdvisoryIngester
from backend.app.services.audit_service import AuditService
from backend.app.services.band_poster import BandPoster
from backend.app.services.decision_service import DecisionService
from backend.app.services.sim_agents import (
    register_sim_agents,
    set_band_client,
    set_decision_service,
)
from data.generator import generate_radar_snapshot
from data.scenarios import (
    SCENARIO_SIGMETS,
    scenario_a_convergence,
    scenario_b_weather_deviation,
    scenario_c_emergency,
)
from shared.band_client import create_band_client


def _run(coro):
    """Run a coroutine in a fresh event loop."""
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeAudit:
    """Captures audit events for end-to-end assertions."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def log_event(self, **kwargs) -> int:
        self.events.append(kwargs)
        return len(self.events)


def _setup_stack() -> tuple:
    """Build the full offline stack: band client, poster, ingester, decisions.

    Returns:
        Tuple of (client, poster, ingester, decisions, audit).
    """
    client = create_band_client("sim")
    register_sim_agents(client)
    audit = _FakeAudit()
    decisions = DecisionService(audit=audit)  # type: ignore[arg-type]
    ingester = AdvisoryIngester(client, audit)  # type: ignore[arg-type]
    poster = BandPoster(client)
    set_decision_service(decisions)
    set_band_client(client)
    return client, poster, ingester, decisions, audit


def test_end_to_end_conflict_to_controller_approval() -> None:
    """SCN-A: conflict detected -> reviewer -> coordinator -> controller approves."""
    client, poster, ingester, decisions, audit = _setup_stack()

    # 1. Generate a snapshot with a conflict and feed it through the loop.
    snap = generate_radar_snapshot(scenario_a_convergence(), elapsed_seconds=0)
    assert snap.conflicts, "SCN-A must produce a conflict"
    _run(poster.process_snapshot(snap))

    # 2. Ingest agent replies into the audit log.
    ingested = _run(ingester.ingest_new(scenario_id="SCN-A"))
    assert ingested > 0

    # 3. The cascade reached the coordinator AND a pending decision exists.
    senders = {e["agent_name"] for e in audit.events}
    assert "conflict-detector" in senders
    assert "safety-reviewer" in senders
    assert "coordinator" in senders

    pending = decisions.list_pending()
    assert len(pending) == 1
    assert pending[0].advisory_kind == "conflict"
    assert pending[0].reviewer_verdict == "APPROVE"

    # 4. The controller approves the decision.
    resolved = _run(
        decisions.resolve(pending[0].decision_id, "APPROVED", controller_note="cleared")
    )
    assert resolved.status.value == "approved"

    # 5. The resolution is logged to audit.
    assert any(e["event_type"] == "decision_resolved" for e in audit.events)
    # No longer pending.
    assert decisions.list_pending() == []

    set_decision_service(None)
    set_band_client(None)


def test_end_to_end_emergency_cascade() -> None:
    """SCN-C: 7700 -> emergency-response -> ground-ops -> reviewer -> coordinator."""
    client, poster, ingester, decisions, audit = _setup_stack()

    snap = generate_radar_snapshot(scenario_c_emergency(), elapsed_seconds=0)
    assert snap.emergencies, "SCN-C must produce an emergency"
    _run(poster.process_snapshot(snap))
    _run(ingester.ingest_new(scenario_id="SCN-C"))

    senders = {e["agent_name"] for e in audit.events}
    assert "emergency-response" in senders
    assert "ground-ops" in senders
    assert "safety-reviewer" in senders
    assert "coordinator" in senders

    # A pending decision for the emergency resolution exists.
    pending = decisions.list_pending()
    assert len(pending) >= 1
    assert any(d.advisory_kind == "emergency" for d in pending)

    set_decision_service(None)
    set_band_client(None)


def test_end_to_end_weather_advisory() -> None:
    """SCN-B: SIGMET -> weather-analyst -> reviewer -> coordinator -> decision."""
    client, poster, ingester, decisions, audit = _setup_stack()

    snap = generate_radar_snapshot(
        scenario_b_weather_deviation(),
        elapsed_seconds=0,
        sigmets=SCENARIO_SIGMETS["SCN-B"],
    )
    _run(poster.process_snapshot(snap))
    _run(ingester.ingest_new(scenario_id="SCN-B"))

    senders = {e["agent_name"] for e in audit.events}
    assert "weather-analyst" in senders
    assert "safety-reviewer" in senders
    assert "coordinator" in senders

    set_decision_service(None)
    set_band_client(None)


def test_end_to_end_structured_events_present() -> None:
    """The audit trail includes structured thought/tool_call events."""
    client, poster, ingester, _, audit = _setup_stack()

    snap = generate_radar_snapshot(scenario_a_convergence(), elapsed_seconds=0)
    _run(poster.process_snapshot(snap))
    _run(ingester.ingest_new(scenario_id="SCN-A"))

    event_types = {e["event_type"] for e in audit.events}
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert "thought" in event_types

    set_decision_service(None)
    set_band_client(None)


def test_end_to_end_decision_rejection() -> None:
    """The controller can REJECT a proposal and it leaves the pending queue."""
    _, poster, _, decisions, _ = _setup_stack()

    snap = generate_radar_snapshot(scenario_a_convergence(), elapsed_seconds=0)
    _run(poster.process_snapshot(snap))

    pending = decisions.list_pending()
    assert len(pending) == 1
    resolved = _run(decisions.resolve(pending[0].decision_id, "REJECTED"))
    assert resolved.status.value == "rejected"
    assert decisions.list_pending() == []

    set_decision_service(None)
    set_band_client(None)
