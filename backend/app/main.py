"""ATC Guardian backend — FastAPI application entry point.

Starts the simulation service and mounts API routers.
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
from backend.app.routers import data as data_router
from backend.app.routers import websocket as ws_router
from backend.app.services.simulation_service import SimulationService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan — startup and shutdown.

    Starts the simulation loop on startup and stops it on shutdown.
    Wires the WebSocket connection manager as a broadcast callback
    so each simulation tick is pushed to connected clients.
    """
    settings = get_settings()
    service = SimulationService(
        scenario_id=settings.default_scenario_id,
        broadcast_callback=ws_router.manager.broadcast_snapshot,
    )
    data_router.set_simulation_service(service)

    task = asyncio.create_task(service.start_loop(settings.simulation_interval_seconds))
    logger.info("ATC Guardian backend started with scenario %s", settings.default_scenario_id)

    yield

    service.stop_loop()
    task.cancel()
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
