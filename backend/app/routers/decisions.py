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


@router.get("/pending")
async def list_pending() -> list[dict]:
    """List all pending controller decisions, oldest first.

    Returns:
        A list of pending decision dicts (serialised for the UI).
    """
    service = _get_service()
    return [d.model_dump(mode="json") for d in service.list_pending()]


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
