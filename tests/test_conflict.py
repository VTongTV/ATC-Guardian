"""Unit tests for ml.conflict — CPA calculation and conflict detection."""

from datetime import datetime, timezone

import pytest

from shared.models import AircraftState, CPAResult
from ml.conflict import compute_cpa, scan_pairwise_conflicts


def _make_aircraft(
    callsign: str = "TEST001",
    latitude: float = 40.0,
    longitude: float = -74.0,
    altitude_ft: int = 35000,
    heading_deg: float = 0.0,
    speed_kts: float = 450.0,
    vertical_speed_fpm: int = 0,
    squawk: str = "1200",
) -> AircraftState:
    """Create an AircraftState with sensible defaults for testing."""
    return AircraftState(
        callsign=callsign,
        latitude=latitude,
        longitude=longitude,
        altitude_ft=altitude_ft,
        heading_deg=heading_deg,
        speed_kts=speed_kts,
        vertical_speed_fpm=vertical_speed_fpm,
        squawk=squawk,
        timestamp=datetime.now(timezone.utc),
    )


class TestComputeCPA:
    """Tests for compute_cpa."""

    def test_converging_aircraft_conflict(self) -> None:
        """Two aircraft flying towards each other at same altitude must conflict."""
        # Aircraft A flying NE at FL350 — close enough to close within 5 min
        aircraft_a = _make_aircraft(
            callsign="UAL123",
            latitude=40.65,
            longitude=-74.10,
            altitude_ft=35000,
            heading_deg=45.0,
            speed_kts=450,
        )
        # Aircraft B flying SW at FL350 — head-on, close by
        aircraft_b = _make_aircraft(
            callsign="DAL456",
            latitude=40.68,
            longitude=-73.95,
            altitude_ft=35000,
            heading_deg=225.0,
            speed_kts=460,
        )

        result = compute_cpa(aircraft_a, aircraft_b)

        assert isinstance(result, CPAResult)
        assert result.aircraft_a_callsign == "UAL123"
        assert result.aircraft_b_callsign == "DAL456"
        assert result.time_to_cpa_seconds > 0
        # Converging head-on at same altitude should be a conflict
        assert result.is_conflict is True
        assert result.altitude_separation_ft == 0

    def test_diverging_aircraft_no_conflict(self) -> None:
        """Two aircraft flying apart on parallel tracks should not conflict."""
        # Aircraft A flying east at FL350
        aircraft_a = _make_aircraft(
            callsign="UAL123",
            latitude=40.00,
            longitude=-74.00,
            altitude_ft=35000,
            heading_deg=90.0,
            speed_kts=450,
        )
        # Aircraft B flying west from same area but offset south
        aircraft_b = _make_aircraft(
            callsign="DAL456",
            latitude=38.00,
            longitude=-74.00,
            altitude_ft=35000,
            heading_deg=270.0,
            speed_kts=450,
        )

        result = compute_cpa(aircraft_a, aircraft_b)

        # They are 120 nm apart and flying opposite directions on parallel tracks
        assert result.min_distance_nm > 0
        assert result.is_conflict is False

    def test_vertical_separation_prevents_conflict(self) -> None:
        """Two aircraft on converging headings but 2000 ft apart should NOT conflict."""
        aircraft_a = _make_aircraft(
            callsign="UAL123",
            latitude=40.60,
            longitude=-74.20,
            altitude_ft=35000,
            heading_deg=45.0,
            speed_kts=450,
        )
        aircraft_b = _make_aircraft(
            callsign="DAL456",
            latitude=40.70,
            longitude=-73.90,
            altitude_ft=37000,
            heading_deg=225.0,
            speed_kts=460,
        )

        result = compute_cpa(aircraft_a, aircraft_b)

        # Horizontal distance may be small but vertical separation is 2000 ft
        assert result.altitude_separation_ft >= 2000
        assert result.is_conflict is False

    def test_result_has_correct_callsigns(self) -> None:
        """CPA result must preserve the order of input callsigns."""
        aircraft_a = _make_aircraft(callsign="AAL100")
        aircraft_b = _make_aircraft(callsign="BAW200")

        result = compute_cpa(aircraft_a, aircraft_b)

        assert result.aircraft_a_callsign == "AAL100"
        assert result.aircraft_b_callsign == "BAW200"

    def test_cpa_distance_is_non_negative(self) -> None:
        """CPA distance must always be >= 0."""
        aircraft_a = _make_aircraft(callsign="A", latitude=40.0, longitude=-74.0, heading_deg=90.0)
        aircraft_b = _make_aircraft(callsign="B", latitude=41.0, longitude=-73.0, heading_deg=270.0)

        result = compute_cpa(aircraft_a, aircraft_b)

        assert result.min_distance_nm >= 0

    def test_time_to_cpa_is_non_negative(self) -> None:
        """Time to CPA must always be >= 0."""
        aircraft_a = _make_aircraft(callsign="A", heading_deg=0.0)
        aircraft_b = _make_aircraft(callsign="B", latitude=41.0, heading_deg=180.0)

        result = compute_cpa(aircraft_a, aircraft_b)

        assert result.time_to_cpa_seconds >= 0


class TestScanPairwiseConflicts:
    """Tests for scan_pairwise_conflicts."""

    def test_empty_list_returns_no_conflicts(self) -> None:
        """No aircraft means no conflicts."""
        result = scan_pairwise_conflicts([])
        assert result == []

    def test_single_aircraft_no_conflict(self) -> None:
        """One aircraft cannot conflict with itself."""
        aircraft = [_make_aircraft(callsign="SOLO1")]
        result = scan_pairwise_conflicts(aircraft)
        assert result == []

    def test_two_diverging_aircraft_no_conflict(self) -> None:
        """Two diverging aircraft on parallel tracks should not produce a conflict."""
        aircraft = [
            _make_aircraft(callsign="A", latitude=40.0, heading_deg=90.0),
            _make_aircraft(callsign="B", latitude=38.0, heading_deg=270.0),
        ]
        result = scan_pairwise_conflicts(aircraft)
        assert result == []
