"""Rule-based detection of conflicts, emergencies, and weather hazards.

Turns a list of aircraft states into the advisory objects the radar
displays, WITHOUT any LLM calls. This is the deterministic layer that
populates a RadarSnapshot before agents are consulted.

Used by the simulation service on every tick so the radar shows real
conflict lines and blinking 7700s even in offline (BAND_MODE=sim) mode.
Agent advisories (produced later in the loop via Band) augment or
refine these detections — they do not replace them.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from ml.conflict import scan_pairwise_conflicts
from shared.constants import (
    CPA_ALERT_THRESHOLD_NM,
    CPA_CRITICAL_THRESHOLD_NM,
    EMERGENCY_SQUAWK_CODE,
    EMERGENCY_GRACE_PERIOD_SECONDS,
    HIJACK_SQUAWK_CODE,
    RADIO_FAILURE_SQUAWK_CODE,
)
from shared.models import (
    AircraftState,
    AlertSeverity,
    ConflictAdvisory,
    ConflictStatus,
    CPAResult,
    EmergencyDeclaration,
    EmergencyPhase,
    PositionGeographic,
    SIGMET,
    WeatherAdvisory,
)

# Squawk codes that constitute an active emergency.
EMERGENCY_TRIGGER_SQUAWKS: frozenset[str] = frozenset(
    {EMERGENCY_SQUAWK_CODE, HIJACK_SQUAWK_CODE, RADIO_FAILURE_SQUAWK_CODE}
)

#: Degrees-to-nautical-miles approximation for SIGMET edge distance (1° lat ≈ 60 nm).
_DEG_LAT_TO_NM: float = 60.0


def detect_conflicts(aircraft: list[AircraftState]) -> list[ConflictAdvisory]:
    """Run pairwise CPA scan and build advisories for every conflict.

    Args:
        aircraft: Current aircraft states on the radar.

    Returns:
        One ConflictAdvisory per conflicting pair, severity classified
        by the CPA distance thresholds. Empty list when separation is
        maintained.
    """
    now = datetime.now(timezone.utc)
    advisories: list[ConflictAdvisory] = []

    for cpa in scan_pairwise_conflicts(aircraft):
        pair_key = "-".join(sorted([cpa.aircraft_a_callsign, cpa.aircraft_b_callsign]))
        advisories.append(
            ConflictAdvisory(
                advisory_id=f"ADV-CONFLICT-{pair_key}",
                timestamp=now,
                severity=_classify_conflict_severity(cpa),
                status=ConflictStatus.DETECTED,
                cpa=cpa,
                resolution_hints=_resolution_hints(cpa),
            )
        )

    return advisories


def detect_emergencies(aircraft: list[AircraftState]) -> list[EmergencyDeclaration]:
    """Detect active emergencies from squawk codes.

    Args:
        aircraft: Current aircraft states on the radar.

    Returns:
        One EmergencyDeclaration per aircraft squawking an emergency
        code (7700/7500/7600). Empty list otherwise.
    """
    now = datetime.now(timezone.utc)
    emergencies: list[EmergencyDeclaration] = []

    for ac in aircraft:
        if ac.squawk not in EMERGENCY_TRIGGER_SQUAWKS:
            continue

        emergencies.append(
            EmergencyDeclaration(
                emergency_id=f"EMRG-{ac.callsign}",
                timestamp=now,
                callsign=ac.callsign,
                phase=_classify_emergency_phase(ac.squawk),
                squawk_code=ac.squawk,
                current_state=ac,
                estimated_position=PositionGeographic(
                    latitude=ac.latitude,
                    longitude=ac.longitude,
                    altitude_ft=ac.altitude_ft,
                ),
                priority=AlertSeverity.CRITICAL,
                grace_period_active=True,
            )
        )

    return emergencies


def _classify_conflict_severity(cpa: CPAResult) -> AlertSeverity:
    """Map a CPA distance to an alert severity.

    Args:
        cpa: The CPA result for the conflicting pair.

    Returns:
        CRITICAL under the critical threshold, WARNING under the alert
        threshold, CAUTION otherwise.
    """
    if cpa.min_distance_nm < CPA_CRITICAL_THRESHOLD_NM:
        return AlertSeverity.CRITICAL
    if cpa.min_distance_nm < CPA_ALERT_THRESHOLD_NM:
        return AlertSeverity.WARNING
    return AlertSeverity.CAUTION


def _resolution_hints(cpa: CPAResult) -> list[str]:
    """Produce deterministic resolution hint strings for a conflict.

    These are generic controller-style hints; the Conflict Detector
    agent later refines them with full context.

    Args:
        cpa: The CPA result for the conflicting pair.

    Returns:
        List of hint strings referencing the pair and suggested actions.
    """
    pair = f"{cpa.aircraft_a_callsign}/{cpa.aircraft_b_callsign}"
    return [
        f"Separation loss forecast for {pair} in {cpa.time_to_cpa_seconds:.0f}s "
        f"(CPA {cpa.min_distance_nm:.1f} nm)",
        f"Consider vectoring {cpa.aircraft_a_callsign} or "
        f"{cpa.aircraft_b_callsign} to restore {CPA_ALERT_THRESHOLD_NM:.0f} nm lateral separation.",
    ]


def _classify_emergency_phase(squawk: str) -> EmergencyPhase:
    """Map a squawk code to an ICAO emergency phase.

    Args:
        squawk: 4-digit transponder code.

    Returns:
        DISTRESS for 7700/7500, ALERT for 7600, UNCERTAINTY otherwise.
    """
    if squawk in {EMERGENCY_SQUAWK_CODE, HIJACK_SQUAWK_CODE}:
        return EmergencyPhase.DISTRESS
    if squawk == RADIO_FAILURE_SQUAWK_CODE:
        return EmergencyPhase.ALERT
    return EmergencyPhase.UNCERTAINTY


# ---------------------------------------------------------------------------
# Weather hazard detection
# ---------------------------------------------------------------------------


def detect_weather_hazards(
    sigmets: list[SIGMET], aircraft: list[AircraftState]
) -> list[WeatherAdvisory]:
    """Detect aircraft affected by SIGMET polygons or their buffer zones.

    Args:
        sigmets: Active SIGMET areas.
        aircraft: Current aircraft states.

    Returns:
        One WeatherAdvisory per SIGMET that affects at least one
        aircraft. SIGMETs with no affected traffic are skipped.
    """
    now = datetime.now(timezone.utc)
    advisories: list[WeatherAdvisory] = []

    for sigmet in sigmets:
        affected = [
            ac.callsign
            for ac in aircraft
            if _aircraft_in_sigmet(ac, sigmet)
        ]
        if not affected:
            continue

        advisories.append(
            WeatherAdvisory(
                advisory_id=f"ADV-WX-{sigmet.sigmet_id}",
                timestamp=now,
                severity=sigmet.severity,
                sigmet=sigmet,
                affected_callsigns=affected,
                deviation_hints=_deviation_hints(sigmet, affected),
            )
        )

    return advisories


def _aircraft_in_sigmet(aircraft: AircraftState, sigmet: SIGMET) -> bool:
    """Check if an aircraft is inside a SIGMET polygon or its buffer.

    Args:
        aircraft: The aircraft to test.
        sigmet: The SIGMET area with polygon and buffer.

    Returns:
        True if the aircraft position is inside the polygon or within
        the buffer distance of any polygon edge.
    """
    polygon: list[tuple[float, float]] = [
        (p.latitude, p.longitude) for p in sigmet.geometry.points
    ]
    if _point_in_polygon(aircraft.latitude, aircraft.longitude, polygon):
        return True
    return _within_buffer(
        aircraft.latitude, aircraft.longitude, polygon, sigmet.geometry.buffer_nm
    )


def _point_in_polygon(lat: float, lon: float, polygon: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test.

    Args:
        lat: Test point latitude.
        lon: Test point longitude.
        polygon: List of (lat, lon) vertices.

    Returns:
        True if the point lies inside the polygon.
    """
    n = len(polygon)
    if n < 3:
        return False

    inside = False
    j = n - 1
    for i in range(n):
        lat_i, lon_i = polygon[i]
        lat_j, lon_j = polygon[j]
        if (lat_i > lat) != (lat_j > lat) and lon < (
            (lon_j - lon_i) * (lat - lat_i) / (lat_j - lat_i) + lon_i
        ):
            inside = not inside
        j = i
    return inside


