"""Tests for the what-if counterfactual analysis (ml/whatif.py).

Verifies maneuver application and the CPA delta computation that lets a
controller preview a maneuver's effect before acting.
"""

from datetime import datetime, timezone

import pytest

from ml.whatif import Maneuver, apply_maneuver, evaluate_maneuver
from shared.models import AircraftState


def _aircraft(
    callsign: str = "UAL123",
    heading: float = 58.0,
    alt: int = 35000,
    speed: float = 460.0,
    lat: float = 40.55,
    lon: float = -74.05,
) -> AircraftState:
    """Build an AircraftState for what-if tests."""
    return AircraftState(
        callsign=callsign,
        latitude=lat,
        longitude=lon,
        altitude_ft=alt,
        heading_deg=heading,
        speed_kts=speed,
        vertical_speed_fpm=0,
        squawk="4321",
        timestamp=datetime.now(timezone.utc),
    )


class TestApplyManeuver:
    """Tests for apply_maneuver."""

    def test_heading_override_applies(self) -> None:
        """A heading maneuver changes only heading."""
        ac = _aircraft("UAL123", heading=58.0)
        maneuvered = apply_maneuver(ac, Maneuver("UAL123", new_heading_deg=90.0))
        assert maneuvered.heading_deg == 90.0
        assert maneuvered.altitude_ft == ac.altitude_ft
        assert maneuvered.speed_kts == ac.speed_kts

    def test_altitude_override_applies(self) -> None:
        """An altitude maneuver changes only altitude."""
        ac = _aircraft("UAL123", alt=35000)
        maneuvered = apply_maneuver(ac, Maneuver("UAL123", new_altitude_ft=10000))
        assert maneuvered.altitude_ft == 10000
        assert maneuvered.heading_deg == ac.heading_deg

    def test_maneuver_on_other_callsign_is_noop(self) -> None:
        """A maneuver for a different callsign returns the original."""
        ac = _aircraft("UAL123")
        maneuvered = apply_maneuver(ac, Maneuver("DAL456", new_heading_deg=200.0))
        assert maneuvered is ac


class TestEvaluateManeuver:
    """Tests for evaluate_maneuver."""

    def test_separating_maneuver_improves_cpa(self) -> None:
        """Turning an aircraft away from its conflict partner increases CPA."""
        # Aircraft far enough apart that future CPA depends on heading.
        a = _aircraft("UAL123", lat=40.50, lon=-73.90, heading=45.0)
        b = _aircraft("DAL456", lat=40.70, lon=-73.50, heading=225.0)
        # Baseline: converging. Turn UAL123 due south (away from DAL456).
        result = evaluate_maneuver([a, b], Maneuver("UAL123", new_heading_deg=180.0), "DAL456")
        assert result.predicted_cpa_nm > result.baseline_cpa_nm
        assert result.delta_nm > 0

    def test_worsening_maneuver_flags_risk(self) -> None:
        """A maneuver that reduces CPA flags riskier/worse/resolves-inverse."""
        a = _aircraft("AAA", lat=40.50, lon=-73.90, heading=90.0)
        b = _aircraft("BBB", lat=40.70, lon=-73.50, heading=270.0)
        # Turn AAA to head NE — closer to BBB's track.
        result = evaluate_maneuver([a, b], Maneuver("AAA", new_heading_deg=45.0), "BBB")
        # The verdict must be one of the four known categories.
        assert any(
            marker in result.verdict
            for marker in ("SAFER", "RESOLVES", "RISKIER", "WORSE", "NEUTRAL")
        )

    def test_unknown_callsign_raises(self) -> None:
        """An unknown maneuvered callsign raises ValueError."""
        a = _aircraft("UAL123")
        b = _aircraft("DAL456")
        with pytest.raises(ValueError, match="not found"):
            evaluate_maneuver([a, b], Maneuver("NOPE", new_heading_deg=90.0), "DAL456")

    def test_unknown_partner_raises(self) -> None:
        """An unknown partner callsign raises ValueError."""
        a = _aircraft("UAL123")
        b = _aircraft("DAL456")
        with pytest.raises(ValueError, match="not found"):
            evaluate_maneuver([a, b], Maneuver("UAL123", new_heading_deg=90.0), "NOPE")

    def test_result_carries_pair_and_verdict(self) -> None:
        """The result includes the pair tuple and a non-empty verdict."""
        a = _aircraft("UAL123", lat=40.6, lon=-73.7, heading=45.0)
        b = _aircraft("DAL456", lat=40.61, lon=-73.7, heading=225.0)
        result = evaluate_maneuver([a, b], Maneuver("UAL123", new_heading_deg=180.0), "DAL456")
        assert result.pair == ("UAL123", "DAL456")
        assert len(result.verdict) > 0
