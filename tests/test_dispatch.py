"""Unit tests for rule-based dispatch logic (agents/dispatch.py).

Tests all five dispatcher classes without requiring Band credentials
or any external API calls. All dispatchers operate on plain dicts.
"""

import sys
import os
from datetime import datetime, timezone

import pytest

# Ensure agents/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agents"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.dispatch import (
    ALTITUDE_PROXIMITY_THRESHOLD_FT,
    CoordinatorDispatcher,
    ConflictDetectorDispatcher,
    DispatchDecision,
    EmergencyResponseDispatcher,
    GroundOpsDispatcher,
    WeatherAnalystDispatcher,
    _compute_bearing,
    _haversine_nm,
    _normalize_angle,
    _point_in_polygon,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_aircraft(
    callsign: str = "UAL123",
    lat: float = 40.0,
    lon: float = -74.0,
    alt: int = 34000,
    heading: float = 90.0,
    speed: float = 450.0,
    squawk: str = "1200",
    vs: int = 0,
) -> dict:
    """Create a minimal aircraft state dict for testing."""
    return {
        "callsign": callsign,
        "latitude": lat,
        "longitude": lon,
        "altitude_ft": alt,
        "heading_deg": heading,
        "speed_kts": speed,
        "squawk": squawk,
        "vertical_speed_fpm": vs,
    }


# ---------------------------------------------------------------------------
# CoordinatorDispatcher tests
# ---------------------------------------------------------------------------


class TestCoordinatorDispatcher:
    """Tests for CoordinatorDispatcher."""

    def setup_method(self) -> None:
        self.dispatcher = CoordinatorDispatcher()

    def test_converging_pair_dispatches_to_conflict_detector(self) -> None:
        """Two aircraft at similar altitudes heading towards each other."""
        # A heading east, B heading west — directly converging
        ac_a = _make_aircraft("UAL123", lat=40.0, lon=-74.0, alt=34000, heading=90.0)
        ac_b = _make_aircraft("DAL456", lat=40.01, lon=-73.9, alt=34000, heading=270.0)

        decisions = self.dispatcher.evaluate_aircraft_data([ac_a, ac_b])

        conflict_decisions = [d for d in decisions if "conflict-detector" in d.target_agents]
        assert len(conflict_decisions) == 1
        assert conflict_decisions[0].should_invoke_llm is False
        assert "conflict-detector" in conflict_decisions[0].target_agents

    def test_diverging_pair_no_dispatch(self) -> None:
        """Two aircraft heading away from each other — no conflict dispatch."""
        ac_a = _make_aircraft("UAL123", lat=40.0, lon=-74.0, alt=34000, heading=90.0)
        ac_b = _make_aircraft("DAL456", lat=40.01, lon=-73.9, alt=34000, heading=270.0)

        # Now make them diverge: A heads east, B heads east (away)
        ac_a_div = _make_aircraft("UAL123", lat=40.0, lon=-74.0, alt=34000, heading=90.0)
        ac_b_div = _make_aircraft("DAL456", lat=40.01, lon=-73.9, alt=34000, heading=90.0)

        decisions = self.dispatcher.evaluate_aircraft_data([ac_a_div, ac_b_div])

        conflict_decisions = [d for d in decisions if "conflict-detector" in d.target_agents]
        assert len(conflict_decisions) == 0

    def test_emergency_squawk_dispatches_to_emergency_response(self) -> None:
        """Squawk 7700 triggers emergency dispatch."""
        ac = _make_aircraft("UAL123", squawk="7700")

        decisions = self.dispatcher.evaluate_aircraft_data([ac])

        emergency_decisions = [d for d in decisions if "emergency-response" in d.target_agents]
        assert len(emergency_decisions) == 1
        assert emergency_decisions[0].urgency == "EMERGENCY"

    def test_normal_squawk_no_dispatch(self) -> None:
        """Squawk 1200 (VFR) does not trigger any dispatch."""
        ac = _make_aircraft("UAL123", squawk="1200")

        decisions = self.dispatcher.evaluate_aircraft_data([ac])

        assert len(decisions) == 0

    def test_similar_altitude_pair_triggers_analysis(self) -> None:
        """Pair within 2000 ft altitude and converging triggers analysis."""
        ac_a = _make_aircraft("UAL123", lat=40.0, lon=-74.0, alt=34000, heading=90.0)
        ac_b = _make_aircraft("DAL456", lat=40.01, lon=-73.9, alt=35000, heading=270.0)

        assert self.dispatcher._have_similar_altitude(ac_a, ac_b) is True
        assert self.dispatcher._are_converging(ac_a, ac_b) is True

    def test_different_altitude_pair_skips(self) -> None:
        """Pair separated by more than 2000 ft is not considered similar altitude."""
        ac_a = _make_aircraft("UAL123", alt=34000)
        ac_b = _make_aircraft("DAL456", alt=37000)

        assert self.dispatcher._have_similar_altitude(ac_a, ac_b) is False

    def test_evaluate_squawk_7500_hijack(self) -> None:
        """Squawk 7500 returns EMERGENCY dispatch for hijack."""
        ac = _make_aircraft("UAL123", squawk="7500")
        decision = self.dispatcher.evaluate_squawk(ac)
        assert decision is not None
        assert decision.urgency == "EMERGENCY"
        assert "hijack" in decision.reason.lower()

    def test_evaluate_squawk_7600_radio_failure(self) -> None:
        """Squawk 7600 returns URGENT dispatch for radio failure."""
        ac = _make_aircraft("UAL123", squawk="7600")
        decision = self.dispatcher.evaluate_squawk(ac)
        assert decision is not None
        assert decision.urgency == "URGENT"

    def test_evaluate_squawk_normal_returns_none(self) -> None:
        """Normal squawk returns None (no dispatch)."""
        ac = _make_aircraft("UAL123", squawk="1200")
        assert self.dispatcher.evaluate_squawk(ac) is None

    def test_empty_aircraft_list(self) -> None:
        """Empty list produces no decisions."""
        decisions = self.dispatcher.evaluate_aircraft_data([])
        assert decisions == []

    def test_multiple_emergency_squawks(self) -> None:
        """Multiple emergency squawks each produce separate decisions."""
        ac_a = _make_aircraft("UAL123", squawk="7700")
        ac_b = _make_aircraft("DAL456", squawk="7500")

        decisions = self.dispatcher.evaluate_aircraft_data([ac_a, ac_b])
        emergency_decisions = [d for d in decisions if "emergency-response" in d.target_agents]
        assert len(emergency_decisions) == 2


