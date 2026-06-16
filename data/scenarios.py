"""Pre-defined demo scenarios for ATC Guardian.

Each scenario initializes aircraft at realistic positions near
Mumbai (VABB / Chhatrapati Shivaji Maharaj Intl) and evolves them
over a 5-minute window to demonstrate:
  A) Converging conflict + resolution
  B) SIGMET weather deviation
  C) Emergency squawk 7700 + descent

NOTE: the original scenarios were authored around JFK (40.63N,
73.68W). When relocated to Mumbai (19.09N) the longitude offsets
were scaled by cos(JFK)/cos(Mumbai) ~= 0.803 so that the true
nautical-mile geometry — and therefore the conflict-detection
thresholds — is preserved.
"""

from datetime import datetime, timedelta, timezone

from shared.models import (
    AircraftState,
    AlertSeverity,
    ScenarioDefinition,
    ScenarioStep,
    SIGMET,
    SIGMETGeometry,
    PositionGeographic,
)


def scenario_a_convergence() -> ScenarioDefinition:
    """Scenario A: Two aircraft on converging headings at FL350.

    UAL123 flies NE toward DAL456 flying SW. CPA computed in
    under 2 minutes. Conflict Detector issues advisory.
    Coordinator dispatches to Ground Ops for runway info.
    """
    now = datetime.now(timezone.utc)
    return ScenarioDefinition(
        scenario_id="SCN-A",
        name="Converging Conflict",
        description="Two aircraft on converging headings at FL350 trigger a conflict advisory.",
        center_latitude=19.09,
        center_longitude=72.87,
        initial_states=[
            AircraftState(
                callsign="UAL123",
                latitude=19.01,
                longitude=72.57,
                altitude_ft=35000,
                heading_deg=58.0,
                speed_kts=460,
                vertical_speed_fpm=0,
                squawk="4321",
                timestamp=now,
            ),
            AircraftState(
                callsign="DAL456",
                latitude=19.18,
                longitude=73.01,
                altitude_ft=35000,
                heading_deg=238.0,
                speed_kts=450,
                vertical_speed_fpm=0,
                squawk="5678",
                timestamp=now,
            ),
            AircraftState(
                callsign="AAL100",
                latitude=19.06,
                longitude=72.77,
                altitude_ft=28000,
                heading_deg=90.0,
                speed_kts=400,
                vertical_speed_fpm=500,
                squawk="1234",
                timestamp=now,
            ),
        ],
        steps=[],
    )


def scenario_b_weather_deviation() -> ScenarioDefinition:
    """Scenario B: SIGMET for severe turbulence near Mumbai approach corridor.

    BAW200 is heading into the SIGMET area. Weather Analyst
    detects overlap and issues advisory. Coordinator dispatches
    deviation to Ground Ops.
    """
    now = datetime.now(timezone.utc)
    return ScenarioDefinition(
        scenario_id="SCN-B",
        name="Weather Deviation",
        description="SIGMET for severe turbulence forces aircraft to deviate from approach.",
        center_latitude=19.09,
        center_longitude=72.87,
        initial_states=[
            AircraftState(
                callsign="BAW200",
                latitude=18.96,
                longitude=72.53,
                altitude_ft=22000,
                heading_deg=50.0,
                speed_kts=380,
                vertical_speed_fpm=-1200,
                squawk="2345",
                timestamp=now,
            ),
            AircraftState(
                callsign="DLH505",
                latitude=19.16,
                longitude=72.93,
                altitude_ft=36000,
                heading_deg=110.0,
                speed_kts=480,
                vertical_speed_fpm=0,
                squawk="3456",
                timestamp=now,
            ),
            AircraftState(
                callsign="AFR890",
                latitude=19.01,
                longitude=73.09,
                altitude_ft=32000,
                heading_deg=330.0,
                speed_kts=440,
                vertical_speed_fpm=-500,
                squawk="4567",
                timestamp=now,
            ),
        ],
        steps=[],
    )


def scenario_c_emergency() -> ScenarioDefinition:
    """Scenario C: Aircraft declares emergency with squawk 7700.

    SWA770 loses pressurization at FL350, squawks 7700, and
    begins emergency descent at 1500 fpm toward FL100. Emergency
    Response detects and coordinates. Ground Ops provides nearest
    suitable runway.
    """
    now = datetime.now(timezone.utc)
    return ScenarioDefinition(
        scenario_id="SCN-C",
        name="Emergency Descent",
        description="Aircraft declares emergency (7700) and begins rapid descent from FL350.",
        center_latitude=19.09,
        center_longitude=72.87,
        initial_states=[
            AircraftState(
                callsign="SWA770",
                latitude=19.11,
                longitude=72.85,
                altitude_ft=35000,
                heading_deg=90.0,
                speed_kts=460,
                vertical_speed_fpm=-1500,
                squawk="7700",
                timestamp=now,
            ),
            AircraftState(
                callsign="JBU410",
                latitude=19.14,
                longitude=72.93,
                altitude_ft=31000,
                heading_deg=180.0,
                speed_kts=420,
                vertical_speed_fpm=-800,
                squawk="6789",
                timestamp=now,
            ),
            AircraftState(
                callsign="EDV5522",
                latitude=19.06,
                longitude=72.81,
                altitude_ft=10000,
                heading_deg=270.0,
                speed_kts=250,
                vertical_speed_fpm=-500,
                squawk="7890",
                timestamp=now,
            ),
        ],
        steps=[],
    )


ALL_SCENARIOS: dict[str, ScenarioDefinition] = {
    "SCN-A": scenario_a_convergence(),
    "SCN-B": scenario_b_weather_deviation(),
    "SCN-C": scenario_c_emergency(),
}


def _scenario_b_sigmet() -> SIGMET:
    """Build the SIGMET active during scenario B.

    A severe-turbulence polygon positioned across BAW200's approach
    corridor so the Weather Analyst has a real hazard to detect.

    Returns:
        A SIGMET valid for one hour from now covering the Mumbai
        west arrival gate.
    """
    now = datetime.now(timezone.utc)
    return SIGMET(
        sigmet_id="SIGM-001",
        phenomenon="SEV_TURB",
        severity=AlertSeverity.WARNING,
        geometry=SIGMETGeometry(
            points=[
                PositionGeographic(latitude=19.04, longitude=72.61),
                PositionGeographic(latitude=19.08, longitude=72.73),
                PositionGeographic(latitude=18.98, longitude=72.77),
                PositionGeographic(latitude=18.94, longitude=72.65),
            ],
            buffer_nm=10.0,
        ),
        base_ft=18000,
        top_ft=26000,
        valid_from=now,
        valid_to=now + timedelta(hours=1),
    )


#: SIGMETs active per scenario. Scenarios not listed here have none.
SCENARIO_SIGMETS: dict[str, list[SIGMET]] = {
    "SCN-B": [_scenario_b_sigmet()],
}
