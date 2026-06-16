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


def scenario_d_parallel_approach() -> ScenarioDefinition:
    """Scenario D: Two aircraft on parallel ILS approaches with eroding lateral separation.

    AAL200 and UAL300 are both on parallel ILS approaches separated
    laterally by only ~0.5 nm — well below the 3nm minimum. A third
    aircraft BAW400 crosses perpendicular at a lower altitude.
    """
    now = datetime.now(timezone.utc)
    return ScenarioDefinition(
        scenario_id="SCN-D",
        name="Parallel Approach",
        description="Two aircraft on parallel ILS approaches with lateral separation eroding below minimums.",
        center_latitude=19.09,
        center_longitude=72.87,
        initial_states=[
            AircraftState(
                callsign="AAL200",
                latitude=19.14,
                longitude=72.72,
                altitude_ft=3000,
                heading_deg=0.0,
                speed_kts=150,
                vertical_speed_fpm=-700,
                squawk="1200",
                timestamp=now,
            ),
            AircraftState(
                callsign="UAL300",
                latitude=19.14,
                longitude=72.73,
                altitude_ft=3000,
                heading_deg=0.0,
                speed_kts=155,
                vertical_speed_fpm=-650,
                squawk="1200",
                timestamp=now,
            ),
            AircraftState(
                callsign="BAW400",
                latitude=19.02,
                longitude=72.87,
                altitude_ft=1500,
                heading_deg=90.0,
                speed_kts=160,
                vertical_speed_fpm=0,
                squawk="3456",
                timestamp=now,
            ),
        ],
        steps=[],
    )


def scenario_e_lost_communication() -> ScenarioDefinition:
    """Scenario E: Aircraft squawking 7600 (radio failure) near arrival.

    RDU100 has lost radio communication and is squawking 7600 while
    on approach. Two other aircraft are on normal approaches in the
    area, creating a potential conflict with a non-communicating acft.
    """
    now = datetime.now(timezone.utc)
    return ScenarioDefinition(
        scenario_id="SCN-E",
        name="Lost Communication",
        description="Aircraft squawking 7600 (radio failure) on approach — unable to receive ATC instructions.",
        center_latitude=19.09,
        center_longitude=72.87,
        initial_states=[
            AircraftState(
                callsign="RDU100",
                latitude=19.15,
                longitude=72.95,
                altitude_ft=18000,
                heading_deg=50.0,
                speed_kts=320,
                vertical_speed_fpm=-1000,
                squawk="7600",
                timestamp=now,
            ),
            AircraftState(
                callsign="EVA210",
                latitude=19.03,
                longitude=72.80,
                altitude_ft=22000,
                heading_deg=320.0,
                speed_kts=360,
                vertical_speed_fpm=-800,
                squawk="2345",
                timestamp=now,
            ),
            AircraftState(
                callsign="CCA305",
                latitude=19.18,
                longitude=73.05,
                altitude_ft=16000,
                heading_deg=240.0,
                speed_kts=340,
                vertical_speed_fpm=-600,
                squawk="4567",
                timestamp=now,
            ),
        ],
        steps=[],
    )


def scenario_f_microburst() -> ScenarioDefinition:
    """Scenario F: SIGMET for wind shear / microburst near approach corridor.

    DAL700 is heading directly into the microburst area on approach.
    Weather Analyst detects the wind shear SIGMET and must advise
    deviation. Additional aircraft are in the vicinity.
    """
    now = datetime.now(timezone.utc)
    return ScenarioDefinition(
        scenario_id="SCN-F",
        name="Microburst Alert",
        description="SIGMET for wind shear / microburst near the approach corridor threatens arriving aircraft.",
        center_latitude=19.09,
        center_longitude=72.87,
        initial_states=[
            AircraftState(
                callsign="DAL700",
                latitude=19.04,
                longitude=72.65,
                altitude_ft=5000,
                heading_deg=60.0,
                speed_kts=220,
                vertical_speed_fpm=-1200,
                squawk="5678",
                timestamp=now,
            ),
            AircraftState(
                callsign="ICE550",
                latitude=19.16,
                longitude=73.02,
                altitude_ft=8000,
                heading_deg=250.0,
                speed_kts=250,
                vertical_speed_fpm=-400,
                squawk="6789",
                timestamp=now,
            ),
            AircraftState(
                callsign="QTR900",
                latitude=18.98,
                longitude=72.80,
                altitude_ft=4000,
                heading_deg=10.0,
                speed_kts=210,
                vertical_speed_fpm=-800,
                squawk="7890",
                timestamp=now,
            ),
        ],
        steps=[],
    )