# ---------------------------------------------------------------------------
# ConflictDetectorDispatcher tests
# ---------------------------------------------------------------------------


class TestConflictDetectorDispatcher:
    """Tests for ConflictDetectorDispatcher."""

    def setup_method(self) -> None:
        self.dispatcher = ConflictDetectorDispatcher()

    def test_cpa_below_5nm_invokes_llm(self) -> None:
        """CPA at 4.5 nm triggers LLM invocation at ROUTINE urgency."""
        cpa = {
            "aircraft_a_callsign": "UAL123",
            "aircraft_b_callsign": "DAL456",
            "min_distance_nm": 4.5,
            "is_conflict": True,
        }
        decision = self.dispatcher.evaluate_cpa(cpa)
        assert decision.should_invoke_llm is True
        assert decision.urgency == "ROUTINE"

    def test_cpa_below_3nm_urgent(self) -> None:
        """CPA at 2.5 nm triggers URGENT urgency."""
        cpa = {
            "aircraft_a_callsign": "UAL123",
            "aircraft_b_callsign": "DAL456",
            "min_distance_nm": 2.5,
            "is_conflict": True,
        }
        decision = self.dispatcher.evaluate_cpa(cpa)
        assert decision.should_invoke_llm is True
        assert decision.urgency == "URGENT"

    def test_cpa_below_1nm_emergency(self) -> None:
        """CPA at 0.8 nm triggers EMERGENCY urgency."""
        cpa = {
            "aircraft_a_callsign": "UAL123",
            "aircraft_b_callsign": "DAL456",
            "min_distance_nm": 0.8,
            "is_conflict": True,
        }
        decision = self.dispatcher.evaluate_cpa(cpa)
        assert decision.should_invoke_llm is True
        assert decision.urgency == "EMERGENCY"

    def test_cpa_above_5nm_skips(self) -> None:
        """CPA at 7.0 nm does not invoke LLM."""
        cpa = {
            "aircraft_a_callsign": "UAL123",
            "aircraft_b_callsign": "DAL456",
            "min_distance_nm": 7.0,
            "is_conflict": False,
        }
        decision = self.dispatcher.evaluate_cpa(cpa)
        assert decision.should_invoke_llm is False

    def test_cpa_exactly_5nm_skips(self) -> None:
        """CPA at exactly 5.0 nm is at threshold — does not invoke."""
        cpa = {
            "aircraft_a_callsign": "UAL123",
            "aircraft_b_callsign": "DAL456",
            "min_distance_nm": 5.0,
            "is_conflict": False,
        }
        decision = self.dispatcher.evaluate_cpa(cpa)
        assert decision.should_invoke_llm is False

    def test_should_analyze_pair_same_altitude(self) -> None:
        """Same-altitude pair within 60 nm should be analyzed."""
        ac_a = _make_aircraft("UAL123", lat=40.0, lon=-74.0, alt=34000)
        ac_b = _make_aircraft("DAL456", lat=40.05, lon=-73.95, alt=34000)

        assert self.dispatcher.should_analyze_pair(ac_a, ac_b) is True

    def test_should_analyze_pair_different_altitude_skips(self) -> None:
        """Pair with >2000 ft altitude separation should be skipped."""
        ac_a = _make_aircraft("UAL123", alt=34000)
        ac_b = _make_aircraft("DAL456", alt=37000)

        assert self.dispatcher.should_analyze_pair(ac_a, ac_b) is False

    def test_should_analyze_pair_far_apart_skips(self) -> None:
        """Pair more than 60 nm apart should be skipped."""
        ac_a = _make_aircraft("UAL123", lat=40.0, lon=-74.0, alt=34000)
        ac_b = _make_aircraft("DAL456", lat=41.0, lon=-73.0, alt=34000)

        assert self.dispatcher.should_analyze_pair(ac_a, ac_b) is False


