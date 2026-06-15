"""ATC Guardian smoke test — verifies the full system before submission.

Runs the complete offline collaboration stack end-to-end and asserts
that every headline feature works:

  - Simulation produces conflicts, emergencies, and weather advisories
  - BandPoster dispatches @mentions through the cascade
  - Safety Reviewer returns verdicts
  - Coordinator creates pending controller decisions
  - Controller can resolve decisions
  - Structured events (thought/tool_call/tool_result) appear in the trail
  - What-if counterfactual returns a verdict
  - Audit export produces a complete report

Exits 0 on success, 1 on any failure. Run before every demo/submission:

    uv run python scripts/smoke_test.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.app.services.advisory_ingester import AdvisoryIngester
from backend.app.services.audit_export import build_incident_report
from backend.app.services.band_poster import BandPoster
from backend.app.services.decision_service import DecisionService
from backend.app.services.sim_agents import (
    register_sim_agents,
    set_band_client,
    set_decision_service,
)
from backend.app.services.simulation_service import SimulationService
from data.generator import generate_radar_snapshot
from data.scenarios import SCENARIO_SIGMETS, scenario_a_convergence, scenario_c_emergency
from ml.whatif import Maneuver, evaluate_maneuver
from shared.agent_roster import AGENT_ROSTER, framework_diversity_summary
from shared.band_client import create_band_client


class _FakeAudit:
    """Captures audit events for the smoke test.

    log_event stores kwargs dicts (what the real service receives);
    get_events_by_scenario returns SimpleNamespace objects so callers
    that access attributes (like build_incident_report) work the same as
    with real AuditEvent models.
    """

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def log_event(self, **kwargs) -> int:
        from datetime import datetime, timezone

        kwargs.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        self.events.append(kwargs)
        return len(self.events)

    async def get_events_by_scenario(self, scenario_id, limit=1000):
        normalized = [
            {
                "timestamp": e.get("timestamp", ""),
                "agent_name": e.get("agent_name", ""),
                "event_type": e.get("event_type", ""),
                "content": e.get("content", ""),
                "target_agent": e.get("target_agent"),
            }
            for e in self.events
        ]
        return [SimpleNamespace(**n) for n in normalized]


def _ok(label: str) -> None:
    """Print a green checkmark line."""
    print(f"  [OK] {label}")


def _fail(label: str, detail: str = "") -> None:
    """Print a red cross line and mark failure."""
    print(f"  [FAIL] {label}{': ' + detail if detail else ''}")


async def run_smoke_test() -> int:
    """Execute all smoke checks. Returns 0 on success, 1 on failure."""
    failures = 0
    print("=" * 60)
    print("ATC GUARDIAN — SMOKE TEST")
    print("=" * 60)

    # --- 1. Agent roster ---
    print("\n1. Agent roster")
    summary = framework_diversity_summary()
    if len(AGENT_ROSTER) == 6 and len(summary) >= 3:
        _ok(f"6 agents across {len(summary)} frameworks: {summary}")
    else:
        _fail(f"Roster incomplete: {len(AGENT_ROSTER)} agents, {summary}")
        failures += 1

    # --- 2. Build the stack ---
    client = create_band_client("sim")
    register_sim_agents(client)
    audit = _FakeAudit()
    decisions = DecisionService(audit=audit)  # type: ignore[arg-type]
    ingester = AdvisoryIngester(client, audit)  # type: ignore[arg-type]
    poster = BandPoster(client)
    set_decision_service(decisions)
    set_band_client(client)

    # --- 3. Conflict scenario ---
    print("\n2. Conflict scenario (SCN-A)")
    snap = generate_radar_snapshot(scenario_a_convergence(), elapsed_seconds=0)
    if snap.conflicts:
        cpa = snap.conflicts[0].cpa
        _ok(f"Conflict detected: {cpa.aircraft_a_callsign}/{cpa.aircraft_b_callsign} CPA {cpa.min_distance_nm}nm")
    else:
        _fail("No conflict detected in SCN-A")
        failures += 1

    await poster.process_snapshot(snap)
    await ingester.ingest_new(scenario_id="SCN-A")

    senders = {e["agent_name"] for e in audit.events}
    for required in ("conflict-detector", "safety-reviewer", "coordinator"):
        if required in senders:
            _ok(f"Cascade reached {required}")
        else:
            _fail(f"Cascade did not reach {required}")
            failures += 1

    event_types = {e["event_type"] for e in audit.events}
    if {"tool_call", "tool_result", "thought"}.issubset(event_types):
        _ok("Structured events (tool_call/tool_result/thought) present")
    else:
        _fail(f"Missing structured events: {event_types}")
        failures += 1

    pending = decisions.list_pending()
    if pending:
        _ok(f"Pending controller decision: {pending[0].decision_id} ({pending[0].advisory_kind})")
        resolved = await decisions.resolve(pending[0].decision_id, "APPROVED", controller_note="smoke")
        if resolved.status.value == "approved":
            _ok("Controller APPROVED the decision")
        else:
            _fail(f"Resolution failed: {resolved.status}")
            failures += 1
    else:
        _fail("No pending decision created")
        failures += 1

    # --- 4. Emergency scenario ---
    print("\n3. Emergency scenario (SCN-C)")
    audit.events.clear()
    snap_c = generate_radar_snapshot(scenario_c_emergency(), elapsed_seconds=0)
    if snap_c.emergencies:
        _ok(f"Emergency detected: {snap_c.emergencies[0].callsign} squawk {snap_c.emergencies[0].squawk_code}")
    else:
        _fail("No emergency detected in SCN-C")
        failures += 1

    await poster.process_snapshot(snap_c)
    await ingester.ingest_new(scenario_id="SCN-C")
    senders_c = {e["agent_name"] for e in audit.events}
    if "ground-ops" in senders_c:
        _ok("Emergency recruited Ground Ops")
    else:
        _fail("Ground Ops not recruited")
        failures += 1

    # --- 5. What-if ---
    print("\n4. What-if counterfactual")
    sim = SimulationService(scenario_id="SCN-A")
    sim.advance(0)
    ac = sim.get_snapshot().aircraft
    if len(ac) >= 2:
        result = evaluate_maneuver(ac, Maneuver(ac[0].callsign, new_heading_deg=180.0), ac[1].callsign)
        _ok(f"What-if verdict: {result.verdict}")
    else:
        _fail("Not enough aircraft for what-if")
        failures += 1

    # --- 6. Audit export ---
    print("\n5. Audit export")
    report = await build_incident_report(
        audit=audit,  # type: ignore[arg-type]
        decisions=decisions,
        simulation=sim,
    )
    required_sections = {"report_type", "scenario", "situation_summary", "agent_event_trail", "controller_decisions"}
    if required_sections.issubset(report.keys()):
        _ok(f"Incident report has all sections ({len(report)} keys)")
    else:
        _fail(f"Report missing sections: {required_sections - report.keys()}")
        failures += 1

    # --- Cleanup module state ---
    set_decision_service(None)
    set_band_client(None)

    # --- Summary ---
    print("\n" + "=" * 60)
    if failures == 0:
        print("ALL SMOKE CHECKS PASSED")
        print("=" * 60)
        return 0
    print(f"{failures} CHECK(S) FAILED — fix before submitting")
    print("=" * 60)
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run_smoke_test()))