def scenario_g_missed_approach() -> ScenarioDefinition:
    """Scenario G: Aircraft executing go-around while departure below.

    SWA500 is executing a missed approach (go-around) and climbing
    rapidly. AAL600 is departing below on a crossing heading, also
    climbing. The converging climb paths create a conflict.
    """
    now = datetime.now(timezone.utc)
    return ScenarioDefinition(
        scenario_id="SCN-G",
        name="Missed Approach",
        description="Aircraft executing go-around while a departing aircraft climbs on a crossing path below.",
        center_latitude=19.09,
        center_longitude=72.87,
        initial_states=[
            AircraftState(
                callsign="SWA500",
                latitude=19.10,
                longitude=72.86,
                altitude_ft=1200,
                heading_deg=270.0,
                speed_kts=160,
                vertical_speed_fpm=2000,
                squawk="1234",
                timestamp=now,
            ),
            AircraftState(
                callsign="AAL600",
                latitude=19.07,
                longitude=72.90,
                altitude_ft=800,
                heading_deg=330.0,
                speed_kts=145,
                vertical_speed_fpm=1800,
                squawk="2345",
                timestamp=now,
            ),
        ],
        steps=[],
    )


def scenario_h_hijack_code() -> ScenarioDefinition:
    """Scenario H: Aircraft squawking 7500 (unlawful interference / hijack).

    TFR800 is squawking 7500, indicating a suspected hijack. Two
    other aircraft are in the area and may need to be rerouted to
    maintain a safe distance from the non-cooperative aircraft.
    """
    now = datetime.now(timezone.utc)
    return ScenarioDefinition(
        scenario_id="SCN-H",
        name="Hijack Code",
        description="Aircraft squawking 7500 (unlawful interference) — non-cooperative, potential hijack.",
        center_latitude=19.09,
        center_longitude=72.87,
        initial_states=[
            AircraftState(
                callsign="TFR800",
                latitude=19.12,
                longitude=72.95,
                altitude_ft=28000,
                heading_deg=90.0,
                speed_kts=420,
                vertical_speed_fpm=0,
                squawk="7500",
                timestamp=now,
            ),
            AircraftState(
                callsign="SIA220",
                latitude=19.05,
                longitude=72.78,
                altitude_ft=30000,
                heading_deg=140.0,
                speed_kts=450,
                vertical_speed_fpm=0,
                squawk="3456",
                timestamp=now,
            ),
            AircraftState(
                callsign="ETH330",
                latitude=19.18,
                longitude=73.10,
                altitude_ft=26000,
                heading_deg=200.0,
                speed_kts=440,
                vertical_speed_fpm=-200,
                squawk="4567",
                timestamp=now,
            ),
        ],
        steps=[],
    )


