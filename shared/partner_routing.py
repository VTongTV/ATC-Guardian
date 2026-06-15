"""Partner model routing — per-agent AI/ML API model choices.

All six ATC Guardian agents route through AI/ML API, but each uses the
frontier model best matched to its task. This "one API, many labs, right
model per job" choice is itself the pitch for the 'Best Use of AI/ML API'
($1,000) partner prize: a single key gives access to Zhipu GLM-5.1,
DeepSeek V4 Pro/Flash, and Moonshot Kimi K2-6, and we pick the strongest
fit for each agent rather than forcing one model everywhere.

The per-agent choices are principled:

- Zhipu GLM-5.1 (``zhipu/glm-5.1``) — Safety Reviewer and Emergency
  Response. Both return strict structured verdicts / phase
  classifications that drive the human-on-the-loop decision or a 7700
  response. GLM-5.1's dependable structured output at temperature 0
  keeps these highest-stakes paths deterministic.
- DeepSeek V4 Pro (``deepseek/deepseek-v4-pro``) — Conflict Detector and
  Weather Analyst. Both need deep analytical reasoning (CPA advisory
  generation, SIGMET interpretation + deviation routing) over rich
  context. V4 Pro pairs that reasoning with reliable JSON output.
- Moonshot Kimi K2-6 (``moonshot/kimi-k2-6``) — Coordinator. The
  orchestration layer's multi-step @mention dispatch spans the whole
  agent roster; Kimi's long-context instruction-following suits it.
- DeepSeek V4 Flash (``deepseek/deepseek-v4-flash``) — Ground Ops.
  Repeated bounded tool calls (runway / ATIS / NOTAM lookups) favour a
  fast, cheap model; V4 Flash is the low-latency variant of the family.

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
        model="zhipu/glm-5.1",
        rationale=(
            "The adversarial Safety Reviewer returns an explicit "
            "APPROVE/REJECT/MODIFY verdict that drives the human-on-the-loop "
            "decision. GLM-5.1's dependable structured output at temperature 0 "
            "guarantees the verdict field is always one of the three allowed "
            "values, so the DecisionPanel never receives an unparseable "
            "recommendation."
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
        model="moonshot/kimi-k2-6",
        rationale=(
            "The Coordinator's multi-step dispatch spans the whole agent "
            "roster through @mentions. Moonshot Kimi K2-6's long-context "
            "instruction-following keeps the full mention/dispatch graph in "
            "view, so the right specialist is routed each turn."
        ),
        prize_category="Best Use of AI/ML API",
    ),
    PartnerModelAssignment(
        agent_name="emergency-response",
        provider="aimlapi",
        model="zhipu/glm-5.1",
        rationale=(
            "7700 emergencies are the highest-stakes path in the system. "
            "GLM-5.1 via AI/ML API gives the most reproducible structured "
            "output at temperature 0, so the emergency phase classification "
            "and resolution plan are deterministic and trustworthy under "
            "pressure."
        ),
        prize_category="Best Use of AI/ML API",
    ),
    PartnerModelAssignment(
        agent_name="ground-ops",
        provider="aimlapi",
        model="deepseek/deepseek-v4-flash",
        rationale=(
            "Ground Ops performs repeated bounded tool-call lookups "
            "(runway / ATIS / NOTAM) that favour speed and cost over deep "
            "reasoning. DeepSeek V4 Flash is the low-latency variant of the "
            "V4 family, ideal for these frequent, simple structured calls."
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