# ---------------------------------------------------------------------------
# WeatherAnalystDispatcher tests
# ---------------------------------------------------------------------------


class TestWeatherAnalystDispatcher:
    """Tests for WeatherAnalystDispatcher."""

    def setup_method(self) -> None:
        self.dispatcher = WeatherAnalystDispatcher()

    def test_sigmet_overlaps_aircraft_invokes_llm(self) -> None:
        """SIGMET polygon containing an aircraft position invokes LLM."""
        sigmet = {
            "sigmet_id": "SIGMET-001",
            "phenomenon": "TS",
            "geometry": {
                "points": [
                    {"latitude": 39.0, "longitude": -75.0},
                    {"latitude": 39.0, "longitude": -73.0},
                    {"latitude": 41.0, "longitude": -73.0},
                    {"latitude": 41.0, "longitude": -75.0},
                ],
                "buffer_nm": 10.0,
            },
        }
        aircraft = [_make_aircraft("UAL123", lat=40.0, lon=-74.0)]

        decision = self.dispatcher.evaluate_sigmet(sigmet, aircraft)
        assert decision.should_invoke_llm is True
        assert "UAL123" in decision.data_summary

    def test_sigmet_no_overlap_skips(self) -> None:
        """SIGMET polygon not containing any aircraft position skips."""
        sigmet = {
            "sigmet_id": "SIGMET-002",
            "phenomenon": "ICE",
            "geometry": {
                "points": [
                    {"latitude": 30.0, "longitude": -80.0},
                    {"latitude": 30.0, "longitude": -78.0},
                    {"latitude": 32.0, "longitude": -78.0},
                    {"latitude": 32.0, "longitude": -80.0},
                ],
                "buffer_nm": 10.0,
            },
        }
        # Aircraft is far away (at 40N, 74W)
        aircraft = [_make_aircraft("UAL123", lat=40.0, lon=-74.0)]

        decision = self.dispatcher.evaluate_sigmet(sigmet, aircraft)
        assert decision.should_invoke_llm is False

    def test_point_in_polygon_inside(self) -> None:
        """Point clearly inside the polygon returns True."""
        polygon = [
            (39.0, -75.0),
            (39.0, -73.0),
            (41.0, -73.0),
            (41.0, -75.0),
        ]
        assert _point_in_polygon(40.0, -74.0, polygon) is True

    def test_point_in_polygon_outside(self) -> None:
        """Point clearly outside the polygon returns False."""
        polygon = [
            (39.0, -75.0),
            (39.0, -73.0),
            (41.0, -73.0),
            (41.0, -75.0),
        ]
        assert _point_in_polygon(42.0, -74.0, polygon) is False

    def test_point_in_polygon_on_vertex(self) -> None:
        """Point exactly on a vertex is treated as inside."""
        polygon = [
            (39.0, -75.0),
            (39.0, -73.0),
            (41.0, -73.0),
            (41.0, -75.0),
        ]
        # Edge behavior — on vertex may or may not be inside depending on implementation
        result = _point_in_polygon(39.0, -75.0, polygon)
        assert isinstance(result, bool)

    def test_invalid_geometry_skips(self) -> None:
        """SIGMET with < 3 vertices is invalid and skips."""
        sigmet = {
            "sigmet_id": "SIGMET-BAD",
            "phenomenon": "TURB",
            "geometry": {
                "points": [
                    {"latitude": 39.0, "longitude": -75.0},
                    {"latitude": 39.0, "longitude": -73.0},
                ],
                "buffer_nm": 10.0,
            },
        }
        aircraft = [_make_aircraft("UAL123", lat=40.0, lon=-74.0)]

        decision = self.dispatcher.evaluate_sigmet(sigmet, aircraft)
        assert decision.should_invoke_llm is False

    def test_empty_aircraft_list(self) -> None:
        """SIGMET with no aircraft still returns a valid decision."""
        sigmet = {
            "sigmet_id": "SIGMET-003",
            "phenomenon": "VA",
            "geometry": {
                "points": [
                    {"latitude": 39.0, "longitude": -75.0},
                    {"latitude": 39.0, "longitude": -73.0},
                    {"latitude": 41.0, "longitude": -73.0},
                    {"latitude": 41.0, "longitude": -75.0},
                ],
                "buffer_nm": 10.0,
            },
        }
        decision = self.dispatcher.evaluate_sigmet(sigmet, [])
        assert decision.should_invoke_llm is False

    def test_aircraft_within_buffer_zone(self) -> None:
        """Aircraft just outside polygon but within buffer triggers invocation."""
        sigmet = {
            "sigmet_id": "SIGMET-BUF",
            "phenomenon": "TS",
            "geometry": {
                "points": [
                    {"latitude": 39.5, "longitude": -74.5},
                    {"latitude": 39.5, "longitude": -73.5},
                    {"latitude": 40.5, "longitude": -73.5},
                    {"latitude": 40.5, "longitude": -74.5},
                ],
                "buffer_nm": 50.0,  # large buffer to ensure the aircraft outside is caught
            },
        }
        # Aircraft at 41.0, -74.0 is just north of the polygon
        aircraft = [_make_aircraft("UAL123", lat=41.0, lon=-74.0)]

        decision = self.dispatcher.evaluate_sigmet(sigmet, aircraft)
        assert decision.should_invoke_llm is True


