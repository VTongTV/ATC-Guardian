"""What-if router — counterfactual CPA evaluation endpoint.

Lets the controller propose a maneuver and see the predicted separation
outcome before acting. Pure math (no LLM); the agents present this as
decision support. A genuine novelty: no competitor does predictive
multi-agent collaboration.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.services.simulation_service import SimulationService
from ml.whatif import Maneuver, evaluate_maneuver

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatif", tags=["whatif"])

# Injected by main.py on application startup
_simulation_service: SimulationService | None = None


def set_simulation_service(service: SimulationService) -> None:
    """Register the simulation service for aircraft lookups.

    Args:
        service: The active SimulationService instance.
    """
    global _simulation_service
    _simulation_service = service


class WhatIfRequest(BaseModel):
    """Request body for a counterfactual maneuver evaluation."""

    callsign: str = Field(description="Aircraft to maneuver")
    partner_callsign: str = Field(description="The other aircraft in the pair")
    new_heading_deg: float | None = Field(default=None, description="Proposed heading")
    new_altitude_ft: int | None = Field(default=None, description="Proposed altitude")
    new_speed_kts: float | None = Field(default=None, description="Proposed speed")


def _get_service() -> SimulationService:
    """Retrieve the simulation service or raise 503.

    Returns:
        The active SimulationService.

    Raises:
        HTTPException: 503 if not initialised.
    """
    if _simulation_service is None:
        raise HTTPException(status_code=503, detail="Simulation service not initialized")
    return _simulation_service


@router.post("/maneuver")
async def evaluate_maneuver_endpoint(body: WhatIfRequest) -> dict:
    """Evaluate a proposed maneuver's impact on CPA.

    Args:
        body: The maneuver and the partner aircraft.

    Returns:
        A dict with baseline vs predicted CPA, delta, and a verdict.

    Raises:
        HTTPException: 404 if either aircraft is not found.
    """
    service = _get_service()
    snapshot = service.get_snapshot()

    maneuver = Maneuver(
        callsign=body.callsign,
        new_heading_deg=body.new_heading_deg,
        new_altitude_ft=body.new_altitude_ft,
        new_speed_kts=body.new_speed_kts,
    )

    try:
        result = evaluate_maneuver(snapshot.aircraft, maneuver, body.partner_callsign)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "maneuver": {
            "callsign": result.maneuver.callsign,
            "new_heading_deg": result.maneuver.new_heading_deg,
            "new_altitude_ft": result.maneuver.new_altitude_ft,
            "new_speed_kts": result.maneuver.new_speed_kts,
        },
        "pair": list(result.pair),
        "baseline_cpa_nm": result.baseline_cpa_nm,
        "predicted_cpa_nm": result.predicted_cpa_nm,
        "baseline_is_conflict": result.baseline_is_conflict,
        "predicted_is_conflict": result.predicted_is_conflict,
        "delta_nm": result.delta_nm,
        "verdict": result.verdict,
    }
