"""Rule-based dispatch logic for ATC Guardian agents.

Each dispatcher evaluates incoming data and decides whether the LLM
should be invoked. These are pure, stateless pre-filters that work
on raw dicts (Band message payloads).

Import from agents/ directory:
    from agents.dispatch import CoordinatorDispatcher, DispatchDecision
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from ml.trajectory import compute_bearing as _compute_bearing_impl
from ml.trajectory import haversine_distance_nm
from shared.constants import (
    CPA_ALERT_THRESHOLD_NM,
    CPA_CRITICAL_THRESHOLD_NM,
    EMERGENCY_SQUAWK_CODE,
    HIJACK_SQUAWK_CODE,
    RADIO_FAILURE_SQUAWK_CODE,
    SEPARATION_MINIMUM_NM,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALTITUDE_PROXIMITY_THRESHOLD_FT: int = 2000
"""Altitude band for considering aircraft pairs relevant (feet)."""

CPA_EMERGENCY_THRESHOLD_NM: float = 1.0
"""CPA distance for EMERGENCY urgency classification."""

EMERGENCY_SQUAWKS: set[str] = {EMERGENCY_SQUAWK_CODE, HIJACK_SQUAWK_CODE}
"""Squawk codes that trigger immediate EMERGENCY urgency."""

URGENT_SQUAWKS: set[str] = {RADIO_FAILURE_SQUAWK_CODE}
"""Squawk codes that trigger URGENT urgency."""


# ---------------------------------------------------------------------------
# Shared result model
# ---------------------------------------------------------------------------


class DispatchDecision(BaseModel):
    """Result of a dispatch rule evaluation.

    Attributes:
        should_invoke_llm: True if the LLM should be invoked for this data.
        reason: Human-readable explanation of the decision.
        urgency: Priority level — ROUTINE, URGENT, or EMERGENCY.
        target_agents: Agent names to @mention if dispatching.
        data_summary: Brief summary for inclusion in the LLM prompt.
    """

    should_invoke_llm: bool
    reason: str
    urgency: str = "ROUTINE"
    target_agents: list[str] = Field(default_factory=list)
    data_summary: str = ""


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance between two points in nautical miles.

    Thin alias for :func:`ml.trajectory.haversine_distance_nm` kept so
    existing dispatch tests and call sites resolve unchanged.

    Args:
        lat1: Latitude of point 1 in decimal degrees.
        lon1: Longitude of point 1 in decimal degrees.
        lat2: Latitude of point 2 in decimal degrees.
        lon2: Longitude of point 2 in decimal degrees.

    Returns:
        Distance in nautical miles.
    """
    return haversine_distance_nm(lat1, lon1, lat2, lon2)


def _point_in_polygon(lat: float, lon: float, polygon: list[tuple[float, float]]) -> bool:
    """Test if a point lies inside a polygon using ray casting.

    Args:
        lat: Latitude of the test point.
        lon: Longitude of the test point.
        polygon: List of (lat, lon) vertices defining the polygon.

    Returns:
        True if the point is inside the polygon.
    """
    n = len(polygon)
    if n < 3:
        return False

    inside = False
    j = n - 1
    for i in range(n):
        lat_i, lon_i = polygon[i]
        lat_j, lon_j = polygon[j]

        if ((lat_i > lat) != (lat_j > lat)) and (
            lon < (lon_j - lon_i) * (lat - lat_i) / (lat_j - lat_i) + lon_i
        ):
            inside = not inside
        j = i

    return inside


# ---------------------------------------------------------------------------
# Coordinator dispatcher
# ---------------------------------------------------------------------------


