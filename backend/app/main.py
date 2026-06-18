"""ATC Guardian backend — FastAPI application entry point.

Starts the simulation service, audit service, weather client,
OpenSky client, Band client, and the agent collaboration loop.
Mounts all API routers. WebSocket support for real-time radar data.
Run from project root: uv run python -m backend.app.main
"""

import asyncio
import logging
import os
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
from backend.app.routers import whatif as whatif_router
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
    whatif_router.set_simulation_service(service)
    audit_router.set_simulation_service_for_export(service)
    audit_router.set_decision_service_for_export(decision_service)

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
    # The mention map resolves each agent handle to its Band UUID; the
    # /messages endpoint requires mentions[].id to be a UUID, not a handle.
    mention_map = {
        "coordinator": settings.coordinator_agent_id,
        "conflict-detector": settings.conflict_detector_agent_id,
        "weather-analyst": settings.weather_analyst_agent_id,
        "ground-ops": settings.ground_ops_agent_id,
        "emergency-response": settings.emergency_response_agent_id,
        "safety-reviewer": settings.safety_reviewer_agent_id,
    }
    band_client = create_band_client(
        mode=settings.band_mode,
        api_key=settings.band_api_key,
        chat_id=settings.band_room_id,
        mention_map=mention_map,
        owner_user_id=settings.band_owner_user_id,
    )
    # Live Band agents are NOT connected here. They are launched lazily on
    # the first /demo/start and fully disconnected on /demo/stop (see
    # _start_demo_loops_async / _stop_demo_loops_async below). Connecting at
    # startup was the root cause of a runaway token-burn bug: every time the
    # Vercel frontend cold-started the Render backend, all 6 agents would
    # connect to the shared Band room, replay its message backlog, and
    # @mention-cascade each other — burning ~1-2M tokens/min before any demo
    # was ever started. Idle (no demo) now means zero connected agents and
    # zero token spend. See backend/app/agents/runner.py.
    agent_tasks: list[asyncio.Task] = []

    # Always wire the decision service into sim_agents so that the
    # coordinator handler (and any future agent handler) can create
    # proposals in both sim and live modes.
    from backend.app.services.sim_agents import (
        register_sim_agents,
        set_band_client,
        set_decision_service as set_sim_decision_service,
    )

    if isinstance(band_client, SimulatedBandClient):
        register_sim_agents(band_client)
        set_band_client(band_client)
    set_sim_decision_service(decision_service)

    poster = BandPoster(band_client)
    # Promote advisories → decisions only in live mode. In sim mode the
    # coordinator handler already creates proposals directly, so promoting
    # here too would double-create them.
    ingester = AdvisoryIngester(
        band_client,
        audit_service,
        decision_service=decision_service,
        promote_decisions=not isinstance(band_client, SimulatedBandClient),
    )

    # Legacy REST poller — still useful in live mode to backfill anything
    # the live client's fetch_replies misses. No-op when unconfigured.
    band_poller = BandPoller(
        api_key=settings.band_api_key,
        chat_id=settings.band_room_id,
        audit_service=audit_service,
    )
    await band_poller.start_polling()

    # Simulation loop and collaboration loop — do NOT auto-start.
    # The loops only run when a demo is explicitly activated via
    # /demo/start so agents stay idle (no LLM calls, no Band
    # dispatches) until the controller is ready.
    simulation_task: asyncio.Task | None = None
    collab_task: asyncio.Task | None = None

    async def _start_demo_loops_async() -> None:
        """Start the simulation + collaboration loops and connect agents.

        Idempotent. On first activation it also launches the 6 live Band
        agents (``BAND_MODE=live`` only) so they connect to the shared room
        exactly when the demo begins — never at backend startup. The agents
        connect before the demo-active flag is flipped so there is no window
        in which dispatches are sent to agents that are not yet subscribed.
        """
        nonlocal simulation_task, collab_task, agent_tasks
        if simulation_task and not simulation_task.done():
            logger.info("Demo loops already running")
            return

        # Launch live agents on demand (first start, or after a stop that
        # tore them down). Skipped entirely in sim mode and when credentials
        # are missing — both are logged by launch_agents().
        if settings.band_mode == "live" and not agent_tasks:
            from backend.app.agents.runner import launch_agents

            try:
                agent_tasks, agent_errors = await launch_agents()
                if agent_tasks:
                    os.environ["LABLAB_AGENTS_LAUNCHED"] = "1"
                    logger.info(
                        "Embedded agent runner: %d agents launched, %d failed",
                        len(agent_tasks),
                        len(agent_errors),
                    )
            except Exception:
                logger.exception(
                    "Embedded agent runner failed — agents must run externally"
                )
                agent_tasks = []

        # Flip the gate only after agents exist (defense-in-depth; the
        # connection lifecycle is the primary gate). Letting the event loop
        # breathe gives the agents' WebSockets a chance to open before the
        # poster fires the first dispatch.
        if agent_tasks:
            from backend.app.agents.runner import set_demo_active

            await asyncio.sleep(0)
            set_demo_active(True)

        service.is_running = True
        simulation_task = asyncio.create_task(
            service.start_loop(settings.simulation_interval_seconds)
        )
        collab_task = asyncio.create_task(
            _collaboration_loop(
                service, poster, ingester, settings.simulation_interval_seconds
            )
        )
        logger.info("Demo loops started — agents will now receive dispatches")

    async def _stop_demo_loops_async() -> None:
        """Stop the simulation + collaboration loops and disconnect agents.

        This is a hard stop:
          1. Deactivate the demo-active gate so any in-flight agent message
             is dropped before the connection tears down.
          2. Cancel the simulation + collaboration loops (which stops the
             poster from dispatching any further @mentions).
          3. Fully disconnect the live agents — cancelling their tasks makes
             ``agent.run()``'s ``finally`` call ``agent.stop()``, which tears
             down every execution context and closes the WebSocket. A
             disconnected agent consumes zero tokens and reads nothing from
             the shared room, even if it keeps filling with messages.

        We intentionally do NOT post STOP-directive messages into the Band
        room: that previously added 12 new messages that every connected
        agent had to process, fuelling the very cascade we are trying to
        stop. Disconnecting is cheaper, safer, and immediate.
        """
        nonlocal simulation_task, collab_task, agent_tasks
        # Step 1: Deactivate the message-processing gate.
        if agent_tasks:
            from backend.app.agents.runner import set_demo_active

            set_demo_active(False)
        # Step 2: Cancel simulation + collab loops (stops new dispatches).
        service.stop_loop()
        poster.reset()
        if simulation_task and not simulation_task.done():
            simulation_task.cancel()
        if collab_task and not collab_task.done():
            collab_task.cancel()
        simulation_task = None
        collab_task = None
        # Step 3: Disconnect the agents entirely (hard token stop).
        if agent_tasks:
            from backend.app.agents.runner import shutdown_agents_async

            await shutdown_agents_async(agent_tasks)
            agent_tasks = []
        logger.info("Demo loops stopped — agents disconnected until next activation")

    def _start_demo_loops() -> None:
        """Sync wrapper — schedules the async start in the event loop."""
        asyncio.create_task(_start_demo_loops_async())

    def _stop_demo_loops() -> None:
        """Sync wrapper — schedules the async stop in the event loop."""
        asyncio.create_task(_stop_demo_loops_async())

    # Expose start/stop to the data router so /demo/start and /demo/stop
    # can trigger them.
    data_router.set_demo_loop_controls(_start_demo_loops, _stop_demo_loops)

    logger.info(
        "ATC Guardian backend started with scenario %s (BAND_MODE=%s) — demo paused",
        settings.default_scenario_id,
        settings.band_mode,
    )

    yield

    # Shutdown — tear down any running demo loops and agents.
    await _stop_demo_loops_async()
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
    app.include_router(whatif_router.router)
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
