"""Tests for the audit export incident-report builder and endpoint."""

import asyncio

from fastapi.testclient import TestClient

from backend.app.services.audit_export import build_incident_report
from backend.app.services.decision_service import DecisionService
from backend.app.services.simulation_service import SimulationService


def _run(coro):
    """Run a coroutine in a fresh event loop."""
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeAudit:
    """Minimal audit stand-in returning canned scenario events."""

    def __init__(self) -> None:
        self.events: list = []

    async def get_events_by_scenario(self, scenario_id, limit=1000):
        return self.events


class _FakeDecisions:
    """Minimal decision service stand-in."""

    def list_pending(self):
        return []


def test_incident_report_has_required_sections() -> None:
    """The exported report contains all regulator-required sections."""
    audit = _FakeAudit()
    decisions = DecisionService()
    sim = SimulationService(scenario_id="SCN-A")

    report = _run(
        build_incident_report(audit=audit, decisions=decisions, simulation=sim)  # type: ignore[arg-type]
    )

    assert report["report_type"] == "ATC_GUARDIAN_INCIDENT_REPORT"
    assert "generated_at" in report
    assert report["scenario"]["scenario_id"] == "SCN-A"
    assert "situation_summary" in report
    assert "callsigns_tracked" in report
    assert "conflicts" in report
    assert "emergencies" in report
    assert "weather_advisories" in report
    assert "agent_event_trail" in report
    assert "controller_decisions" in report


def test_incident_report_summarises_situation() -> None:
    """The situation summary counts aircraft and advisories correctly."""
    audit = _FakeAudit()
    decisions = DecisionService()
    sim = SimulationService(scenario_id="SCN-C")
    # Advance to populate snapshots
    sim.advance(0)

    report = _run(
        build_incident_report(audit=audit, decisions=decisions, simulation=sim)  # type: ignore[arg-type]
    )

    summary = report["situation_summary"]
    assert summary["aircraft_count"] == len(sim.get_snapshot().aircraft)
    assert summary["active_emergencies"] >= 1  # SCN-C has SWA770 squawking 7700


def test_export_endpoint_returns_report() -> None:
    """GET /audit/export returns the incident report via the router."""
    from fastapi import FastAPI

    from backend.app.routers import audit as audit_router

    app = FastAPI()
    audit = _FakeAudit()
    decisions = DecisionService()
    sim = SimulationService(scenario_id="SCN-A")
    audit_router.set_audit_service(audit)  # type: ignore[arg-type]
    audit_router.set_decision_service_for_export(decisions)
    audit_router.set_simulation_service_for_export(sim)
    app.include_router(audit_router.router)
    client = TestClient(app)

    response = client.get("/audit/export")
    assert response.status_code == 200
    body = response.json()
    assert body["report_type"] == "ATC_GUARDIAN_INCIDENT_REPORT"


def test_export_endpoint_filters_by_scenario() -> None:
    """GET /audit/export?scenario_id=SCN-C reports the emergency scenario."""
    from fastapi import FastAPI

    from backend.app.routers import audit as audit_router

    app = FastAPI()
    audit = _FakeAudit()
    decisions = DecisionService()
    sim = SimulationService(scenario_id="SCN-A")
    audit_router.set_audit_service(audit)  # type: ignore[arg-type]
    audit_router.set_decision_service_for_export(decisions)
    audit_router.set_simulation_service_for_export(sim)
    app.include_router(audit_router.router)
    client = TestClient(app)

    response = client.get("/audit/export?scenario_id=SCN-C")
    assert response.status_code == 200
    assert response.json()["scenario"]["scenario_id"] == "SCN-C"
