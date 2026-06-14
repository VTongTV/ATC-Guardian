"""ATC Guardian backend — FastAPI application entry point.

Starts the simulation service, audit service, weather client,
OpenSky client, Band client, and the agent collaboration loop.
Mounts all API routers. WebSocket support for real-time radar data.
Run from project root: uv run python -m backend.app.main
"""

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import get_settings
from backend.app.routers import audit as audit_router
from backend.app.routers import collaboration as collaboration_router
from backend.app.routers import data as data_router
from backend.app.routers import decisions as decisions_router
from backend.app.routers import weather as weather_router
from backend.app.routers import websocket as ws_router
from backend.app.services.advisory_ingester import AdvisoryIngester
from backend.app.services.audit_service import AuditService
from backend.app.services.band_poller import BandPoller
from backend.app.services.band_poster import BandPoster
from backend.app.services.decision_service import DecisionService
from backend.app.services.opensky_client import OpenSkyClient
from backend.app.services.simulation_service import SimulationService
from backend.app.services.weather_client import AWCWeatherClient
from shared.band_client import SimulatedBandClient, create_band_client

logger = logging.getLogger(__name__)


async def _collaboration_loop(
    service: SimulationService,
    poster: BandPoster,
    ingester: AdvisoryIngester,
    interval_seconds: float,
) -> None:
    """Drive the detect → @mention → advisory loop each simulation tick.

    After every broadcast snapshot the poster dispatches any new
    conditions to agents via Band, and the ingester mirrors agent
    replies into the audit log. Runs until the simulation stops.

    Args:
        service: The simulation service (read for current snapshot).
        poster: The Band poster that triggers agents.
        ingester: The ingester that stores agent replies.
        interval_seconds: Loop period in seconds.
    """
    while service.is_running:
        try:
            await poster.process_snapshot(service.current_snapshot)
            await ingester.ingest_new(service.active_scenario.scenario_id)
        except Exception:
            logger.exception("Collaboration loop iteration failed")
        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan — startup and shutdown.

    Starts the simulation loop, audit DB, weather client,
    OpenSky client, Band client + collaboration loop on startup.
    Stops and closes everything on shutdown.
    """
    settings = get_settings()

    # Audit service (SQLite — always available)
    audit_service = AuditService()
    await audit_service.initialize()
    audit_router.set_audit_service(audit_service)
    collaboration_router.set_audit_service(audit_service)

    # Decision service (human-on-the-loop) — agent proposals await
    # controller APPROVE/REJECT/MODIFY before execution.
    decision_service = DecisionService(audit=audit_service)
    decisions_router.set_decision_service(decision_service)

    # Simulation service (scenario data)
    service = SimulationService(
        scenario_id=settings.default_scenario_id,
        broadcast_callback=ws_router.manager.broadcast_snapshot,
    )
    data_router.set_simulation_service(service)

    # AWC weather client (proxied — no CORS on AWC)
    weather_client = AWCWeatherClient()
    weather_router.set_weather_client(weather_client)

    # OpenSky client (optional — requires credentials)
    opensky_client = OpenSkyClient(
        username=settings.opensky_username,
        password=settings.opensky_password,
    )
    if opensky_client.is_configured:
        logger.info("OpenSky client configured with credentials")
    else:
        logger.info("OpenSky client not configured — simulation-only mode")

    # Band client — drives the agent collaboration loop. Defaults to an
    # in-process simulation so the full loop runs with zero credentials;
    # flip BAND_MODE=live once the Band room and agents are provisioned.
    band_client = create_band_client(
        mode=settings.band_mode,
        api_key=settings.band_api_key,
        chat_id=settings.band_room_id,
    )
    if isinstance(band_client, SimulatedBandClient):
        from backend.app.services.sim_agents import (
            register_sim_agents,
            set_band_client,
            set_decision_service,
        )

        register_sim_agents(band_client)
        set_decision_service(decision_service)
        set_band_client(band_client)

    poster = BandPoster(band_client)
    ingester = AdvisoryIngester(band_client, audit_service)

    # Legacy REST poller — still useful in live mode to backfill anything
    # the live client's fetch_replies misses. No-op when unconfigured.
    band_poller = BandPoller(
        api_key=settings.band_api_key,
        chat_id=settings.band_room_id,
        audit_service=audit_service,
    )
    await band_poller.start_polling()

    # Start simulation loop
    task = asyncio.create_task(service.start_loop(settings.simulation_interval_seconds))
    collab_task = asyncio.create_task(
        _collaboration_loop(service, poster, ingester, settings.simulation_interval_seconds)
    )
    logger.info(
        "ATC Guardian backend started with scenario %s (BAND_MODE=%s)",
        settings.default_scenario_id,
        settings.band_mode,
    )

    yield

    # Shutdown
    service.stop_loop()
    task.cancel()
    collab_task.cancel()
    await band_poller.close()
    await band_client.close()
    await opensky_client.close()
    await weather_client.close()
    await audit_service.close()
    logger.info("ATC Guardian backend stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI instance with CORS, lifespan, and routers.
    """
    settings = get_settings()

    app = FastAPI(
        title="ATC Guardian",
        description="Multi-agent Air Traffic Control decision support system",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(data_router.router)
    app.include_router(weather_router.router)
    app.include_router(audit_router.router)
    app.include_router(decisions_router.router)
    app.include_router(collaboration_router.router)
    app.include_router(ws_router.router)

    return app


app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    uvicorn.run(
        "backend.app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
