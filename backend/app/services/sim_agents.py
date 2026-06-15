"""Simulated agent handlers for offline Band collaboration (BAND_MODE=sim).

Each handler mirrors what the corresponding Band agent would reply when
@mentioned, but runs locally with no LLM and no network. They produce
real advisory-shaped :class:`BandInboundMessage` objects so the audit
timeline, agent chat panel, and radar all populate identically to live
mode.

These handlers are intentionally deterministic and conservative: they
echo the detected condition, add a concise recommendation, and (for the
coordinator) surface a pending decision to the controller. The real
Band agents replace them when ``BAND_MODE=live``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Callable

from shared.band_client import AgentHandler, BandInboundMessage, BandOutboundMessage

logger = logging.getLogger(__name__)

# Optional decision service, set by main.py so the coordinator handler
# can create pending controller decisions. Kept as module state because
# the SimulatedBandClient calls handlers as plain functions.
_decision_service: "object | None" = None  # DecisionService at runtime

# Optional Band client, set by main.py so handlers can emit structured
# Band events (thought / tool_call / tool_result / error) into the room
# for a richer audit timeline.
_band_client: "object | None" = None  # BandClient at runtime


def set_decision_service(service: object | None) -> None:
    """Inject the decision service so coordinator can create proposals.

    Args:
        service: The DecisionService instance, or None to disable.
    """
    global _decision_service
    _decision_service = service


def set_band_client(client: object | None) -> None:
    """Inject the Band client so handlers can post structured events.

    Args:
        client: The BandClient instance, or None to disable event emission.
    """
    global _band_client
    _band_client = client


async def _emit_event(
    agent: str, event_type: str, content: str, metadata: dict | None = None
) -> None:
    """Post a structured Band event if a client is wired.

    Structured events (thought / tool_call / tool_result / error) make
    the audit timeline richer and demonstrate deeper Band usage than
    text-only messaging. Failures are swallowed so they never break the
    collaboration loop.

    Args:
        agent: Agent identity producing the event.
        event_type: One of thought / task / tool_call / tool_result / error.
        content: Human-readable description.
        metadata: Optional structured payload.
    """
    if _band_client is None:
        return
    try:
        await _band_client.post_event(agent, event_type, content, metadata)  # type: ignore[attr-defined]
    except Exception:
        logger.exception("Failed to emit %s event from %s", event_type, agent)


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
    """Simulate the Coordinator surfacing a reviewed advisory for approval.

    The coordinator creates a pending :class:`ControllerDecision`
    (AI-assisted, human-decided) and acknowledges the chain. It does NOT
    re-recruit anyone — the specialist already delivered its finding and
    the reviewer already vetted it.

    Args:
        inbound: The verdict or advisory addressed to coordinator.

    Returns:
        A single acknowledgement reply with no further mentions.
    """
    meta = inbound.metadata or {}
    summary = meta.get("summary", inbound.content)
    verdict = meta.get("verdict", "APPROVE")
    recommendation = meta.get("recommendation") or meta.get("modification") or "see advisory"
    advisory_kind = _kind_from_metadata(meta)
    evidence = {k: v for k, v in meta.items() if k in {"cpa", "callsign", "sigmet_id", "phase"}}

    # Create a pending controller decision (human-on-the-loop).
    decision_summary = "No proposal created"
    if _decision_service is not None and verdict in {"APPROVE", "MODIFY"}:
        try:
            decision = await _decision_service.create_proposal(  # type: ignore[attr-defined]
                scenario_id=meta.get("scenario_id", "SCN-A"),
                advisory_kind=advisory_kind,
                summary=summary,
                agent_recommendation=recommendation,
                reviewer_verdict=verdict,
                evidence=evidence,
            )
            decision_summary = f"Decision {decision.decision_id} pending controller approval"
        except Exception:
            logger.exception("Coordinator failed to create pending decision")
            decision_summary = "Decision creation failed"
    elif verdict == "REJECT":
        decision_summary = "Reviewer REJECTED — no controller action needed"

    return [
        _reply(
            sender="coordinator",
            content=(
                f"Coordinator: {summary}. Reviewer verdict {verdict}. "
                f"{decision_summary}. End of chain."
            ),
            mentions=[],  # intentionally empty — terminates the cascade
            correlation_id=inbound.correlation_id,
            metadata={"role": "coordinator", "kind": "acknowledgement"},
        )
    ]


def _kind_from_metadata(meta: dict) -> str:
    """Map advisory metadata to a kind label for the decision service.

    Looks at both the structured ``kind`` field and the human-readable
    ``summary`` so a safety-verdict reply (whose kind is
    ``safety_verdict``) still resolves to the originating condition type.

    Args:
        meta: The message metadata.

    Returns:
        One of conflict / weather / emergency / advisory.
    """
    haystack = f"{meta.get('kind', '')} {meta.get('summary', '')} {meta.get('callsign', '')}".lower()
    if "conflict" in haystack:
        return "conflict"
    if "sigmet" in haystack or "weather" in haystack:
        return "weather"
    if "emergency" in haystack or "7700" in haystack or "distress" in haystack:
        return "emergency"
    return "advisory"


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

    # Emit structured tool events so the audit timeline shows the
    # detector's reasoning, not just the final advisory.
    await _emit_event(
        "conflict-detector",
        "tool_call",
        f"compute_cpa({cpa.get('aircraft_a_callsign', '?')}, "
        f"{cpa.get('aircraft_b_callsign', '?')})",
        metadata={"tool": "compute_cpa"},
    )
    await _emit_event(
        "conflict-detector",
        "tool_result",
        f"CPA {dist} nm in {tta}s, conflict={cpa.get('is_conflict', False)}",
        metadata={"cpa": cpa},
    )

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

    # Emit a structured 'thought' event so the audit timeline shows the
    # reviewer's reasoning, not just the final verdict.
    await _emit_event(
        "safety-reviewer",
        "thought",
        f"Cross-examining {kind} against ICAO minima: {reasoning}",
        metadata={"verdict": verdict, "kind": kind, "cpa_nm": dist},
    )

    content = (
        f"VERDICT: {verdict} | REASONING: {reasoning}"
        + (f" | MODIFICATION: {modification}" if modification else "")
        + " Routing to @coordinator."
    )
    # Preserve the specialist's recommendation and any callsign so the
    # coordinator can build a complete controller decision.
    recommendation = meta.get("recommendation")
    callsign = meta.get("callsign")
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
                "recommendation": recommendation or modification or reasoning,
                "callsign": callsign,
                "cpa": cpa if cpa else None,
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