def _within_buffer(
    lat: float, lon: float, polygon: list[tuple[float, float]], buffer_nm: float
) -> bool:
    """Check if a point is within buffer_nm of any polygon edge.

    Args:
        lat: Test point latitude.
        lon: Test point longitude.
        polygon: List of (lat, lon) vertices.
        buffer_nm: Buffer distance in nautical miles.

    Returns:
        True if the point is within the buffer zone of any edge.
    """
    n = len(polygon)
    for i in range(n):
        j = (i + 1) % n
        edge_a_lat, edge_a_lon = polygon[i]
        edge_b_lat, edge_b_lon = polygon[j]
        if (
            _point_to_segment_distance_nm(
                lat, lon, edge_a_lat, edge_a_lon, edge_b_lat, edge_b_lon
            )
            <= buffer_nm
        ):
            return True
    return False


def _point_to_segment_distance_nm(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    """Shortest distance from a point to a line segment in nautical miles.

    Uses a flat-earth approximation (1° lat ≈ 60 nm), acceptable for
    the small areas SIGMET polygons typically span.

    Args:
        px: Test point latitude.
        py: Test point longitude.
        ax: Segment endpoint A latitude.
        ay: Segment endpoint A longitude.
        bx: Segment endpoint B latitude.
        by: Segment endpoint B longitude.

    Returns:
        Distance in nautical miles.
    """
    px_nm = px * _DEG_LAT_TO_NM
    py_nm = py * _DEG_LAT_TO_NM * math.cos(math.radians(px))
    ax_nm = ax * _DEG_LAT_TO_NM
    ay_nm = ay * _DEG_LAT_TO_NM * math.cos(math.radians(ax))
    bx_nm = bx * _DEG_LAT_TO_NM
    by_nm = by * _DEG_LAT_TO_NM * math.cos(math.radians(bx))

    dx = bx_nm - ax_nm
    dy = by_nm - ay_nm
    seg_len_sq = dx * dx + dy * dy

    if seg_len_sq == 0:
        return math.sqrt((px_nm - ax_nm) ** 2 + (py_nm - ay_nm) ** 2)

    t = max(0.0, min(1.0, ((px_nm - ax_nm) * dx + (py_nm - ay_nm) * dy) / seg_len_sq))
    proj_x = ax_nm + t * dx
    proj_y = ay_nm + t * dy
    return math.sqrt((px_nm - proj_x) ** 2 + (py_nm - proj_y) ** 2)


def _deviation_hints(sigmet: SIGMET, affected: list[str]) -> list[str]:
    """Produce deterministic deviation hints for a SIGMET.

    Args:
        sigmet: The active SIGMET.
        affected: Callsigns inside the SIGMET area.

    Returns:
        List of hint strings advising lateral/vertical deviation.
    """
    return [
        f"{', '.join(affected)} inside {sigmet.phenomenon} SIGMET {sigmet.sigmet_id} "
        f"(FL{sigmet.base_ft // 100:03d}-FL{sigmet.top_ft // 100:03d})",
        f"Recommend lateral deviation of ≥10 nm or climb/descend clear of "
        f"FL{sigmet.base_ft // 100:03d}-FL{sigmet.top_ft // 100:03d}.",
    ]

