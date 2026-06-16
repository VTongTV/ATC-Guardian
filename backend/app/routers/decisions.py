"""Decisions router — human-on-the-loop controller approval endpoints.

Exposes pending agent proposals and lets the controller resolve them
(APPROVE / REJECT / MODIFY). Nothing an agent recommends is marked
executed until the controller acts here.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.services.decision_service import DecisionNotFound, DecisionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/decisions", tags=["decisions"])

# Injected by main.py on application startup
_decision_service: DecisionService | None = None


def set_decision_service(service: DecisionService) -> None:
    """Register the decision service instance for this router.

    Called once during application lifespan startup.

    Args:
        service: The active DecisionService instance.
    """
    global _decision_service
    _decision_service = service


def _get_service() -> DecisionService:
    """Retrieve the decision service or raise 503 if not initialized.

    Returns:
        The active DecisionService.

    Raises:
        HTTPException: 503 if the service is not yet initialized.
    """
    if _decision_service is None:
        raise HTTPException(status_code=503, detail="Decision service not initialized")
    return _decision_service


class ResolveRequest(BaseModel):
    """Request body for resolving a pending decision."""

    action: str = Field(description="APPROVED | REJECTED | MODIFIED")
    controller_note: str | None = Field(default=None, description="Optional free-text note")


class ProposalRequest(BaseModel):
    """Request body for creating a new decision proposal."""

    scenario_id: str = Field(description="Active scenario id")
    advisory_kind: str = Field(description="conflict | weather | emergency")
    summary: str = Field(description="One-line UI description")
    agent_recommendation: str = Field(description="The specialist + reviewer recommendation")
    reviewer_verdict: str = Field(description="Safety Reviewer verdict (APPROVE/REJECT/MODIFY)")
    evidence: dict | None = Field(default=None, description="Optional structured evidence")


@router.get("/pending")
async def list_pending() -> list[dict]:
    """List all pending controller decisions, oldest first.

    Returns:
        A list of pending decision dicts (serialised for the UI).
    """
    service = _get_service()
    return [d.model_dump(mode="json") for d in service.list_pending()]


@router.post("/proposal")
async def create_proposal(body: ProposalRequest) -> dict:
    """Create a new pending decision proposal.

    Allows external agents (or test scripts) to submit proposals
    via REST, enabling both live-mode agents and the demo UI to
    populate the controller decisions panel.

    Args:
        body: Proposal fields matching DecisionService.create_proposal().

    Returns:
        The newly created pending decision.
    """
    service = _get_service()
    decision = await service.create_proposal(
        scenario_id=body.scenario_id,
        advisory_kind=body.advisory_kind,
        summary=body.summary,
        agent_recommendation=body.agent_recommendation,
        reviewer_verdict=body.reviewer_verdict,
        evidence=body.evidence,
    )
    return decision.model_dump(mode="json")


@router.post("/seed-demo")
async def seed_demo_decision() -> dict:
    """Create a demo pending decision for testing the UI.

    Returns:
        The created decision.
    """
    service = _get_service()
    decision = await service.create_proposal(
        scenario_id="SCN-A",
        advisory_kind="conflict",
        summary="Demo: UAL123/DAL456 CPA 2.3nm — vector trailing aircraft right 15°",
        agent_recommendation="Vector trailing aircraft right 15° to restore separation",
        reviewer_verdict="APPROVE",
        evidence={"cpa_nm": 2.3, "pair": "UAL123/DAL456"},
    )
    return decision.model_dump(mode="json")


@router.post("/{decision_id}/resolve")
async def resolve_decision(
    decision_id: str, body: ResolveRequest
) -> dict:
    """Resolve a pending decision with a controller action.

    Args:
        decision_id: The decision to resolve.
        body: The action (APPROVED/REJECTED/MODIFIED) and optional note.

    Returns:
        The resolved decision.

    Raises:
        HTTPException: 404 if the decision is not found or already resolved.
        HTTPException: 400 if the action is invalid.
    """
    service = _get_service()
    try:
        resolved = await service.resolve(
            decision_id=decision_id,
            action=body.action,
            controller_note=body.controller_note,
        )
    except DecisionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return resolved.model_dump(mode="json")