class CoordinatorDispatcher:
    """Evaluates incoming aircraft data to decide coordinator dispatches.

    Pre-filter rules:
    - Squawk 7700/7500/7600 detected → IMMEDIATE dispatch to @emergency-response
    - 2+ aircraft at similar altitude (within 2000 ft) and converging → dispatch to @conflict-detector
    - SIGMET data received → dispatch to @weather-analyst
    - Emergency/diversion needs airport info → dispatch to @ground-ops
    """

    def evaluate_aircraft_data(self, aircraft_states: list[dict]) -> list[DispatchDecision]:
        """Evaluate aircraft states and return dispatch decisions.

        Args:
            aircraft_states: List of aircraft state dicts from Band messages.

        Returns:
            List of DispatchDecision for actions the coordinator should take.
        """
        decisions: list[DispatchDecision] = []

        # 1. Check for emergency squawks first (highest priority)
        for ac in aircraft_states:
            emergency_decision = self.evaluate_squawk(ac)
            if emergency_decision is not None:
                decisions.append(emergency_decision)

        # 2. Check for converging pairs at similar altitudes
        conflict_pairs = self._find_converging_pairs(aircraft_states)
        if conflict_pairs:
            pair_descriptions = []
            for ac_a, ac_b in conflict_pairs:
                pair_descriptions.append(
                    f"{ac_a.get('callsign', 'UNK')} and {ac_b.get('callsign', 'UNK')}"
                )
            decisions.append(
                DispatchDecision(
                    should_invoke_llm=False,
                    reason=f"Converging pairs detected: {', '.join(pair_descriptions)}",
                    urgency="ROUTINE",
                    target_agents=["conflict-detector"],
                    data_summary=f"Conflict detector should analyze {len(conflict_pairs)} converging pair(s)",
                )
            )

        return decisions

    def evaluate_squawk(self, aircraft: dict) -> DispatchDecision | None:
        """Check if an aircraft squawk requires emergency dispatch.

        Args:
            aircraft: Aircraft state dict with 'squawk' and 'callsign' keys.

        Returns:
            DispatchDecision if emergency squawk detected, None otherwise.
        """
        squawk = aircraft.get("squawk", "1200")
        callsign = aircraft.get("callsign", "UNK")

        if squawk == EMERGENCY_SQUAWK_CODE:
            return DispatchDecision(
                should_invoke_llm=False,
                reason=f"Squawk 7700 (emergency) detected on {callsign}",
                urgency="EMERGENCY",
                target_agents=["emergency-response"],
                data_summary=f"EMERGENCY: {callsign} squawking 7700",
            )

        if squawk == HIJACK_SQUAWK_CODE:
            return DispatchDecision(
                should_invoke_llm=False,
                reason=f"Squawk 7500 (hijack) detected on {callsign}",
                urgency="EMERGENCY",
                target_agents=["emergency-response"],
                data_summary=f"HIJACK: {callsign} squawking 7500",
            )

        if squawk == RADIO_FAILURE_SQUAWK_CODE:
            return DispatchDecision(
                should_invoke_llm=False,
                reason=f"Squawk 7600 (radio failure) detected on {callsign}",
                urgency="URGENT",
                target_agents=["emergency-response"],
                data_summary=f"RADIO FAILURE: {callsign} squawking 7600",
            )

        return None

    def _find_converging_pairs(
        self, aircraft_states: list[dict]
    ) -> list[tuple[dict, dict]]:
        """Find pairs of aircraft that are converging at similar altitudes.

        Args:
            aircraft_states: List of aircraft state dicts.

        Returns:
            List of (ac_a, ac_b) tuples for converging pairs.
        """
        pairs: list[tuple[dict, dict]] = []
        n = len(aircraft_states)

        for i in range(n):
            for j in range(i + 1, n):
                ac_a = aircraft_states[i]
                ac_b = aircraft_states[j]

                if self._have_similar_altitude(ac_a, ac_b) and self._are_converging(ac_a, ac_b):
                    pairs.append((ac_a, ac_b))

        return pairs

    def _are_converging(self, ac_a: dict, ac_b: dict) -> bool:
        """Check if two aircraft are on converging courses.

        Two aircraft are considered converging if the distance between
        them is decreasing based on their headings and speeds. A simple
        approximation: check if the bearing from A to B is within 90° of
        A's heading, and vice versa.

        Args:
            ac_a: First aircraft state dict.
            ac_b: Second aircraft state dict.

        Returns:
            True if the aircraft are converging.
        """
        lat_a = ac_a.get("latitude", 0.0)
        lon_a = ac_a.get("longitude", 0.0)
        lat_b = ac_b.get("latitude", 0.0)
        lon_b = ac_b.get("longitude", 0.0)
        heading_a = ac_a.get("heading_deg", 0.0)
        heading_b = ac_b.get("heading_deg", 0.0)

        # Bearing from A to B
        bearing_a_to_b = _compute_bearing(lat_a, lon_a, lat_b, lon_b)
        # Bearing from B to A (opposite direction)
        bearing_b_to_a = (bearing_a_to_b + 180) % 360

        # Check if A is heading towards B (within 90° of bearing)
        diff_a = abs(_normalize_angle(heading_a - bearing_a_to_b))
        # Check if B is heading towards A
        diff_b = abs(_normalize_angle(heading_b - bearing_b_to_a))

        return diff_a < 90 and diff_b < 90

    def _have_similar_altitude(
        self, ac_a: dict, ac_b: dict, threshold_ft: int = ALTITUDE_PROXIMITY_THRESHOLD_FT
    ) -> bool:
        """Check if two aircraft are within the altitude threshold.

        Args:
            ac_a: First aircraft state dict.
            ac_b: Second aircraft state dict.
            threshold_ft: Altitude difference threshold in feet.

        Returns:
            True if altitude difference is within the threshold.
        """
        alt_a = ac_a.get("altitude_ft", 0)
        alt_b = ac_b.get("altitude_ft", 0)
        return abs(alt_a - alt_b) <= threshold_ft


