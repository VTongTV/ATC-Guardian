"""Unit tests for shared.detector — deterministic conflict/emergency/weather detection.

These verify the rule-based layer that populates RadarSnapshot advisory
arrays without any LLM or Band calls.
"""

from datetime import datetime, timezone

from shared.detector import (
    detect_conflicts,
    detect_emergencies,
    detect_weather_hazards,
)
from shared.models import (
    AircraftState,
    AlertSeverity,
    EmergencyPhase,
    PositionGeographic,
    SIGMET,
    SIGMETGeometry,
)


def _aircraft(
    callsign: str = "UAL123",
    lat: float = 40.55,
    lon: float = -74.05,
    alt: int = 35000,
    heading: float = 58.0,
    speed: float = 460.0,
    squawk: str = "4321",
    vs: int = 0,
) -> AircraftState:
    """Build a minimal AircraftState for detector tests."""
    return AircraftState(
        callsign=callsign,
        latitude=lat,
        longitude=lon,
        altitude_ft=alt,
        heading_deg=heading,
        speed_kts=speed,
        vertical_speed_fpm=vs,
        squawk=squawk,
        timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# detect_conflicts
# ---------------------------------------------------------------------------


class TestDetectConflicts:
    """Tests for detect_conflicts."""

    def test_converging_pair_produces_advisory(self) -> None:
        """Two aircraft on converging courses at the same altitude conflict."""
        a = _aircraft("UAL123", lat=40.55, lon=-74.05, heading=58.0)
        b = _aircraft("DAL456", lat=40.72, lon=-73.50, heading=238.0)
        results = detect_conflicts([a, b])

        assert len(results) == 1
        advisory = results[0]
        pair = {advisory.cpa.aircraft_a_callsign, advisory.cpa.aircraft_b_callsign}
        assert pair == {"UAL123", "DAL456"}
        assert advisory.cpa.is_conflict is True
        assert len(advisory.resolution_hints) >= 1

    def test_well_separated_aircraft_produce_no_conflicts(self) -> None:
        """Aircraft far apart at different altitudes produce no advisories."""
        a = _aircraft("AAA", lat=40.0, lon=-74.0, alt=35000)
        b = _aircraft("BBB", lat=41.0, lon=-73.0, alt=20000)
        assert detect_conflicts([a, b]) == []

    def test_severity_escalates_with_proximity(self) -> None:
        """A head-on collision course yields at least WARNING severity."""
        # Same point, opposite headings → near-zero CPA
        a = _aircraft("AAA", lat=40.6, lon=-73.7, heading=0.0)
        b = _aircraft("BBB", lat=40.61, lon=-73.7, heading=180.0)
        results = detect_conflicts([a, b])
        assert len(results) == 1
        assert results[0].severity in {AlertSeverity.WARNING, AlertSeverity.CRITICAL}


# ---------------------------------------------------------------------------
# detect_emergencies
# ---------------------------------------------------------------------------


class TestDetectEmergencies:
    """Tests for detect_emergencies."""

    def test_squawk_7700_triggers_distress(self) -> None:
        """Squawk 7700 produces a DISTRESS-phase emergency declaration."""
        ac = _aircraft("SWA770", squawk="7700", vs=-1500)
        results = detect_emergencies([ac])

        assert len(results) == 1
        emrg = results[0]
        assert emrg.callsign == "SWA770"
        assert emrg.squawk_code == "7700"
        assert emrg.phase == EmergencyPhase.DISTRESS
        assert emrg.priority == AlertSeverity.CRITICAL

    def test_squawk_7500_triggers_distress(self) -> None:
        """Squawk 7500 (hijack) produces a DISTRESS-phase emergency."""
        ac = _aircraft("HJK", squawk="7500")
        results = detect_emergencies([ac])

        assert len(results) == 1
        assert results[0].phase == EmergencyPhase.DISTRESS

    def test_squawk_7600_triggers_alert_phase(self) -> None:
        """Squawk 7600 (radio failure) produces an ALERT-phase emergency."""
        ac = _aircraft("RDO", squawk="7600")
        results = detect_emergencies([ac])

        assert len(results) == 1
        assert results[0].phase == EmergencyPhase.ALERT

    def test_normal_squawk_produces_no_emergency(self) -> None:
        """A normal squawk code produces no emergency declaration."""
        ac = _aircraft("OK", squawk="1200")
        assert detect_emergencies([ac]) == []


# ---------------------------------------------------------------------------
# detect_weather_hazards
# ---------------------------------------------------------------------------


def _sigmet(points: list[tuple[float, float]], buffer_nm: float = 10.0) -> SIGMET:
    """Build a minimal SIGMET over the given polygon for weather tests."""
    now = datetime.now(timezone.utc)
    return SIGMET(
        sigmet_id="SIGM-T",
        phenomenon="SEV_TURB",
        severity=AlertSeverity.WARNING,
        geometry=SIGMETGeometry(
            points=[PositionGeographic(latitude=la, longitude=lo) for la, lo in points],
            buffer_nm=buffer_nm,
        ),
        base_ft=18000,
        top_ft=26000,
        valid_from=now,
        valid_to=now,
    )


class TestDetectWeatherHazards:
    """Tests for detect_weather_hazards."""

    def test_aircraft_inside_polygon_is_flagged(self) -> None:
        """An aircraft inside the SIGMET polygon is in the affected list."""
        sigmet = _sigmet(
            [(40.0, -74.0), (40.0, -73.0), (39.5, -73.5)], buffer_nm=0.0
        )
        inside = _aircraft("IN", lat=39.8, lon=-73.6)
        outside = _aircraft("OUT", lat=41.5, lon=-72.0)

        results = detect_weather_hazards([sigmet], [inside, outside])
        assert len(results) == 1
        assert "IN" in results[0].affected_callsigns
        assert "OUT" not in results[0].affected_callsigns

    def test_buffer_zone_catches_nearby_aircraft(self) -> None:
        """An aircraft just outside the polygon but inside the buffer is flagged."""
        sigmet = _sigmet(
            [(40.0, -74.0), (40.0, -73.0), (39.5, -73.5)], buffer_nm=10.0
        )
        nearby = _aircraft("NEAR", lat=40.05, lon=-73.6)
        results = detect_weather_hazards([sigmet], [nearby])
        assert len(results) == 1
        assert "NEAR" in results[0].affected_callsigns

    def test_sigmet_with_no_affected_aircraft_is_skipped(self) -> None:
        """A SIGMET over empty airspace produces no advisory."""
        sigmet = _sigmet(
            [(40.0, -74.0), (40.0, -73.0), (39.5, -73.5)], buffer_nm=0.0
        )
        far = _aircraft("FAR", lat=45.0, lon=-60.0)
        assert detect_weather_hazards([sigmet], [far]) == []

    def test_deviation_hints_reference_fl_band(self) -> None:
        """Deviation hints mention the SIGMET flight-level band."""
        sigmet = _sigmet(
            [(40.0, -74.0), (40.0, -73.0), (39.5, -73.5)], buffer_nm=0.0
        )
        inside = _aircraft("IN", lat=39.8, lon=-73.6)
        results = detect_weather_hazards([sigmet], [inside])
        joined = " ".join(results[0].deviation_hints)
        assert "FL180" in joined
        assert "FL260" in joined
