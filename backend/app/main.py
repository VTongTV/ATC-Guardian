"""ATC Guardian backend — FastAPI application entry point.

Starts the simulation service, audit service, weather client,
OpenSky client, and Band poller. Mounts all API routers.
WebSocket support for real-time radar data streaming.
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
from backend.app.routers import data as data_router
from backend.app.routers import weather as weather_router
from backend.app.routers import websocket as ws_router
from backend.app.services.audit_service import AuditService
from backend.app.services.band_poller import BandPoller
from backend.app.services.opensky_client import OpenSkyClient
from backend.app.services.simulation_service import SimulationService
from backend.app.services.weather_client import AWCWeatherClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan — startup and shutdown.

    Starts the simulation loop, audit DB, weather client,
    OpenSky client, and Band poller on startup.
    Stops and closes everything on shutdown.
    """
    settings = get_settings()

    # Audit service (SQLite — always available)
    audit_service = AuditService()
    await audit_service.initialize()
    audit_router.set_audit_service(audit_service)

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

    # Band poller (optional — requires credentials)
    band_poller = BandPoller(
        api_key=settings.band_api_key,
        chat_id=settings.band_room_id,
        audit_service=audit_service,
    )
    await band_poller.start_polling()

    # Start simulation loop
    task = asyncio.create_task(service.start_loop(settings.simulation_interval_seconds))
    logger.info("ATC Guardian backend started with scenario %s", settings.default_scenario_id)

    yield

    # Shutdown
    await band_poller.close()
    await opensky_client.close()
    await weather_client.close()
    service.stop_loop()
    task.cancel()
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