def scenario_i_fuel_emergency() -> ScenarioDefinition:
    """Scenario I: Aircraft declaring minimum fuel / fuel emergency.

    JBU900 is descending with a fuel emergency (squawk 7700), needing
    priority handling. Other aircraft on approach must be re-sequenced
    to give the emergency aircraft a clear path.
    """
    now = datetime.now(timezone.utc)
    return ScenarioDefinition(
        scenario_id="SCN-I",
        name="Fuel Emergency",
        description="Aircraft declaring minimum fuel emergency (squawk 7700) — needs priority approach.",
        center_latitude=19.09,
        center_longitude=72.87,
        initial_states=[
            AircraftState(
                callsign="JBU900",
                latitude=19.15,
                longitude=73.00,
                altitude_ft=12000,
                heading_deg=250.0,
                speed_kts=300,
                vertical_speed_fpm=-1500,
                squawk="7700",
                timestamp=now,
            ),
            AircraftState(
                callsign="VIR440",
                latitude=19.06,
                longitude=72.82,
                altitude_ft=8000,
                heading_deg=30.0,
                speed_kts=280,
                vertical_speed_fpm=-500,
                squawk="1234",
                timestamp=now,
            ),
            AircraftState(
                callsign="BAW555",
                latitude=19.00,
                longitude=72.95,
                altitude_ft=10000,
                heading_deg=310.0,
                speed_kts=290,
                vertical_speed_fpm=-400,
                squawk="5678",
                timestamp=now,
            ),
        ],
        steps=[],
    )


def scenario_j_runway_incursion() -> ScenarioDefinition:
    """Scenario J: Runway incursion — ground conflict at low altitude.

    EDF100 is on final approach at 500 ft, while EDF200 is on the
    runway at 200 ft taxiing or holding short. Both are at slow speed,
    creating a potential runway incursion / collision risk.
    """
    now = datetime.now(timezone.utc)
    return ScenarioDefinition(
        scenario_id="SCN-J",
        name="Runway Incursion",
        description="Two aircraft at low altitude near the airport — one on approach, one on the runway.",
        center_latitude=19.09,
        center_longitude=72.87,
        initial_states=[
            AircraftState(
                callsign="EDF100",
                latitude=19.10,
                longitude=72.85,
                altitude_ft=500,
                heading_deg=270.0,
                speed_kts=130,
                vertical_speed_fpm=-500,
                squawk="1200",
                timestamp=now,
            ),
            AircraftState(
                callsign="EDF200",
                latitude=19.09,
                longitude=72.87,
                altitude_ft=200,
                heading_deg=270.0,
                speed_kts=15,
                vertical_speed_fpm=0,
                squawk="1200",
                on_ground=True,
                timestamp=now,
            ),
        ],
        steps=[],
    )


ALL_SCENARIOS: dict[str, ScenarioDefinition] = {
    "SCN-A": scenario_a_convergence(),
    "SCN-B": scenario_b_weather_deviation(),
    "SCN-C": scenario_c_emergency(),
    "SCN-D": scenario_d_parallel_approach(),
    "SCN-E": scenario_e_lost_communication(),
    "SCN-F": scenario_f_microburst(),
    "SCN-G": scenario_g_missed_approach(),
    "SCN-H": scenario_h_hijack_code(),
    "SCN-I": scenario_i_fuel_emergency(),
    "SCN-J": scenario_j_runway_incursion(),
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


def _scenario_f_sigmet() -> SIGMET:
    """Build the SIGMET active during scenario F.

    A wind-shear / microburst polygon positioned across DAL700's
    approach path so the Weather Analyst has a real hazard to detect.

    Returns:
        A SIGMET valid for one hour from now covering the Mumbai
        approach corridor west of the airport.
    """
    now = datetime.now(timezone.utc)
    return SIGMET(
        sigmet_id="SIGM-002",
        phenomenon="MICROBURST",
        severity=AlertSeverity.CRITICAL,
        geometry=SIGMETGeometry(
            points=[
                PositionGeographic(latitude=19.06, longitude=72.62),
                PositionGeographic(latitude=19.10, longitude=72.72),
                PositionGeographic(latitude=18.98, longitude=72.74),
                PositionGeographic(latitude=18.94, longitude=72.64),
            ],
            buffer_nm=8.0,
        ),
        base_ft=0,
        top_ft=6000,
        valid_from=now,
        valid_to=now + timedelta(hours=1),
    )


#: SIGMETs active per scenario. Scenarios not listed here have none.
SCENARIO_SIGMETS: dict[str, list[SIGMET]] = {
    "SCN-B": [_scenario_b_sigmet()],
    "SCN-F": [_scenario_f_sigmet()],
}
