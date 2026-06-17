"""Data router — endpoints for simulated and live aircraft data.

Provides the /data/simulated endpoint that the frontend radar
display polls for the current aircraft state snapshot, plus
/demo/start and /demo/stop endpoints that control when the
simulation and agent collaboration loops are active.

Agents sit idle (no LLM calls, no Band dispatches) until a demo
is explicitly started.
"""

import logging
from typing import Callable

from fastapi import APIRouter, HTTPException

from backend.app.services.simulation_service import SimulationService
from shared.models import RadarSnapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data", tags=["data"])

# Injected by main.py on application startup
_simulation_service: SimulationService | None = None

# Demo loop controls — injected by main.py
_start_demo_loops: Callable[[], None] | None = None
_stop_demo_loops: Callable[[], None] | None = None


def set_simulation_service(service: SimulationService) -> None:
    """Register the simulation service instance for this router.

    Called once during application lifespan startup.

    Args:
        service: The active SimulationService instance.
    """
    global _simulation_service
    _simulation_service = service


def set_demo_loop_controls(
    start: Callable[[], None],
    stop: Callable[[], None],
) -> None:
    """Register the demo start/stop callbacks from main.py.

    Args:
        start: Callable that starts the simulation + collaboration loops.
        stop: Callable that stops them.
    """
    global _start_demo_loops, _stop_demo_loops
    _start_demo_loops = start
    _stop_demo_loops = stop


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


@router.post("/demo/start")
async def start_demo() -> dict[str, str]:
    """Start the simulation and agent collaboration loops.

    Agents begin receiving dispatches and the simulation clock
    starts advancing. Idempotent — calling twice has no effect.

    Returns:
        Confirmation message.
    """
    if _start_demo_loops is None:
        raise HTTPException(status_code=503, detail="Demo controls not initialized")
    _start_demo_loops()
    return {"status": "started", "message": "Demo active — agents receiving dispatches"}


@router.post("/demo/stop")
async def stop_demo() -> dict[str, str]:
    """Stop the simulation and agent collaboration loops.

    Agents return to idle (no LLM calls, no Band dispatches).
    The current scenario and snapshot remain available for
    inspection via /data/simulated.

    Returns:
        Confirmation message.
    """
    if _stop_demo_loops is None:
        raise HTTPException(status_code=503, detail="Demo controls not initialized")
    _stop_demo_loops()
    return {"status": "stopped", "message": "Demo paused — agents idle"}
