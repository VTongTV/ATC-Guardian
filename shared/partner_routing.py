"""Partner model routing — per-agent AI/ML API model choices.

All six ATC Guardian agents route through AI/ML API, using DeepSeek V4 Pro
with ``reasoning_effort=low`` across the board. This "one API, many labs,
right model per job" choice is itself the pitch for the 'Best Use of
AI/ML API' ($1,000) partner prize: a single key gives access to
DeepSeek V4 Pro, Zhipu GLM-5.1, and Moonshot Kimi K2-6, and we pick
the strongest fit for each agent rather than forcing one model everywhere.

Token economy: V4 Pro with ``reasoning_effort=low`` minimises thinking
tokens while keeping pro-quality output. Combined with per-agent rate
limits (3 messages/minute) and prompt-level anti-chatter directives, this
keeps demo burn rates sustainable.

The per-agent choices are principled:

- DeepSeek V4 Pro (``deepseek/deepseek-v4-pro``) — All agents. V4 Pro
  pairs strong analytical reasoning with reliable structured JSON output.
  With ``reasoning_effort=low`` and ``max_tokens`` caps, thinking tokens
  are minimised while output quality remains high.

These are the recommended models when ``LLM_PROVIDER=aimlapi``. Each is
applied via the per-agent ``*_MODEL`` env var (see
:func:`env_overrides_for_active_provider`). Agents fall back to OpenRouter
free models when no AI/ML API key is configured, so the system always runs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PartnerModelAssignment:
    """A recommended AI/ML API model for one agent.

    Attributes:
        agent_name: Agent identity this recommendation applies to.
        provider: Always ``aimlapi`` — all agents run through AI/ML API.
        model: Model identifier passed to AI/ML API.
        rationale: One-paragraph justification for judges.
        prize_category: Which partner prize this counts toward.
    """

    agent_name: str
    provider: str
    model: str
    rationale: str
    prize_category: str


#: Recommended AI/ML API model per agent. To activate, set
#: ``LLM_PROVIDER=aimlapi`` plus the per-agent ``*_MODEL`` overrides from
#: :func:`env_overrides_for_active_provider` (documented in the README).
PARTNER_MODEL_ASSIGNMENTS: list[PartnerModelAssignment] = [
    PartnerModelAssignment(
        agent_name="conflict-detector",
        provider="aimlapi",
        model="deepseek/deepseek-v4-pro",
        rationale=(
            "Conflict detection is the most time-critical loop in ATC "
            "Guardian (seconds matter). DeepSeek V4 Pro pairs strong "
            "analytical reasoning with reliable structured JSON output, so "
            "the Conflict Detector's CPA advisories are well-formed every "
            "time — essential because the Safety Reviewer and the controller "
            "both parse them downstream."
        ),
        prize_category="Best Use of AI/ML API",
    ),
    PartnerModelAssignment(
        agent_name="safety-reviewer",
        provider="aimlapi",
        model="deepseek/deepseek-v4-pro",
        rationale=(
            "The adversarial Safety Reviewer returns an explicit "
            "APPROVE/REJECT/MODIFY verdict. V4 Pro with reasoning_effort=low "
            "gives fast, dependable structured output for this bounded "
            "classification task while keeping thinking tokens minimal."
        ),
        prize_category="Best Use of AI/ML API",
    ),
    PartnerModelAssignment(
        agent_name="weather-analyst",
        provider="aimlapi",
        model="deepseek/deepseek-v4-pro",
        rationale=(
            "Weather analysis (SIGMET interpretation, deviation routing) "
            "rewards deep reasoning over unstructured meteorological text. "
            "DeepSeek V4 Pro is the strongest analytical model on AI/ML API "
            "for this, turning raw SIGMET polygons into a crisp deviation "
            "advisory the Coordinator can act on."
        ),
        prize_category="Best Use of AI/ML API",
    ),
    PartnerModelAssignment(
        agent_name="coordinator",
        provider="aimlapi",
        model="deepseek/deepseek-v4-pro",
        rationale=(
            "The Coordinator's multi-step dispatch spans the whole agent "
            "roster through @mentions. V4 Pro with reasoning_effort=low "
            "handles this orchestration efficiently — deep enough for "
            "correct routing, but no wasted thinking tokens."
        ),
        prize_category="Best Use of AI/ML API",
    ),
    PartnerModelAssignment(
        agent_name="emergency-response",
        provider="aimlapi",
        model="deepseek/deepseek-v4-pro",
        rationale=(
            "7700 emergencies are the highest-stakes path in the system. "
            "V4 Pro with reasoning_effort=low gives the most reliable "
            "structured output at temperature 0, so the emergency phase "
            "classification and resolution plan are deterministic and "
            "trustworthy under pressure."
        ),
        prize_category="Best Use of AI/ML API",
    ),
    PartnerModelAssignment(
        agent_name="ground-ops",
        provider="aimlapi",
        model="deepseek/deepseek-v4-pro",
        rationale=(
            "Ground Ops performs repeated bounded tool-call lookups "
            "(runway / ATIS / NOTAM). V4 Pro with reasoning_effort=low "
            "and max_tokens=512 gives precise structured output without "
            "wasting thinking tokens on simple lookups."
        ),
        prize_category="Best Use of AI/ML API",
    ),
]


def assignments_by_provider(provider: str) -> list[PartnerModelAssignment]:
    """Return all assignments for a given provider.

    All agents currently route through AI/ML API, so passing
    ``"aimlapi"`` returns every assignment and any other provider returns
    an empty list.

    Args:
        provider: Provider to filter by (e.g. ``aimlapi``).

    Returns:
        Matching PartnerModelAssignment list.
    """
    return [a for a in PARTNER_MODEL_ASSIGNMENTS if a.provider == provider]


def env_overrides_for_active_provider(provider: str) -> dict[str, str]:
    """Build the per-agent ``*_MODEL`` env-var map for a provider.

    Args:
        provider: The provider to activate assignments for.

    Returns:
        Dict mapping env-var name (e.g. ``CONFLICT_DETECTOR_MODEL``) to
        model id.
    """
    env_suffix = {
        "coordinator": "COORDINATOR_MODEL",
        "conflict-detector": "CONFLICT_DETECTOR_MODEL",
        "weather-analyst": "WEATHER_ANALYST_MODEL",
        "safety-reviewer": "SAFETY_REVIEWER_MODEL",
        "ground-ops": "GROUND_OPS_MODEL",
        "emergency-response": "EMERGENCY_RESPONSE_MODEL",
    }
    return {
        env_suffix[a.agent_name]: a.model
        for a in PARTNER_MODEL_ASSIGNMENTS
        if a.provider == provider and a.agent_name in env_suffix
    }
