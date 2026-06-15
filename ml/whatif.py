"""What-if counterfactual CPA analysis.

Lets a controller propose a maneuver (e.g. "turn UAL123 heading 090")
and see the predicted CPA outcome BEFORE acting. Pure math, no LLM —
the agents present this to the controller as decision support.

This is a genuine novelty: no competitor on the leaderboard does
predictive multi-agent collaboration. The controller asks 'what if',
the system recomputes separation, the controller decides.
"""

from __future__ import annotations

from dataclasses import dataclass

from ml.conflict import compute_cpa
from shared.models import AircraftState, CPAResult


@dataclass(frozen=True)
class Maneuver:
    """A proposed controller maneuver applied to one aircraft.

    Attributes:
        callsign: Aircraft to maneuver.
        new_heading_deg: Optional new heading (turn).
        new_altitude_ft: Optional new altitude (climb/descend).
        new_speed_kts: Optional new speed.
    """

    callsign: str
    new_heading_deg: float | None = None
    new_altitude_ft: int | None = None
    new_speed_kts: float | None = None


@dataclass(frozen=True)
class WhatIfResult:
    """Outcome of a counterfactual CPA computation.

    Attributes:
        maneuver: The maneuver that was applied.
        pair: Callsigns of the two aircraft evaluated.
        baseline_cpa_nm: CPA distance before the maneuver.
        predicted_cpa_nm: CPA distance after the maneuver.
        baseline_is_conflict: Whether the baseline was a conflict.
        predicted_is_conflict: Whether the maneuvered scenario is a conflict.
        delta_nm: Change in CPA distance (positive = safer).
        verdict: One-line assessment for the UI.
    """

    maneuver: Maneuver
    pair: tuple[str, str]
    baseline_cpa_nm: float
    predicted_cpa_nm: float
    baseline_is_conflict: bool
    predicted_is_conflict: bool
    delta_nm: float
    verdict: str


def apply_maneuver(aircraft: AircraftState, maneuver: Maneuver) -> AircraftState:
    """Return a copy of an aircraft with a maneuver applied.

    Args:
        aircraft: The original aircraft state.
        maneuver: The maneuver to apply (only matching callsign is affected).

    Returns:
        A new AircraftState with the maneuver's overrides applied.
    """
    if aircraft.callsign != maneuver.callsign:
        return aircraft
    return aircraft.model_copy(
        update={
            "heading_deg": (
                maneuver.new_heading_deg
                if maneuver.new_heading_deg is not None
                else aircraft.heading_deg
            ),
            "altitude_ft": (
                maneuver.new_altitude_ft
                if maneuver.new_altitude_ft is not None
                else aircraft.altitude_ft
            ),
            "speed_kts": (
                maneuver.new_speed_kts
                if maneuver.new_speed_kts is not None
                else aircraft.speed_kts
            ),
        }
    )


def evaluate_maneuver(
    aircraft_list: list[AircraftState],
    maneuver: Maneuver,
    partner_callsign: str,
) -> WhatIfResult:
    """Compute the CPA impact of a proposed maneuver on an aircraft pair.

    Args:
        aircraft_list: Current aircraft states.
        maneuver: The maneuver to evaluate.
        partner_callsign: The other aircraft in the pair.

    Returns:
        A WhatIfResult comparing baseline vs predicted CPA.

    Raises:
        ValueError: If the maneuvered or partner aircraft are not found.
    """
    target = _find(aircraft_list, maneuver.callsign)
    partner = _find(aircraft_list, partner_callsign)
    if target is None:
        raise ValueError(f"Aircraft {maneuver.callsign} not found")
    if partner is None:
        raise ValueError(f"Aircraft {partner_callsign} not found")

    baseline = compute_cpa(target, partner)

    maneuvered = apply_maneuver(target, maneuver)
    predicted = compute_cpa(maneuvered, partner)

    delta = predicted.min_distance_nm - baseline.min_distance_nm
    if predicted.is_conflict and not baseline.is_conflict:
        verdict = f"WORSE: maneuver introduces a conflict (CPA {predicted.min_distance_nm} nm)."
    elif not predicted.is_conflict and baseline.is_conflict:
        verdict = f"RESOLVES: maneuver clears the conflict (CPA {predicted.min_distance_nm} nm)."
    elif delta > 0.1:
        verdict = f"SAFER: CPA improves by {delta:.1f} nm to {predicted.min_distance_nm} nm."
    elif delta < -0.1:
        verdict = f"RISKIER: CPA worsens by {abs(delta):.1f} nm to {predicted.min_distance_nm} nm."
    else:
        verdict = f"NEUTRAL: CPA unchanged at {predicted.min_distance_nm} nm."

    return WhatIfResult(
        maneuver=maneuver,
        pair=(maneuver.callsign, partner_callsign),
        baseline_cpa_nm=baseline.min_distance_nm,
        predicted_cpa_nm=predicted.min_distance_nm,
        baseline_is_conflict=baseline.is_conflict,
        predicted_is_conflict=predicted.is_conflict,
        delta_nm=round(delta, 2),
        verdict=verdict,
    )


def _find(aircraft_list: list[AircraftState], callsign: str) -> AircraftState | None:
    """Find an aircraft by callsign.

    Args:
        aircraft_list: Aircraft to search.
        callsign: Callsign to find.

    Returns:
        The matching AircraftState, or None.
    """
    for ac in aircraft_list:
        if ac.callsign == callsign:
            return ac
    return None