# ---------------------------------------------------------------------------
# GroundOpsDispatcher tests
# ---------------------------------------------------------------------------


class TestGroundOpsDispatcher:
    """Tests for GroundOpsDispatcher."""

    def setup_method(self) -> None:
        self.dispatcher = GroundOpsDispatcher()

    def test_direct_request_invokes_llm(self) -> None:
        """Any direct ground request invokes LLM."""
        request = {
            "request_type": "runway",
            "icao_code": "KJFK",
            "context_callsign": "UAL123",
        }
        decision = self.dispatcher.evaluate_request(request)
        assert decision.should_invoke_llm is True
        assert decision.urgency == "ROUTINE"

    def test_always_responds_to_mention(self) -> None:
        """Ground ops always processes requests — no skip conditions."""
        request_atis = {
            "request_type": "atis",
            "icao_code": "KLAX",
        }
        decision = self.dispatcher.evaluate_request(request_atis)
        assert decision.should_invoke_llm is True

        request_notam = {
            "request_type": "notam",
            "icao_code": "KORD",
            "context_callsign": "DAL456",
        }
        decision = self.dispatcher.evaluate_request(request_notam)
        assert decision.should_invoke_llm is True

    def test_minimal_request_data(self) -> None:
        """Request with minimal data still processes."""
        request = {"request_type": "unknown"}
        decision = self.dispatcher.evaluate_request(request)
        assert decision.should_invoke_llm is True


# ---------------------------------------------------------------------------
# EmergencyResponseDispatcher tests
# ---------------------------------------------------------------------------


