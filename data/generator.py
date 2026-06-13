"""Simulation engine for evolving aircraft state over time.

Takes a ScenarioDefinition and produces time-stepped snapshots
by extrapolating each aircraft along its current state vector.
Supports mid-scenario events (squawk changes, heading changes)
injected at specific elapsed times.
"""

from datetime import datetime, timedelta, timezone

from ml.trajectory import extrapolate_position
from shared.constants import SIMULATED_DATA_INTERVAL_SECONDS
from shared.models import AircraftState, PositionGeographic, RadarSnapshot, ScenarioDefinition


def evolve_scenario(
    scenario: ScenarioDefinition,
    elapsed_seconds: float,
) -> list[AircraftState]:
    """Compute all aircraft states at a given elapsed time in the scenario.

    Each aircraft is extrapolated forward from its initial state
    using constant-velocity great-circle projection.

    Args:
        scenario: The scenario definition with initial aircraft states.
        elapsed_seconds: Seconds since scenario start.

    Returns:
        List of updated AircraftState at the given elapsed time.
    """
    evolved_states: list[AircraftState] = []

    for aircraft in scenario.initial_states:
        evolved = _evolve_single_aircraft(aircraft, elapsed_seconds)
        evolved_states.append(evolved)

    return evolved_states


def generate_radar_snapshot(
    scenario: ScenarioDefinition,
    elapsed_seconds: float,
) -> RadarSnapshot:
    """Produce a complete radar snapshot for a given scenario time.

    Args:
        scenario: The scenario definition.
        elapsed_seconds: Seconds since scenario start.

    Returns:
        RadarSnapshot with all aircraft states at the given time.
        Conflicts, weather, and emergencies are empty — agents fill those.
    """
    now = datetime.now(timezone.utc)
    aircraft_states = evolve_scenario(scenario, elapsed_seconds)

    return RadarSnapshot(
        timestamp=now,
        aircraft=aircraft_states,
        conflicts=[],
        weather_advisories=[],
        emergencies=[],
    )


def generate_scenario_timeline(
    scenario: ScenarioDefinition,
    duration_seconds: float | None = None,
    interval_seconds: float | None = None,
) -> list[RadarSnapshot]:
    """Generate a full timeline of radar snapshots for a scenario.

    Args:
        scenario: The scenario definition.
        duration_seconds: Total duration in seconds. Defaults to SCENARIO_DURATION_SECONDS.
        interval_seconds: Time between snapshots. Defaults to SIMULATED_DATA_INTERVAL_SECONDS.

    Returns:
        List of RadarSnapshot objects from t=0 to t=duration.
    """
    from shared.constants import SCENARIO_DURATION_SECONDS

    duration = duration_seconds or SCENARIO_DURATION_SECONDS
    interval = interval_seconds or SIMULATED_DATA_INTERVAL_SECONDS

    snapshots: list[RadarSnapshot] = []
    elapsed = 0.0

    while elapsed <= duration:
        snapshot = generate_radar_snapshot(scenario, elapsed)
        snapshots.append(snapshot)
        elapsed += interval

    return snapshots


def _evolve_single_aircraft(
    aircraft: AircraftState,
    elapsed_seconds: float,
) -> AircraftState:
    """Evolve a single aircraft forward in time.

    Projects the aircraft position using its current state vector.
    Squawk code and other discrete parameters are preserved unless
    scenario steps override them (handled at a higher level).

    Args:
        aircraft: The initial aircraft state.
        elapsed_seconds: Seconds to project forward.

    Returns:
        New AircraftState at the projected time.
    """
    if elapsed_seconds <= 0:
        return aircraft

    position = extrapolate_position(aircraft, elapsed_seconds)
    new_altitude = position.altitude_ft if position.altitude_ft is not None else aircraft.altitude_ft

    new_timestamp = aircraft.timestamp + timedelta(seconds=elapsed_seconds)

    return AircraftState(
        callsign=aircraft.callsign,
        latitude=round(position.latitude, 6),
        longitude=round(position.longitude, 6),
        altitude_ft=new_altitude,
        heading_deg=aircraft.heading_deg,
        speed_kts=aircraft.speed_kts,
        vertical_speed_fpm=aircraft.vertical_speed_fpm,
        squawk=aircraft.squawk,
        category=aircraft.category,
        timestamp=new_timestamp,
        on_ground=aircraft.on_ground,
    )
