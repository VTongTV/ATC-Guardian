"""Tests for the human-on-the-loop DecisionService and router.

Verifies that pending proposals are created from agent verdicts,
resolved by controller actions, and that resolutions are logged to the
audit service. Uses an in-memory fake audit; no network.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from backend.app.routers import decisions as decisions_router
from backend.app.services.decision_service import (
    DecisionNotFound,
    DecisionService,
)
from backend.app.services.sim_agents import set_decision_service
from shared.models import DecisionStatus


def _run(coro):
    """Run a coroutine in a fresh event loop."""
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeAudit:
    """Captures audit log_event calls for assertions."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def log_event(self, **kwargs) -> int:
        self.events.append(kwargs)
        return len(self.events)


# ---------------------------------------------------------------------------
# DecisionService
# ---------------------------------------------------------------------------


class TestDecisionService:
    """Tests for the DecisionService core."""

    def test_create_proposal_starts_pending(self) -> None:
        """A new proposal is PENDING until the controller acts."""
        audit = _FakeAudit()
        svc = DecisionService(audit=audit)  # type: ignore[arg-type]
        decision = _run(
            svc.create_proposal(
                scenario_id="SCN-A",
                advisory_kind="conflict",
                summary="UAL123/DAL456 CPA 4.8nm",
                agent_recommendation="vector UAL123 right 15",
                reviewer_verdict="APPROVE",
                evidence={"cpa_nm": 4.8},
            )
        )
        assert decision.status == DecisionStatus.PENDING
        assert decision.reviewer_verdict == "APPROVE"
        assert decision.evidence == {"cpa_nm": 4.8}
        # Creation logged to audit
        assert any(e["event_type"] == "decision_proposed" for e in audit.events)

    def test_list_pending_returns_only_pending(self) -> None:
        """list_pending excludes resolved decisions."""
        svc = DecisionService()
        d = _run(
            svc.create_proposal(
                scenario_id="SCN-A",
                advisory_kind="conflict",
                summary="x",
                agent_recommendation="y",
                reviewer_verdict="APPROVE",
            )
        )
        assert len(svc.list_pending()) == 1
        _run(svc.resolve(d.decision_id, "APPROVED"))
        assert svc.list_pending() == []

    def test_resolve_approved_sets_status_and_logs(self) -> None:
        """Resolving APPROVED updates status and logs to audit."""
        audit = _FakeAudit()
        svc = DecisionService(audit=audit)  # type: ignore[arg-type]
        d = _run(
            svc.create_proposal(
                scenario_id="SCN-C",
                advisory_kind="emergency",
                summary="SWA770 squawk 7700",
                agent_recommendation="descend FL100",
                reviewer_verdict="APPROVE",
            )
        )
        resolved = _run(svc.resolve(d.decision_id, "APPROVED", controller_note="ok"))
        assert resolved.status == DecisionStatus.APPROVED
        assert resolved.controller_action == "APPROVED"
        assert resolved.controller_note == "ok"
        assert resolved.resolved_at is not None
        assert any(e["event_type"] == "decision_resolved" for e in audit.events)

    def test_resolve_rejected_and_modified_actions(self) -> None:
        """All three actions are accepted and set the right status."""
        for action, status in [
            ("REJECTED", DecisionStatus.REJECTED),
            ("MODIFIED", DecisionStatus.MODIFIED),
            ("APPROVED", DecisionStatus.APPROVED),
        ]:
            svc = DecisionService()
            d = _run(
                svc.create_proposal(
                    scenario_id="SCN-A",
                    advisory_kind="conflict",
                    summary="x",
                    agent_recommendation="y",
                    reviewer_verdict="APPROVE",
                )
            )
            resolved = _run(svc.resolve(d.decision_id, action))
            assert resolved.status == status

    def test_resolve_unknown_decision_raises(self) -> None:
        """Resolving a non-existent id raises DecisionNotFound."""
        svc = DecisionService()
        with pytest.raises(DecisionNotFound):
            _run(svc.resolve("DEC-nope", "APPROVED"))

    def test_resolve_already_resolved_raises(self) -> None:
        """Resolving an already-resolved decision raises."""
        svc = DecisionService()
        d = _run(
            svc.create_proposal(
                scenario_id="SCN-A",
                advisory_kind="conflict",
                summary="x",
                agent_recommendation="y",
                reviewer_verdict="APPROVE",
            )
        )
        _run(svc.resolve(d.decision_id, "APPROVED"))
        with pytest.raises(DecisionNotFound):
            _run(svc.resolve(d.decision_id, "REJECTED"))

    def test_invalid_action_raises_value_error(self) -> None:
        """An invalid action string raises ValueError."""
        svc = DecisionService()
        d = _run(
            svc.create_proposal(
                scenario_id="SCN-A",
                advisory_kind="conflict",
                summary="x",
                agent_recommendation="y",
                reviewer_verdict="APPROVE",
            )
        )
        with pytest.raises(ValueError):
            _run(svc.resolve(d.decision_id, "MAYBE"))

    def test_reset_clears_all(self) -> None:
        """reset() empties the pending store."""
        svc = DecisionService()
        _run(
            svc.create_proposal(
                scenario_id="SCN-A",
                advisory_kind="conflict",
                summary="x",
                agent_recommendation="y",
                reviewer_verdict="APPROVE",
            )
        )
        svc.reset()
        assert svc.list_pending() == []


