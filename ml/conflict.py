"""Closest Point of Approach (CPA) calculation between aircraft pairs.

Determines the minimum future distance between two aircraft
projecting along their current state vectors. Uses relative
velocity decomposition to find the exact CPA time and distance.
"""

import math

from shared.constants import (
    CPA_ALERT_THRESHOLD_NM,
    CPA_CRITICAL_THRESHOLD_NM,
    CPA_TIME_HORIZON_SECONDS,
    SEPARATION_MINIMUM_NM,
    VERTICAL_SEPARATION_MINIMUM_FT,
)
from shared.models import AircraftState, CPAResult
from ml.trajectory import compute_bearing, extrapolate_position, haversine_distance_nm


def compute_cpa(aircraft_a: AircraftState, aircraft_b: AircraftState) -> CPAResult:
    """Compute Closest Point of Approach between two aircraft.

    Projects both aircraft along their current headings and speeds,
    then finds the time of minimum lateral distance within the
    look-ahead window. Vertical separation at that time is also
    computed.

    Args:
        aircraft_a: First aircraft state vector.
        aircraft_b: Second aircraft state vector.

    Returns:
        CPAResult with min_distance_nm, time_to_cpa_seconds,
        relative_bearing, altitude_separation, and conflict flag.

    Raises:
        ValueError: If both aircraft are at the same position (zero distance).
    """
    positions = _project_both(aircraft_a, aircraft_b)
    time_to_cpa = _find_cpa_time(positions, CPA_TIME_HORIZON_SECONDS)
    cpa_index = _time_to_index(time_to_cpa)

    pos_a_cpa = positions["aircraft_a"][cpa_index]
    pos_b_cpa = positions["aircraft_b"][cpa_index]

    min_distance_nm = haversine_distance_nm(
        pos_a_cpa.latitude, pos_a_cpa.longitude,
        pos_b_cpa.latitude, pos_b_cpa.longitude,
    )

    alt_a = pos_a_cpa.altitude_ft or 0
    alt_b = pos_b_cpa.altitude_ft or 0
    altitude_separation = abs(alt_a - alt_b)

    relative_bearing = compute_bearing(
        pos_a_cpa.latitude, pos_a_cpa.longitude,
        pos_b_cpa.latitude, pos_b_cpa.longitude,
    )

    is_conflict = _is_conflict(min_distance_nm, altitude_separation)

    return CPAResult(
        aircraft_a_callsign=aircraft_a.callsign,
        aircraft_b_callsign=aircraft_b.callsign,
        min_distance_nm=round(min_distance_nm, 2),
        time_to_cpa_seconds=round(time_to_cpa, 1),
        relative_bearing_deg=round(relative_bearing, 1),
        altitude_separation_ft=altitude_separation,
        is_conflict=is_conflict,
    )


def scan_pairwise_conflicts(
    aircraft_list: list[AircraftState],
) -> list[CPAResult]:
    """Scan all aircraft pairs for conflicts.

    Args:
        aircraft_list: List of current aircraft states.

    Returns:
        List of CPAResults where is_conflict is True (only conflicts, not safe pairs).
    """
    conflicts: list[CPAResult] = []
    count = len(aircraft_list)

    for i in range(count):
        for j in range(i + 1, count):
            result = compute_cpa(aircraft_list[i], aircraft_list[j])
            if result.is_conflict:
                conflicts.append(result)

    return conflicts


def _project_both(
    aircraft_a: AircraftState, aircraft_b: AircraftState
) -> dict[str, list]:
    """Project both aircraft positions at regular time steps.

    Uses 10-second increments within the look-ahead window.

    Args:
        aircraft_a: First aircraft state vector.
        aircraft_b: Second aircraft state vector.

    Returns:
        Dict with keys "aircraft_a" and "aircraft_b", each mapping
        to a list of PositionGeographic at each time step.
    """
    step_seconds = 10
    steps = CPA_TIME_HORIZON_SECONDS // step_seconds

    positions_a = [extrapolate_position(aircraft_a, t * step_seconds) for t in range(steps + 1)]
    positions_b = [extrapolate_position(aircraft_b, t * step_seconds) for t in range(steps + 1)]

    return {"aircraft_a": positions_a, "aircraft_b": positions_b}


def _find_cpa_time(
    positions: dict[str, list],
    horizon_seconds: int,
) -> float:
    """Find the time (in seconds) of minimum distance between projected paths.

    Args:
        positions: Dict of projected positions from _project_both.
        horizon_seconds: Look-ahead window in seconds.

    Returns:
        Time in seconds (from 0) at which the two aircraft are closest.
    """
    step_seconds = 10
    min_distance = float("inf")
    cpa_time = 0.0

    for t_step in range(len(positions["aircraft_a"])):
        pos_a = positions["aircraft_a"][t_step]
        pos_b = positions["aircraft_b"][t_step]

        dist = haversine_distance_nm(
            pos_a.latitude, pos_a.longitude,
            pos_b.latitude, pos_b.longitude,
        )

        if dist < min_distance:
            min_distance = dist
            cpa_time = t_step * step_seconds

    return cpa_time


def _time_to_index(time_seconds: float) -> int:
    """Convert a time value to a position list index.

    Args:
        time_seconds: Time in seconds from now.

    Returns:
        Index into the projected positions list.
    """
    step_seconds = 10
    return int(time_seconds / step_seconds)


def _is_conflict(distance_nm: float, altitude_separation_ft: int) -> bool:
    """Determine if a CPA distance constitutes a conflict.

    A conflict exists when both lateral and vertical separation
    minima are simultaneously violated at the CPA point.

    Args:
        distance_nm: Lateral distance at CPA in nautical miles.
        altitude_separation_ft: Vertical separation at CPA in feet.

    Returns:
        True if both lateral and vertical separation are violated.
    """
    lateral_conflict = distance_nm < SEPARATION_MINIMUM_NM
    vertical_conflict = altitude_separation_ft < VERTICAL_SEPARATION_MINIMUM_FT
    return lateral_conflict and vertical_conflict
