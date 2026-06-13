"""Unit tests for ml.trajectory — great-circle math and position extrapolation."""

import math
from datetime import datetime, timezone

import pytest

from shared.models import AircraftState, PositionGeographic
from ml.trajectory import (
    compute_bearing,
    extrapolate_position,
    haversine_distance_nm,
)


def _make_aircraft(
    callsign: str = "TEST001",
    latitude: float = 40.0,
    longitude: float = -74.0,
    altitude_ft: int = 35000,
    heading_deg: float = 0.0,
    speed_kts: float = 450.0,
    vertical_speed_fpm: int = 0,
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
        timestamp=datetime.now(timezone.utc),
    )


class TestHaversineDistance:
    """Tests for haversine_distance_nm."""

    def test_same_point_returns_zero(self) -> None:
        """Distance between a point and itself must be zero."""
        dist = haversine_distance_nm(40.0, -74.0, 40.0, -74.0)
        assert dist == pytest.approx(0.0, abs=0.01)

    def test_known_distance_jfk_lhr(self) -> None:
        """JFK (40.64, -73.78) to LHR (51.47, -0.46) ≈ 3004 nm."""
        dist = haversine_distance_nm(40.64, -73.78, 51.47, -0.46)
        assert dist == pytest.approx(3004.0, rel=0.01)

    def test_short_distance(self) -> None:
        """Two points 1 nm apart at the equator."""
        # 1 nm = 1/60 degree at equator
        dist = haversine_distance_nm(0.0, 0.0, 0.0, 1.0 / 60.0)
        assert dist == pytest.approx(1.0, abs=0.05)

    def test_antipodal_points(self) -> None:
        """Distance between antipodal points must be half Earth circumference."""
        dist = haversine_distance_nm(0.0, 0.0, 0.0, 180.0)
        expected = math.pi * 3440.065  # pi * Earth radius in nm
        assert dist == pytest.approx(expected, rel=0.001)


class TestExtrapolatePosition:
    """Tests for extrapolate_position."""

    def test_heading_north_increases_latitude(self) -> None:
        """Flying north at 450 kts for 1 minute should increase latitude."""
        aircraft = _make_aircraft(latitude=40.0, heading_deg=0.0, speed_kts=450.0)
        pos = extrapolate_position(aircraft, delta_seconds=60.0)

        assert pos.latitude > 40.0
        assert pos.longitude == pytest.approx(-74.0, abs=0.01)

    def test_heading_east_increases_longitude(self) -> None:
        """Flying east at 450 kts for 1 minute should increase longitude."""
        aircraft = _make_aircraft(latitude=0.0, longitude=0.0, heading_deg=90.0, speed_kts=450.0)
        pos = extrapolate_position(aircraft, delta_seconds=60.0)

        assert pos.longitude > 0.0
        assert pos.latitude == pytest.approx(0.0, abs=0.01)

    def test_climbing_aircraft_altitude_increases(self) -> None:
        """A climbing aircraft should have higher altitude after extrapolation."""
        aircraft = _make_aircraft(altitude_ft=30000, vertical_speed_fpm=2000)
        pos = extrapolate_position(aircraft, delta_seconds=60.0)

        assert pos.altitude_ft is not None
        assert pos.altitude_ft > 30000

    def test_descending_aircraft_altitude_decreases(self) -> None:
        """A descending aircraft should have lower altitude after extrapolation."""
        aircraft = _make_aircraft(altitude_ft=30000, vertical_speed_fpm=-1500)
        pos = extrapolate_position(aircraft, delta_seconds=60.0)

        assert pos.altitude_ft is not None
        assert pos.altitude_ft < 30000

    def test_altitude_floor_at_zero(self) -> None:
        """Altitude must never go below 0 (ground)."""
        aircraft = _make_aircraft(altitude_ft=100, vertical_speed_fpm=-5000)
        pos = extrapolate_position(aircraft, delta_seconds=120.0)

        assert pos.altitude_ft == 0

    def test_zero_delta_returns_current_position(self) -> None:
        """With delta_seconds=0, position should not change."""
        aircraft = _make_aircraft(latitude=40.0, longitude=-74.0, altitude_ft=35000)
        pos = extrapolate_position(aircraft, delta_seconds=0.0)

        assert pos.latitude == pytest.approx(40.0, abs=0.001)
        assert pos.longitude == pytest.approx(-74.0, abs=0.001)
        assert pos.altitude_ft == 35000


class TestComputeBearing:
    """Tests for compute_bearing."""

    def test_due_north(self) -> None:
        """Bearing from equator to north pole must be 0°."""
        bearing = compute_bearing(0.0, 0.0, 45.0, 0.0)
        assert bearing == pytest.approx(0.0, abs=0.5)

    def test_due_east(self) -> None:
        """Bearing from equator going east must be 90°."""
        bearing = compute_bearing(0.0, 0.0, 0.0, 45.0)
        assert bearing == pytest.approx(90.0, abs=0.5)

    def test_due_south(self) -> None:
        """Bearing going due south must be 180°."""
        bearing = compute_bearing(45.0, 0.0, 0.0, 0.0)
        assert bearing == pytest.approx(180.0, abs=0.5)

    def test_due_west(self) -> None:
        """Bearing going due west must be 270°."""
        bearing = compute_bearing(0.0, 45.0, 0.0, 0.0)
        assert bearing == pytest.approx(270.0, abs=0.5)