# ---------------------------------------------------------------------------
# Coordinator creates proposals via the injected service
# ---------------------------------------------------------------------------


class TestCoordinatorCreatesProposal:
    """Tests that the coordinator sim handler creates controller decisions."""

    def test_coordinator_creates_pending_decision_for_approved_verdict(self) -> None:
        """When the reviewer APPROVES, the coordinator surfaces a decision."""
        from backend.app.services.sim_agents import coordinator_handler
        from shared.band_client import BandOutboundMessage

        audit = _FakeAudit()
        svc = DecisionService(audit=audit)  # type: ignore[arg-type]
        set_decision_service(svc)

        inbound = BandOutboundMessage(
            sender="safety-reviewer",
            content="@coordinator VERDICT: APPROVE",
            mentions=["coordinator"],
            metadata={
                "kind": "safety_verdict",
                "summary": "APPROVE: Conflict UAL123/DAL456",
                "verdict": "APPROVE",
                "recommendation": "vector UAL123 right 15 degrees",
                "callsign": "UAL123",
            },
            correlation_id="ADV-1",
        )
        _run(coordinator_handler(inbound))

        pending = svc.list_pending()
        assert len(pending) == 1
        assert pending[0].agent_recommendation == "vector UAL123 right 15 degrees"
        assert pending[0].advisory_kind == "conflict"

        # Clean up module state
        set_decision_service(None)

    def test_coordinator_skips_decision_when_reviewer_rejects(self) -> None:
        """A REJECTED verdict does not create a controller decision."""
        from backend.app.services.sim_agents import coordinator_handler
        from shared.band_client import BandOutboundMessage

        svc = DecisionService()
        set_decision_service(svc)

        inbound = BandOutboundMessage(
            sender="safety-reviewer",
            content="@coordinator VERDICT: REJECT",
            mentions=["coordinator"],
            metadata={
                "kind": "safety_verdict",
                "summary": "REJECT: stale data",
                "verdict": "REJECT",
            },
        )
        _run(coordinator_handler(inbound))
        assert svc.list_pending() == []
        set_decision_service(None)


# ---------------------------------------------------------------------------
# Router (via TestClient on a minimal app)
# ---------------------------------------------------------------------------


class TestDecisionsRouter:
    """End-to-end router tests using FastAPI TestClient."""

    @pytest.fixture
    def client_and_service(self):
        """Build a minimal FastAPI app with the decisions router wired."""
        from fastapi import FastAPI

        app = FastAPI()
        svc = DecisionService()
        decisions_router.set_decision_service(svc)
        app.include_router(decisions_router.router)
        return TestClient(app), svc

    def test_pending_returns_empty_initially(self, client_and_service) -> None:
        """GET /decisions/pending returns [] when nothing is pending."""
        client, _ = client_and_service
        response = client.get("/decisions/pending")
        assert response.status_code == 200
        assert response.json() == []

    def test_resolve_returns_404_for_unknown(self, client_and_service) -> None:
        """POST resolve on an unknown id returns 404."""
        client, _ = client_and_service
        response = client.post(
            "/decisions/DEC-nope/resolve", json={"action": "APPROVED"}
        )
        assert response.status_code == 404

    def test_resolve_returns_400_for_invalid_action(self, client_and_service) -> None:
        """POST resolve with an invalid action returns 400."""
        client, svc = client_and_service
        d = _run(
            svc.create_proposal(
                scenario_id="SCN-A",
                advisory_kind="conflict",
                summary="x",
                agent_recommendation="y",
                reviewer_verdict="APPROVE",
            )
        )
        response = client.post(
            f"/decisions/{d.decision_id}/resolve", json={"action": "MAYBE"}
        )
        assert response.status_code == 400

    def test_full_resolve_flow(self, client_and_service) -> None:
        """Create a proposal, then resolve it via the endpoint."""
        client, svc = client_and_service
        d = _run(
            svc.create_proposal(
                scenario_id="SCN-A",
                advisory_kind="conflict",
                summary="UAL123/DAL456 CPA 4.8nm",
                agent_recommendation="vector UAL123 right 15",
                reviewer_verdict="APPROVE",
            )
        )
        # Pending list shows it
        pending = client.get("/decisions/pending").json()
        assert len(pending) == 1

        # Resolve it
        response = client.post(
            f"/decisions/{d.decision_id}/resolve",
            json={"action": "APPROVED", "controller_note": "cleared"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "approved"
        assert body["controller_note"] == "cleared"

        # No longer pending
        assert client.get("/decisions/pending").json() == []
