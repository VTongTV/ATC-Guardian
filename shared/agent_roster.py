"""Static agent roster — declarative metadata for the ATC Guardian team.

Single source of truth for the six agents: their name, display label,
agentic framework, role, why that framework was chosen, and colour.
Used by the collaboration-graph endpoint, the frontend node-graph, and
the README so the cross-framework story is consistent everywhere.

Band of Agents rewards visible cross-framework collaboration; this
roster makes the LangGraph / PydanticAI / CrewAI diversity explicit
rather than hidden in adapter imports.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentDescriptor(BaseModel):
    """Metadata describing one agent in the ATC Guardian team.

    Attributes:
        name: Band identity (matches @mention target and handler key).
        label: Human-readable label for the UI.
        framework: Agentic framework driving the agent.
        framework_note: One-line rationale for the framework choice.
        role: One-line description of the agent's responsibility.
        colour: Hex colour for the UI node/badge.
    """

    name: str = Field(description="Band identity / @mention target")
    label: str = Field(description="Human-readable label")
    framework: str = Field(description="Agentic framework")
    framework_note: str = Field(description="Why this framework for this role")
    role: str = Field(description="One-line responsibility")
    colour: str = Field(description="Hex colour for the UI")


#: The six ATC Guardian agents, in collaboration-chain order.
AGENT_ROSTER: list[AgentDescriptor] = [
    AgentDescriptor(
        name="coordinator",
        label="Coordinator",
        framework="LangGraph",
        framework_note="Stateful ReAct graph with checkpointing for multi-step dispatch.",
        role="Routes detected conditions to specialists and surfaces reviewed decisions to the controller.",
        colour="#4488ff",
    ),
    AgentDescriptor(
        name="conflict-detector",
        label="Conflict Detector",
        framework="Pydantic AI",
        framework_note="Structured, validated outputs for precise CPA/separation advisories.",
        role="Computes closest-point-of-approach and issues conflict advisories.",
        colour="#ffaa00",
    ),
    AgentDescriptor(
        name="weather-analyst",
        label="Weather Analyst",
        framework="CrewAI",
        framework_note="Crew role/goal/backstory framing suits meteorological reasoning.",
        role="Analyzes SIGMETs and recommends deviation routes.",
        colour="#33ccff",
    ),
    AgentDescriptor(
        name="safety-reviewer",
        label="Safety Reviewer",
        framework="Pydantic AI",
        framework_note="Typed Approve/Reject/Modify verdicts with validation — adversarial check.",
        role="Independently cross-examines every advisory against ICAO minima before action.",
        colour="#aa33ff",
    ),
    AgentDescriptor(
        name="ground-ops",
        label="Ground Ops",
        framework="LangGraph",
        framework_note="Tool-calling graph for airport/runway/ATIS lookups.",
        role="Provides airport information to support diversions and emergencies.",
        colour="#33ff33",
    ),
    AgentDescriptor(
        name="emergency-response",
        label="Emergency Response",
        framework="LangGraph",
        framework_note="Low-temperature stateful graph for high-stakes 7700 coordination.",
        role="Classifies emergency phase and coordinates the response cascade.",
        colour="#ff3333",
    ),
]

#: Quick lookup by name.
AGENT_BY_NAME: dict[str, AgentDescriptor] = {a.name: a for a in AGENT_ROSTER}


def framework_diversity_summary() -> dict[str, int]:
    """Count agents per framework for the cross-framework pitch.

    Returns:
        Dict mapping framework name to number of agents using it.
    """
    counts: dict[str, int] = {}
    for agent in AGENT_ROSTER:
        counts[agent.framework] = counts.get(agent.framework, 0) + 1
    return counts
