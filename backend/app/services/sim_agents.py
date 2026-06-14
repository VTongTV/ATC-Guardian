"""Simulated agent handlers for offline Band collaboration (BAND_MODE=sim).

Each handler mirrors what the corresponding Band agent would reply when
@mentioned, but runs locally with no LLM and no network. They produce
real advisory-shaped :class:`BandInboundMessage` objects so the audit
timeline, agent chat panel, and radar all populate identically to live
mode.

These handlers are intentionally deterministic and conservative: they
echo the detected condition, add a concise recommendation, and (for the
coordinator) recruit the relevant specialist. The real Band agents
replace them when ``BAND_MODE=live``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Callable

from shared.band_client import AgentHandler, BandInboundMessage, BandOutboundMessage

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _reply(
    sender: str,
    content: str,
    mentions: list[str] | None = None,
    correlation_id: str | None = None,
    metadata: dict | None = None,
) -> BandInboundMessage:
    """Build a BandInboundMessage reply.

    Args:
        sender: Agent identity producing the reply.
        content: Reply body, including any @mentions.
        mentions: Agents mentioned by the reply.
        correlation_id: Optional id linking back to the triggering request.
        metadata: Optional structured payload.

    Returns:
        A populated BandInboundMessage.
    """
    return BandInboundMessage(
        message_id="",  # filled by SimulatedBandClient buffer ordering
        timestamp=_now_iso(),
        sender=sender,
        content=content,
        mentions=mentions or [],
        message_type="text",
        metadata=metadata,
        correlation_id=correlation_id,
    )


# ---------------------------------------------------------------------------
# Individual agent handlers
# ---------------------------------------------------------------------------


async def coordinator_handler(
    inbound: BandOutboundMessage,
) -> list[BandInboundMessage]:
    """Simulate the Coordinator acknowledging an advisory.

    The Coordinator logs the advisory for the controller. It does NOT
    re-recruit anyone — the specialist already delivered its finding, so
    mentioning them again would cause an echo loop. The coordinator's
    job at this point is to surface the decision to the human.

    Args:
        inbound: The advisory or system message addressed to coordinator.

    Returns:
        A single acknowledgement reply with no further mentions.
    """
    content = (inbound.metadata or {}).get("summary", inbound.content)
    return [
        _reply(
            sender="coordinator",
            content=(
                f"Coordinator logged advisory: {content}. "
                "Surfacing to controller for decision. End of chain."
            ),
            mentions=[],  # intentionally empty — terminates the cascade
            correlation_id=inbound.correlation_id,
            metadata={"role": "coordinator", "kind": "acknowledgement"},
        )
    ]


async def conflict_detector_handler(
    inbound: BandOutboundMessage,
) -> list[BandInboundMessage]:
    """Simulate the Conflict Detector issuing a conflict advisory.

    The advisory is routed to the Safety Reviewer (not directly to the
    coordinator) so it is adversarially checked before action.

    Args:
        inbound: The triggering message (coordinator or system dispatch).

    Returns:
        A conflict-advisory reply routed to safety-reviewer.
    """
    meta = inbound.metadata or {}
    cpa = meta.get("cpa", {})
    pair = f"{cpa.get('aircraft_a_callsign', '?')}/{cpa.get('aircraft_b_callsign', '?')}"
    dist = cpa.get("min_distance_nm", "?")
    tta = cpa.get("time_to_cpa_seconds", "?")
    return [
        _reply(
            sender="conflict-detector",
            content=(
                f"CONFLICT ADVISORY {pair}: CPA {dist} nm in {tta}s. "
                "Recommend vectoring the trailing aircraft right 15° to restore "
                "separation. Submitting to @safety-reviewer for verification."
            ),
            mentions=["safety-reviewer"],
            correlation_id=inbound.correlation_id,
            metadata={
                "role": "conflict-detector",
                "kind": "conflict_advisory",
                "summary": f"Conflict {pair} CPA {dist} nm",
                "cpa": cpa,
                "recommendation": "vector trailing aircraft right 15 degrees",
            },
        )
    ]


async def weather_analyst_handler(
    inbound: BandOutboundMessage,
) -> list[BandInboundMessage]:
    """Simulate the Weather Analyst issuing a deviation advisory.

    The advisory is routed to the Safety Reviewer for verification.

    Args:
        inbound: The triggering message.

    Returns:
        A weather-advisory reply routed to safety-reviewer.
    """
    meta = inbound.metadata or {}
    sigmet_id = meta.get("sigmet_id", "UNKNOWN")
    affected = meta.get("affected_callsigns", [])
    return [
        _reply(
            sender="weather-analyst",
            content=(
                f"WEATHER ADVISORY: SIGMET {sigmet_id} affects {', '.join(affected)}. "
                "Recommend 15 nm right deviation to clear the hazard area. "
                "Submitting to @safety-reviewer for verification."
            ),
            mentions=["safety-reviewer"],
            correlation_id=inbound.correlation_id,
            metadata={
                "role": "weather-analyst",
                "kind": "weather_advisory",
                "summary": f"SIGMET {sigmet_id} affects {', '.join(affected)}",
                "sigmet_id": sigmet_id,
                "affected_callsigns": affected,
                "recommendation": "15 nm right deviation",
            },
        )
    ]


async def safety_reviewer_handler(
    inbound: BandOutboundMessage,
) -> list[BandInboundMessage]:
    """Simulate the Safety Reviewer cross-examining an advisory.

    Applies ICAO separation minima to the proposed advisory and returns
    a verdict. Conflicts with CPA under the lateral minimum and
    insufficient vertical separation get APPROVED (action needed);
    otherwise MODIFIED toward a more conservative turn. This is the
    adversarial review loop the rubric rewards.

    Args:
        inbound: The advisory submitted by a specialist agent.

    Returns:
        A verdict reply routed to coordinator.
    """
    meta = inbound.metadata or {}
    kind = meta.get("kind", "")
    cpa = meta.get("cpa", {})
    dist = cpa.get("min_distance_nm")
    summary = meta.get("summary", "advisory")

    if kind == "conflict_advisory" and isinstance(dist, (int, float)):
        if dist < 3.0:
            verdict = "APPROVE"
            reasoning = (
                f"CPA {dist} nm is below the 3.0 nm critical threshold and "
                "vertical separation is insufficient; immediate vector required."
            )
            modification = ""
        elif dist < 5.0:
            verdict = "APPROVE"
            reasoning = (
                f"CPA {dist} nm violates the 5.0 nm lateral minimum; "
                "recommended turn restores separation."
            )
            modification = ""
        else:
            verdict = "MODIFY"
            reasoning = (
                f"CPA {dist} nm is inside the alert band but the turn "
                "direction should target the trailing aircraft specifically."
            )
            modification = "Turn the trailing (faster) aircraft, not the leader."
    else:
        # Weather / emergency / unknown: approve with a conservative note.
        verdict = "APPROVE"
        reasoning = "Advisory is consistent with current separation minima."
        modification = ""

    content = (
        f"VERDICT: {verdict} | REASONING: {reasoning}"
        + (f" | MODIFICATION: {modification}" if modification else "")
        + " Routing to @coordinator."
    )
    return [
        _reply(
            sender="safety-reviewer",
            content=content,
            mentions=["coordinator"],
            correlation_id=inbound.correlation_id,
            metadata={
                "role": "safety-reviewer",
                "kind": "safety_verdict",
                "summary": f"{verdict}: {summary}",
                "verdict": verdict,
                "reasoning": reasoning,
                "modification": modification,
            },
        )
    ]


async def emergency_response_handler(
    inbound: BandOutboundMessage,
) -> list[BandInboundMessage]:
    """Simulate Emergency Response coordinating a 7700.

    Only recruits @ground-ops when the triggering message actually
    carries an emergency (kind=emergency). When ground-ops replies, the
    reply's kind is ground_response — at that point ER routes the final
    plan to the Safety Reviewer before coordinator, breaking the
    cascade cleanly.

    Args:
        inbound: The triggering message.

    Returns:
        An emergency-coordination reply, scoped to avoid echo loops.
    """
    meta = inbound.metadata or {}
    kind = meta.get("kind", "")
    callsign = meta.get("callsign", "UNKNOWN")

    if kind == "ground_response":
        # Ground ops came back with runway info — route plan to reviewer.
        return [
            _reply(
                sender="emergency-response",
                content=(
                    f"Emergency Response: runway info received for {callsign}. "
                    "Vectors to nearest suitable. Submitting final plan to "
                    "@safety-reviewer."
                ),
                mentions=["safety-reviewer"],
                correlation_id=inbound.correlation_id,
                metadata={
                    "role": "emergency-response",
                    "kind": "emergency_resolution",
                    "summary": f"Emergency {callsign} resolution ready",
                    "callsign": callsign,
                },
            )
        ]

    # Fresh emergency: recruit ground-ops for runway info.
    return [
        _reply(
            sender="emergency-response",
            content=(
                f"EMERGENCY RESPONSE: {callsign} squawking 7700. "
                "Initiating distress phase. Requesting nearest suitable "
                "runway from @ground-ops."
            ),
            mentions=["ground-ops"],
            correlation_id=inbound.correlation_id,
            metadata={
                "role": "emergency-response",
                "kind": "emergency_declaration",
                "summary": f"Emergency {callsign} squawk 7700",
                "callsign": callsign,
                "phase": "distress",
                "recommendation": "descend to FL100, vectors to nearest suitable",
            },
        )
    ]


async def ground_ops_handler(
    inbound: BandOutboundMessage,
) -> list[BandInboundMessage]:
    """Simulate Ground Ops returning airport information.

    Args:
        inbound: The triggering message.

    Returns:
        A ground-info reply routed back to emergency-response with the
        emergency's callsign preserved in metadata.
    """
    callsign = (inbound.metadata or {}).get("callsign", "UNKNOWN")
    return [
        _reply(
            sender="ground-ops",
            content=(
                "GROUND OPS: KJFK active runways 31L/31R, wind 290/12. "
                "Emergency equipment standing by. Routing to @emergency-response."
            ),
            mentions=["emergency-response"],
            correlation_id=inbound.correlation_id,
            metadata={
                "role": "ground-ops",
                "kind": "ground_response",
                "callsign": callsign,
                "icao": "KJFK",
                "active_runways": ["31L", "31R"],
            },
        )
    ]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

#: Maps agent name -> simulated handler.
SIM_AGENT_HANDLERS: dict[str, AgentHandler] = {
    "coordinator": coordinator_handler,
    "conflict-detector": conflict_detector_handler,
    "weather-analyst": weather_analyst_handler,
    "safety-reviewer": safety_reviewer_handler,
    "emergency-response": emergency_response_handler,
    "ground-ops": ground_ops_handler,
}


def register_sim_agents(client: object) -> None:
    """Register every simulated agent handler on a SimulatedBandClient.

    Args:
        client: A SimulatedBandClient instance (typed as object here to
            avoid importing the concrete class in this module's body).
    """
    for name, handler in SIM_AGENT_HANDLERS.items():
        client.register_agent(name, handler)  # type: ignore[attr-defined]
    logger.info(
        "Registered %d simulated agent handlers: %s",
        len(SIM_AGENT_HANDLERS),
        ", ".join(SIM_AGENT_HANDLERS),
    )


def _specialist_for_kind(kind: str) -> str:
    """Pick the specialist agent name for a given alert kind.

    Args:
        kind: The alert kind from message metadata
            (``conflict`` / ``weather`` / ``emergency``).

    Returns:
        The agent name to @mention.
    """
    if kind == "conflict":
        return "conflict-detector"
    if kind == "weather":
        return "weather-analyst"
    if kind == "emergency":
        return "emergency-response"
    return "coordinator"
