"""Tests for data.generator — scenario simulation engine."""

from datetime import datetime, timezone

from data.generator import evolve_scenario, generate_radar_snapshot, generate_scenario_timeline
from data.scenarios import (
    SCENARIO_SIGMETS,
    scenario_a_convergence,
    scenario_b_weather_deviation,
    scenario_c_emergency,
)
from shared.models import AircraftState, RadarSnapshot


class TestEvolveScenario:
    """Tests for evolve_scenario."""

    def test_elapsed_zero_returns_initial_states(self) -> None:
        """At t=0, evolved states must match initial states."""
        scenario = scenario_a_convergence()
        states = evolve_scenario(scenario, elapsed_seconds=0)

        assert len(states) == len(scenario.initial_states)
        for evolved, initial in zip(states, scenario.initial_states):
            assert evolved.callsign == initial.callsign
            assert evolved.altitude_ft == initial.altitude_ft

    def test_aircraft_moved_after_positive_elapsed(self) -> None:
        """After 60 seconds, aircraft should have moved from initial position."""
        scenario = scenario_a_convergence()
        states = evolve_scenario(scenario, elapsed_seconds=60)

        for evolved, initial in zip(states, scenario.initial_states):
            if initial.speed_kts > 0:
                # Aircraft with non-zero speed should have moved
                lat_moved = abs(evolved.latitude - initial.latitude) > 0.001
                lon_moved = abs(evolved.longitude - initial.longitude) > 0.001
                assert lat_moved or lon_moved


class TestGenerateRadarSnapshot:
    """Tests for generate_radar_snapshot."""

    def test_returns_radar_snapshot_type(self) -> None:
        """Must return a RadarSnapshot instance."""
        scenario = scenario_a_convergence()
        snapshot = generate_radar_snapshot(scenario, elapsed_seconds=0)

        assert isinstance(snapshot, RadarSnapshot)

    def test_snapshot_has_aircraft(self) -> None:
        """Snapshot must contain aircraft states."""
        scenario = scenario_a_convergence()
        snapshot = generate_radar_snapshot(scenario, elapsed_seconds=0)

        assert len(snapshot.aircraft) > 0

    def test_converging_scenario_detects_conflict(self) -> None:
        """Scenario A (UAL123 vs DAL456 converging) must surface a conflict."""
        scenario = scenario_a_convergence()
        snapshot = generate_radar_snapshot(scenario, elapsed_seconds=0)

        assert len(snapshot.conflicts) >= 1
        pair = snapshot.conflicts[0].cpa
        callsigns = {pair.aircraft_a_callsign, pair.aircraft_b_callsign}
        assert {"UAL123", "DAL456"} == callsigns
        assert pair.is_conflict is True

    def test_emergency_scenario_detects_7700(self) -> None:
        """Scenario C must surface an emergency for SWA770 (squawk 7700)."""
        scenario = scenario_c_emergency()
        snapshot = generate_radar_snapshot(scenario, elapsed_seconds=0)

        assert len(snapshot.emergencies) >= 1
        emrg = snapshot.emergencies[0]
        assert emrg.callsign == "SWA770"
        assert emrg.squawk_code == "7700"

    def test_weather_scenario_detects_sigmet_when_provided(self) -> None:
        """Scenario B with its SIGMET must surface a weather advisory."""
        scenario = scenario_b_weather_deviation()
        sigmets = SCENARIO_SIGMETS["SCN-B"]
        snapshot = generate_radar_snapshot(scenario, elapsed_seconds=0, sigmets=sigmets)

        assert len(snapshot.weather_advisories) >= 1
        advisory = snapshot.weather_advisories[0]
        assert advisory.sigmet.sigmet_id == "SIGM-001"

    def test_no_sigmet_means_no_weather_advisory(self) -> None:
        """Without SIGMETs the weather advisory list is empty."""
        scenario = scenario_b_weather_deviation()
        snapshot = generate_radar_snapshot(scenario, elapsed_seconds=0)

        assert snapshot.weather_advisories == []


class TestGenerateScenarioTimeline:
    """Tests for generate_scenario_timeline."""

    def test_timeline_has_multiple_snapshots(self) -> None:
        """5 min at 4s intervals should produce multiple snapshots."""
        scenario = scenario_a_convergence()
        timeline = generate_scenario_timeline(scenario)

        assert len(timeline) > 10

    def test_custom_duration(self) -> None:
        """Custom duration should produce correct number of snapshots."""
        scenario = scenario_a_convergence()
        timeline = generate_scenario_timeline(scenario, duration_seconds=20, interval_seconds=5)

        assert len(timeline) == 5  # 0, 5, 10, 15, 20

    def test_emergency_scenario_preserves_squawk(self) -> None:
        """Emergency scenario must preserve 7700 squawk throughout evolution."""
        scenario = scenario_c_emergency()
        states = evolve_scenario(scenario, elapsed_seconds=60)
        swa770 = next(s for s in states if s.callsign == "SWA770")

        assert swa770.squawk == "7700"

    def test_emergency_aircraft_descends(self) -> None:
        """Emergency aircraft with negative vertical speed must lose altitude."""
        scenario = scenario_c_emergency()
        states = evolve_scenario(scenario, elapsed_seconds=120)
        swa770 = next(s for s in states if s.callsign == "SWA770")

        # Started at 35000, descending at 1500 fpm for 2 minutes = -3000 ft
        assert swa770.altitude_ft < 35000