def _compute_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute initial bearing from point 1 to point 2.

    Thin alias for :func:`ml.trajectory.compute_bearing` kept so existing
    dispatch tests and call sites resolve unchanged.

    Args:
        lat1: Latitude of origin in decimal degrees.
        lon1: Longitude of origin in decimal degrees.
        lat2: Latitude of destination in decimal degrees.
        lon2: Longitude of destination in decimal degrees.

    Returns:
        Bearing in degrees (0-360, clockwise from true north).
    """
    return _compute_bearing_impl(lat1, lon1, lat2, lon2)


def _normalize_angle(angle: float) -> float:
    """Normalize an angle to the range [-180, 180].

    Args:
        angle: Angle in degrees.

    Returns:
        Normalized angle in range [-180, 180].
    """
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle


# ---------------------------------------------------------------------------
# Conflict detector dispatcher
# ---------------------------------------------------------------------------


class ConflictDetectorDispatcher:
    """Evaluates if conflict detection requires LLM invocation.

    Pre-filter rules:
    - CPA < 5 nm → invoke LLM
    - CPA < 3 nm → invoke with URGENT urgency
    - CPA < 1 nm → invoke with EMERGENCY urgency
    - CPA >= 5 nm → skip, log only
    """

    def evaluate_cpa(self, cpa_result: dict) -> DispatchDecision:
        """Evaluate CPA result to decide if LLM should be invoked.

        Args:
            cpa_result: Dict with 'min_distance_nm', 'aircraft_a_callsign',
                        'aircraft_b_callsign', and 'is_conflict' keys.

        Returns:
            DispatchDecision indicating whether the LLM should analyze this CPA.
        """
        min_distance = cpa_result.get("min_distance_nm", float("inf"))
        ac_a = cpa_result.get("aircraft_a_callsign", "UNK")
        ac_b = cpa_result.get("aircraft_b_callsign", "UNK")
        is_conflict = cpa_result.get("is_conflict", False)

        if min_distance >= CPA_ALERT_THRESHOLD_NM:
            return DispatchDecision(
                should_invoke_llm=False,
                reason=f"CPA {min_distance:.1f} nm between {ac_a} and {ac_b} exceeds {CPA_ALERT_THRESHOLD_NM} nm threshold",
                data_summary=f"CPA {min_distance:.1f} nm — no action needed",
            )

        if min_distance < CPA_EMERGENCY_THRESHOLD_NM:
            urgency = "EMERGENCY"
            reason = f"CPA {min_distance:.1f} nm (EMERGENCY) between {ac_a} and {ac_b}"
        elif min_distance < CPA_CRITICAL_THRESHOLD_NM:
            urgency = "URGENT"
            reason = f"CPA {min_distance:.1f} nm (CRITICAL) between {ac_a} and {ac_b}"
        else:
            urgency = "ROUTINE"
            reason = f"CPA {min_distance:.1f} nm (ALERT) between {ac_a} and {ac_b}"

        return DispatchDecision(
            should_invoke_llm=True,
            reason=reason,
            urgency=urgency,
            data_summary=f"CONFLICT: {ac_a} and {ac_b} CPA {min_distance:.1f} nm ({urgency})",
        )

    def should_analyze_pair(self, ac_a: dict, ac_b: dict) -> bool:
        """Quick check if a pair is worth CPA analysis at all.

        Skips pairs that are obviously non-conflicting (e.g., far apart
        or at very different altitudes).

        Args:
            ac_a: First aircraft state dict.
            ac_b: Second aircraft state dict.

        Returns:
            True if the pair should undergo full CPA calculation.
        """
        lat_a = ac_a.get("latitude", 0.0)
        lon_a = ac_a.get("longitude", 0.0)
        lat_b = ac_b.get("latitude", 0.0)
        lon_b = ac_b.get("longitude", 0.0)
        alt_a = ac_a.get("altitude_ft", 0)
        alt_b = ac_b.get("altitude_ft", 0)

        # Quick altitude filter: skip if vertical separation > 2000 ft
        if abs(alt_a - alt_b) > ALTITUDE_PROXIMITY_THRESHOLD_FT:
            return False

        # Quick distance filter: skip if > 60 nm apart
        distance_nm = _haversine_nm(lat_a, lon_a, lat_b, lon_b)
        return distance_nm <= 60.0


# ---------------------------------------------------------------------------
# Weather analyst dispatcher
# ---------------------------------------------------------------------------


class WeatherAnalystDispatcher:
    """Evaluates if weather data requires LLM invocation.

    Pre-filter rules:
    - SIGMET polygon overlaps any aircraft flight path → invoke LLM
    - No overlap → skip, log only
    """

    def evaluate_sigmet(self, sigmet: dict, aircraft: list[dict]) -> DispatchDecision:
        """Check if SIGMET affects any active aircraft.

        Args:
            sigmet: Dict with 'sigmet_id', 'phenomenon', and 'geometry' keys.
                    geometry contains 'points' (list of {lat, lon}) and optional 'buffer_nm'.
            aircraft: List of aircraft state dicts.

        Returns:
            DispatchDecision indicating whether the LLM should analyze this SIGMET.
        """
        sigmet_id = sigmet.get("sigmet_id", "UNK")
        phenomenon = sigmet.get("phenomenon", "unknown")
        geometry = sigmet.get("geometry", {})
        points_raw = geometry.get("points", [])
        buffer_nm = geometry.get("buffer_nm", 10.0)

        # Convert geometry points to (lat, lon) tuples
        polygon: list[tuple[float, float]] = []
        for pt in points_raw:
            if isinstance(pt, dict):
                polygon.append((pt.get("latitude", 0.0), pt.get("longitude", 0.0)))
            elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
                polygon.append((pt[0], pt[1]))

        if len(polygon) < 3:
            return DispatchDecision(
                should_invoke_llm=False,
                reason=f"SIGMET {sigmet_id} has invalid geometry (< 3 vertices)",
                data_summary=f"SIGMET {sigmet_id} ({phenomenon}) — skipped, invalid geometry",
            )

        affected_callsigns: list[str] = []
        for ac in aircraft:
            lat = ac.get("latitude", 0.0)
            lon = ac.get("longitude", 0.0)
            callsign = ac.get("callsign", "UNK")

            # Check if aircraft position is inside the SIGMET polygon
            if _point_in_polygon(lat, lon, polygon):
                affected_callsigns.append(callsign)
                continue

            # Check if aircraft is within the buffer zone of any polygon edge
            if self._within_buffer(lat, lon, polygon, buffer_nm):
                affected_callsigns.append(callsign)

        if not affected_callsigns:
            return DispatchDecision(
                should_invoke_llm=False,
                reason=f"SIGMET {sigmet_id} ({phenomenon}) does not affect any tracked aircraft",
                data_summary=f"SIGMET {sigmet_id} ({phenomenon}) — no affected aircraft",
            )

        return DispatchDecision(
            should_invoke_llm=True,
            reason=f"SIGMET {sigmet_id} ({phenomenon}) affects {len(affected_callsigns)} aircraft: {', '.join(affected_callsigns)}",
            urgency="ROUTINE",
            data_summary=f"WEATHER: SIGMET {sigmet_id} ({phenomenon}) affects {', '.join(affected_callsigns)}",
        )

    def _within_buffer(
        self,
        lat: float,
        lon: float,
        polygon: list[tuple[float, float]],
        buffer_nm: float,
    ) -> bool:
        """Check if a point is within buffer_nm of any polygon edge.

        Args:
            lat: Latitude of the test point.
            lon: Longitude of the test point.
            polygon: List of (lat, lon) polygon vertices.
            buffer_nm: Buffer distance in nautical miles.

        Returns:
            True if the point is within the buffer zone.
        """
        n = len(polygon)
        for i in range(n):
            j = (i + 1) % n
            edge_lat1, edge_lon1 = polygon[i]
            edge_lat2, edge_lon2 = polygon[j]

            dist = _point_to_segment_distance_nm(lat, lon, edge_lat1, edge_lon1, edge_lat2, edge_lon2)
            if dist <= buffer_nm:
                return True

        return False


def _point_to_segment_distance_nm(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    """Compute shortest distance from point to line segment in nm.

    Uses an approximation that treats lat/lon as a flat plane.
    Acceptable for small areas (SIGMET polygons typically span < 5°).

    Args:
        px: Latitude of the test point.
        py: Longitude of the test point.
        ax: Latitude of segment endpoint A.
        ay: Longitude of segment endpoint A.
        bx: Latitude of segment endpoint B.
        by: Longitude of segment endpoint B.

    Returns:
        Distance in nautical miles.
    """
    # Convert to approximate nm (1° lat ≈ 60 nm)
    px_nm = px * 60
    py_nm = py * 60 * math.cos(math.radians(px))
    ax_nm = ax * 60
    ay_nm = ay * 60 * math.cos(math.radians(ax))
    bx_nm = bx * 60
    by_nm = by * 60 * math.cos(math.radians(bx))

    dx = bx_nm - ax_nm
    dy = by_nm - ay_nm
    seg_len_sq = dx * dx + dy * dy

    if seg_len_sq == 0:
        # Degenerate segment (A == B)
        return math.sqrt((px_nm - ax_nm) ** 2 + (py_nm - ay_nm) ** 2)

    t = max(0, min(1, ((px_nm - ax_nm) * dx + (py_nm - ay_nm) * dy) / seg_len_sq))

    proj_x = ax_nm + t * dx
    proj_y = ay_nm + t * dy

    return math.sqrt((px_nm - proj_x) ** 2 + (py_nm - proj_y) ** 2)


# ---------------------------------------------------------------------------
# Ground ops dispatcher
# ---------------------------------------------------------------------------


class GroundOpsDispatcher:
    """Evaluates if ground info requests need LLM processing.

    Pre-filter rules:
    - Always responds to direct @mention requests → invoke LLM
    - Never invokes proactively
    """

    def evaluate_request(self, request_data: dict) -> DispatchDecision:
        """Evaluate if ground request requires LLM invocation.

        Args:
            request_data: Dict with 'request_type', 'icao_code', and
                          optional 'context_callsign' keys.

        Returns:
            DispatchDecision indicating whether the LLM should process this request.
        """
        request_type = request_data.get("request_type", "unknown")
        icao_code = request_data.get("icao_code", "UNKW")
        callsign = request_data.get("context_callsign", "N/A")

        return DispatchDecision(
            should_invoke_llm=True,
            reason=f"Ground request ({request_type}) for {icao_code} from {callsign}",
            urgency="ROUTINE",
            data_summary=f"GROUND OPS: {request_type} request for {icao_code} (callsign: {callsign})",
        )


# ---------------------------------------------------------------------------
# Emergency response dispatcher
# ---------------------------------------------------------------------------


class EmergencyResponseDispatcher:
    """Evaluates if emergency data requires LLM invocation.

    Pre-filter rules:
    - Squawk 7700/7500 → IMMEDIATELY invoke LLM (EMERGENCY urgency)
    - Squawk 7600 → invoke LLM (URGENT urgency)
    - No emergency squawk → skip
    """

    def evaluate_squawk(self, aircraft: dict) -> DispatchDecision | None:
        """Evaluate aircraft squawk code for emergency response.

        Args:
            aircraft: Dict with 'squawk', 'callsign', 'latitude',
                      'longitude', 'altitude_ft', 'heading_deg',
                      'speed_kts', and 'vertical_speed_fpm' keys.

        Returns:
            DispatchDecision if emergency squawk detected, None otherwise.
        """
        squawk = aircraft.get("squawk", "1200")
        callsign = aircraft.get("callsign", "UNK")

        if squawk == EMERGENCY_SQUAWK_CODE:
            phase = self.classify_emergency_phase(squawk)
            return DispatchDecision(
                should_invoke_llm=True,
                reason=f"Squawk 7700 (emergency) on {callsign} — {phase}",
                urgency="EMERGENCY",
                data_summary=f"EMERGENCY RESPONSE: {callsign} squawking 7700 ({phase})",
            )

        if squawk == HIJACK_SQUAWK_CODE:
            phase = self.classify_emergency_phase(squawk)
            return DispatchDecision(
                should_invoke_llm=True,
                reason=f"Squawk 7500 (hijack) on {callsign} — {phase}",
                urgency="EMERGENCY",
                data_summary=f"HIJACK RESPONSE: {callsign} squawking 7500 ({phase})",
            )

        if squawk == RADIO_FAILURE_SQUAWK_CODE:
            phase = self.classify_emergency_phase(squawk)
            return DispatchDecision(
                should_invoke_llm=True,
                reason=f"Squawk 7600 (radio failure) on {callsign} — {phase}",
                urgency="URGENT",
                data_summary=f"RADIO FAILURE: {callsign} squawking 7600 ({phase})",
            )

        return None

    def classify_emergency_phase(self, squawk_code: str) -> str:
        """Map squawk code to ICAO emergency phase.

        Args:
            squawk_code: 4-digit transponder code.

        Returns:
            ICAO emergency phase string: "distress", "alert", or "uncertainty".
        """
        if squawk_code in EMERGENCY_SQUAWKS:
            return "distress"

        if squawk_code in URGENT_SQUAWKS:
            return "alert"

        return "uncertainty"