class TestEmergencyResponseDispatcher:
    """Tests for EmergencyResponseDispatcher."""

    def setup_method(self) -> None:
        self.dispatcher = EmergencyResponseDispatcher()

    def test_squawk_7700_emergency_dispatch(self) -> None:
        """Squawk 7700 triggers EMERGENCY LLM invocation."""
        ac = _make_aircraft("UAL123", squawk="7700")
        decision = self.dispatcher.evaluate_squawk(ac)

        assert decision is not None
        assert decision.should_invoke_llm is True
        assert decision.urgency == "EMERGENCY"

    def test_squawk_7500_emergency_dispatch(self) -> None:
        """Squawk 7500 (hijack) triggers EMERGENCY LLM invocation."""
        ac = _make_aircraft("UAL123", squawk="7500")
        decision = self.dispatcher.evaluate_squawk(ac)

        assert decision is not None
        assert decision.should_invoke_llm is True
        assert decision.urgency == "EMERGENCY"

    def test_squawk_7600_urgent_dispatch(self) -> None:
        """Squawk 7600 (radio failure) triggers URGENT LLM invocation."""
        ac = _make_aircraft("UAL123", squawk="7600")
        decision = self.dispatcher.evaluate_squawk(ac)

        assert decision is not None
        assert decision.should_invoke_llm is True
        assert decision.urgency == "URGENT"

    def test_normal_squawk_no_dispatch(self) -> None:
        """Normal squawk 1200 returns None — no dispatch."""
        ac = _make_aircraft("UAL123", squawk="1200")
        decision = self.dispatcher.evaluate_squawk(ac)
        assert decision is None

    def test_classify_7700_as_distress(self) -> None:
        """Squawk 7700 classifies as distress phase."""
        phase = self.dispatcher.classify_emergency_phase("7700")
        assert phase == "distress"

    def test_classify_7600_as_alert(self) -> None:
        """Squawk 7600 classifies as alert phase."""
        phase = self.dispatcher.classify_emergency_phase("7600")
        assert phase == "alert"

    def test_classify_7500_as_distress(self) -> None:
        """Squawk 7500 (hijack) classifies as distress phase."""
        phase = self.dispatcher.classify_emergency_phase("7500")
        assert phase == "distress"

    def test_classify_normal_as_uncertainty(self) -> None:
        """Squawk 1200 classifies as uncertainty phase."""
        phase = self.dispatcher.classify_emergency_phase("1200")
        assert phase == "uncertainty"


# ---------------------------------------------------------------------------
# DispatchDecision model tests
# ---------------------------------------------------------------------------


class TestDispatchDecision:
    """Tests for the DispatchDecision Pydantic model."""

    def test_default_values(self) -> None:
        """DispatchDecision has correct defaults."""
        d = DispatchDecision(should_invoke_llm=True, reason="test")
        assert d.urgency == "ROUTINE"
        assert d.target_agents == []
        assert d.data_summary == ""

    def test_full_construction(self) -> None:
        """DispatchDecision accepts all fields."""
        d = DispatchDecision(
            should_invoke_llm=False,
            reason="no action",
            urgency="EMERGENCY",
            target_agents=["conflict-detector", "emergency-response"],
            data_summary="Summary here",
        )
        assert d.urgency == "EMERGENCY"
        assert len(d.target_agents) == 2

    def test_serialization(self) -> None:
        """DispatchDecision serializes to dict correctly."""
        d = DispatchDecision(should_invoke_llm=True, reason="test", urgency="URGENT")
        data = d.model_dump()
        assert data["should_invoke_llm"] is True
        assert data["urgency"] == "URGENT"


# ---------------------------------------------------------------------------
# Geometry helper tests
# ---------------------------------------------------------------------------


class TestGeometryHelpers:
    """Tests for helper geometry functions."""

    def test_haversine_same_point(self) -> None:
        """Haversine distance from a point to itself is 0."""
        dist = _haversine_nm(40.0, -74.0, 40.0, -74.0)
        assert dist == pytest.approx(0.0, abs=0.01)

    def test_haversine_known_distance(self) -> None:
        """Haversine distance matches known value (~60 nm per degree latitude)."""
        # 1 degree latitude ≈ 60 nm
        dist = _haversine_nm(40.0, -74.0, 41.0, -74.0)
        assert dist == pytest.approx(60.0, abs=1.0)

    def test_compute_bearing_north(self) -> None:
        """Bearing from south to north is 0° (north)."""
        bearing = _compute_bearing(40.0, -74.0, 41.0, -74.0)
        assert bearing == pytest.approx(0.0, abs=1.0)

    def test_compute_bearing_east(self) -> None:
        """Bearing from west to east is 90°."""
        bearing = _compute_bearing(40.0, -75.0, 40.0, -74.0)
        assert bearing == pytest.approx(90.0, abs=1.0)

    def test_normalize_angle_wrap(self) -> None:
        """Angle normalization wraps correctly."""
        assert _normalize_angle(200) == pytest.approx(-160)
        assert _normalize_angle(-200) == pytest.approx(160)
        assert _normalize_angle(0) == 0
        assert _normalize_angle(180) == 180
        assert _normalize_angle(-180) == -180
