"""Simulation service — manages scenario lifecycle and data generation.

Tracks which scenario is active, how much time has elapsed,
and provides the current radar snapshot on demand.
"""

import asyncio
import logging
from datetime import datetime, timezone

from data.generator import evolve_scenario, generate_radar_snapshot
from data.scenarios import ALL_SCENARIOS
from shared.constants import SCENARIO_DURATION_SECONDS, SIMULATED_DATA_INTERVAL_SECONDS
from shared.models import RadarSnapshot, ScenarioDefinition

logger = logging.getLogger(__name__)


class SimulationService:
    """Manages the active scenario and produces time-stepped radar snapshots.

    The service runs a background loop that advances the simulation
    clock and stores the latest snapshot for API consumers.

    Attributes:
        active_scenario: The currently loaded scenario definition.
        elapsed_seconds: Seconds elapsed since scenario start.
        current_snapshot: The most recently generated radar snapshot.
        is_running: Whether the simulation loop is active.
    """

    def __init__(self, scenario_id: str = "SCN-A") -> None:
        """Initialize the simulation service with a scenario.

        Args:
            scenario_id: Key into ALL_SCENARIOS to load on startup.

        Raises:
            KeyError: If scenario_id is not found in the scenario registry.
        """
        if scenario_id not in ALL_SCENARIOS:
            raise KeyError(f"Scenario '{scenario_id}' not found. Available: {list(ALL_SCENARIOS.keys())}")

        self.active_scenario: ScenarioDefinition = ALL_SCENARIOS[scenario_id]
        self.elapsed_seconds: float = 0.0
        self.current_snapshot: RadarSnapshot = generate_radar_snapshot(self.active_scenario, 0.0)
        self.is_running: bool = False
        self._task: asyncio.Task | None = None

    def load_scenario(self, scenario_id: str) -> None:
        """Switch to a different scenario and reset the clock.

        Args:
            scenario_id: Key into ALL_SCENARIOS.

        Raises:
            KeyError: If scenario_id is not found.
        """
        if scenario_id not in ALL_SCENARIOS:
            raise KeyError(f"Scenario '{scenario_id}' not found. Available: {list(ALL_SCENARIOS.keys())}")

        self.active_scenario = ALL_SCENARIOS[scenario_id]
        self.elapsed_seconds = 0.0
        self.current_snapshot = generate_radar_snapshot(self.active_scenario, 0.0)
        logger.info("Loaded scenario %s: %s", scenario_id, self.active_scenario.name)

    def get_snapshot(self) -> RadarSnapshot:
        """Return the current radar snapshot.

        Returns:
            The most recently generated RadarSnapshot.
        """
        return self.current_snapshot

    def advance(self, delta_seconds: float | None = None) -> RadarSnapshot:
        """Advance the simulation clock and generate a new snapshot.

        Args:
            delta_seconds: Time to advance in seconds. Defaults to the
                configured SIMULATED_DATA_INTERVAL_SECONDS.

        Returns:
            Updated RadarSnapshot at the new elapsed time.
        """
        step = delta_seconds or SIMULATED_DATA_INTERVAL_SECONDS
        self.elapsed_seconds += step

        if self.elapsed_seconds > SCENARIO_DURATION_SECONDS:
            self.elapsed_seconds = 0.0
            logger.info("Scenario %s completed, resetting to t=0", self.active_scenario.scenario_id)

        self.current_snapshot = generate_radar_snapshot(self.active_scenario, self.elapsed_seconds)
        return self.current_snapshot

    async def start_loop(self, interval_seconds: float | None = None) -> None:
        """Run the simulation in a continuous loop.

        Advances the clock at the specified interval until stopped
        or the scenario completes a full cycle.

        Args:
            interval_seconds: Seconds between simulation steps.
                Defaults to SIMULATED_DATA_INTERVAL_SECONDS.
        """
        interval = interval_seconds or SIMULATED_DATA_INTERVAL_SECONDS
        self.is_running = True
        logger.info("Simulation loop started for %s", self.active_scenario.scenario_id)

        while self.is_running:
            self.advance()
            await asyncio.sleep(interval)

    def stop_loop(self) -> None:
        """Stop the simulation loop."""
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("Simulation loop stopped")

    def start_background(self, interval_seconds: float | None = None) -> asyncio.Task:
        """Start the simulation loop as a background asyncio task.

        Must be called from within a running event loop (e.g. during
        FastAPI lifespan startup).

        Args:
            interval_seconds: Seconds between simulation steps.

        Returns:
            The asyncio.Task running the simulation loop.
        """
        self._task = asyncio.create_task(self.start_loop(interval_seconds))
        return self._task
