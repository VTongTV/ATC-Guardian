"""Data router — endpoints for simulated and live aircraft data.

Provides the /data/simulated endpoint that the frontend radar
display polls for the current aircraft state snapshot.
"""

import logging

from fastapi import APIRouter, HTTPException

from backend.app.services.simulation_service import SimulationService
from shared.models import RadarSnapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data", tags=["data"])

# Injected by main.py on application startup
_simulation_service: SimulationService | None = None


def set_simulation_service(service: SimulationService) -> None:
    """Register the simulation service instance for this router.

    Called once during application lifespan startup.

    Args:
        service: The active SimulationService instance.
    """
    global _simulation_service
    _simulation_service = service


def _get_service() -> SimulationService:
    """Retrieve the simulation service or raise 503 if not initialized.

    Returns:
        The active SimulationService.

    Raises:
        HTTPException: 503 if the service is not yet initialized.
    """
    if _simulation_service is None:
        raise HTTPException(status_code=503, detail="Simulation service not initialized")
    return _simulation_service


@router.get("/simulated", response_model=RadarSnapshot)
async def get_simulated_data() -> RadarSnapshot:
    """Return the current simulated radar snapshot.

    Returns:
        RadarSnapshot with all aircraft states at the current simulation time.
    """
    service = _get_service()
    return service.get_snapshot()


@router.post("/scenario/{scenario_id}", response_model=RadarSnapshot)
async def load_scenario(scenario_id: str) -> RadarSnapshot:
    """Switch to a different scenario and reset the simulation clock.

    Args:
        scenario_id: One of SCN-A, SCN-B, or SCN-C.

    Returns:
        RadarSnapshot at the start of the newly loaded scenario.

    Raises:
        HTTPException: 404 if scenario_id is not recognized.
    """
    service = _get_service()
    try:
        service.load_scenario(scenario_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found") from None
    return service.get_snapshot()


@router.post("/advance", response_model=RadarSnapshot)
async def advance_simulation() -> RadarSnapshot:
    """Manually advance the simulation by one time step.

    Returns:
        Updated RadarSnapshot after advancing one step.
    """
    service = _get_service()
    return service.advance()
