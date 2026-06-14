"""Decision service — pending controller decisions (human-on-the-loop).

Holds the proposals that agents surface for controller approval. Each
proposal starts PENDING; the controller resolves it to APPROVED,
REJECTED, or MODIFIED via the REST endpoint. Resolution is logged to
the audit service for the compliance trail.

This is the 'AI-assisted, human-decided' layer: agents detect, review,
and recommend, but the controller holds the only authority to execute.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from backend.app.services.audit_service import AuditService
from shared.models import ControllerDecision, DecisionStatus

logger = logging.getLogger(__name__)


class DecisionNotFound(Exception):
    """Raised when a decision id does not exist or is already resolved."""


class DecisionService:
    """In-memory store of pending controller decisions.

    The store is intentionally in-memory: proposals are transient (they
    exist only while awaiting a controller action). Resolved decisions
    are logged to the persistent audit service and then dropped from the
    pending set.

    Attributes:
        _pending: Maps decision_id -> ControllerDecision for pending items.
        _audit: Optional audit service to log resolutions into.
    """

    def __init__(self, audit: AuditService | None = None) -> None:
        """Initialise an empty decision store.

        Args:
            audit: Optional audit service. When provided, every created
                proposal and every resolution is logged.
        """
        self._pending: dict[str, ControllerDecision] = {}
        self._audit = audit

    async def create_proposal(
        self,
        scenario_id: str,
        advisory_kind: str,
        summary: str,
        agent_recommendation: str,
        reviewer_verdict: str,
        evidence: dict | None = None,
    ) -> ControllerDecision:
        """Create a new pending decision and log its creation.

        Args:
            scenario_id: Active scenario id.
            advisory_kind: conflict | weather | emergency.
            summary: One-line UI description.
            agent_recommendation: The specialist + reviewer recommendation.
            reviewer_verdict: Safety Reviewer verdict (APPROVE/REJECT/MODIFY).
            evidence: Optional structured evidence.

        Returns:
            The newly created, PENDING ControllerDecision.
        """
        decision = ControllerDecision(
            decision_id=f"DEC-{uuid.uuid4().hex[:8]}",
            created_at=datetime.now(timezone.utc),
            status=DecisionStatus.PENDING,
            scenario_id=scenario_id,
            advisory_kind=advisory_kind,
            summary=summary,
            agent_recommendation=agent_recommendation,
            reviewer_verdict=reviewer_verdict,
            evidence=evidence or {},
        )
        self._pending[decision.decision_id] = decision
        logger.info("Created pending decision %s: %s", decision.decision_id, summary)

        if self._audit is not None:
            await self._audit.log_event(
                agent_name="coordinator",
                event_type="decision_proposed",
                content=f"Proposal {decision.decision_id}: {summary}",
                metadata={
                    "decision_id": decision.decision_id,
                    "advisory_kind": advisory_kind,
                    "agent_recommendation": agent_recommendation,
                    "reviewer_verdict": reviewer_verdict,
                    "evidence": evidence or {},
                },
                scenario_id=scenario_id,
            )
        return decision

    def list_pending(self) -> list[ControllerDecision]:
        """Return all pending decisions, oldest first.

        Returns:
            List of ControllerDecision with status PENDING.
        """
        return sorted(
            (d for d in self._pending.values() if d.status == DecisionStatus.PENDING),
            key=lambda d: d.created_at,
        )

    def get(self, decision_id: str) -> ControllerDecision:
        """Fetch a decision by id.

        Args:
            decision_id: The decision identifier.

        Returns:
            The ControllerDecision.

        Raises:
            DecisionNotFound: If no such decision exists.
        """
        decision = self._pending.get(decision_id)
        if decision is None:
            raise DecisionNotFound(f"Decision {decision_id} not found")
        return decision

    async def resolve(
        self,
        decision_id: str,
        action: str,
        controller_note: str | None = None,
    ) -> ControllerDecision:
        """Resolve a pending decision with a controller action.

        Args:
            decision_id: The decision to resolve.
            action: APPROVED | REJECTED | MODIFIED.
            controller_note: Optional free-text note.

        Returns:
            The resolved ControllerDecision (frozen copy updated).

        Raises:
            DecisionNotFound: If the decision does not exist or is already resolved.
            ValueError: If action is not one of the allowed values.
        """
        action_upper = action.upper()
        if action_upper not in {"APPROVED", "REJECTED", "MODIFIED"}:
            raise ValueError(
                f"Invalid action '{action}'. Must be APPROVED, REJECTED, or MODIFIED."
            )

        decision = self._pending.get(decision_id)
        if decision is None or decision.status != DecisionStatus.PENDING:
            raise DecisionNotFound(
                f"Decision {decision_id} not found or already resolved"
            )

        resolved = decision.model_copy(
            update={
                "status": DecisionStatus(action_upper.lower()),
                "controller_action": action_upper,
                "controller_note": controller_note,
                "resolved_at": datetime.now(timezone.utc),
            }
        )
        self._pending[decision_id] = resolved
        logger.info(
            "Decision %s resolved: %s", decision_id, action_upper
        )

        if self._audit is not None:
            await self._audit.log_event(
                agent_name="controller",
                event_type="decision_resolved",
                content=f"Decision {decision_id} {action_upper}: {decision.summary}",
                metadata={
                    "decision_id": decision_id,
                    "action": action_upper,
                    "controller_note": controller_note,
                    "agent_recommendation": decision.agent_recommendation,
                },
                scenario_id=decision.scenario_id,
            )

        # Drop resolved decisions from the pending set after a short
        # retention so the UI can show the most recent outcome.
        return resolved

    def reset(self) -> None:
        """Clear all decisions (e.g. on scenario change)."""
        self._pending.clear()
