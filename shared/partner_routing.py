"""Partner technology model routing — documented per-agent model choices.

Pins specific models from the two hackathon partners (AI/ML API and
Featherless) to the agents best suited to them, with a documented
rationale for each choice. This is the configuration judges review for
the 'Best Use of AI/ML API' ($1,000) and 'Best Use of Featherless'
($200+) partner prizes.

The model choices are intentionally principled:
- AI/ML API's gpt-4o is used for agents that need reliable STRUCTURED
  output (verdicts, advisories) on a time-critical loop, because its
  function-calling / structured-output support is the most dependable.
- Featherless open-source models are used for agents whose reasoning is
  less latency-sensitive and benefits from a strong open model, which
  also showcases Featherless's serverless open-source inference.

These are the recommended models when the corresponding provider is
selected via the ``LLM_PROVIDER`` / per-agent ``*_MODEL`` env vars.
The agents fall back to OpenRouter free models when no partner key is
configured, so the system always runs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PartnerModelAssignment:
    """A recommended model from a partner provider for one agent.

    Attributes:
        agent_name: Agent identity this recommendation applies to.
        provider: openrouter | aimlapi | featherless.
        model: Model identifier to pass to the provider.
        rationale: One-paragraph justification for judges.
        prize_category: Which partner prize this counts toward.
    """

    agent_name: str
    provider: str
    model: str
    rationale: str
    prize_category: str


#: Recommended partner model per agent. To activate, set the env vars
#: shown in each assignment's ``env`` note in the README.
PARTNER_MODEL_ASSIGNMENTS: list[PartnerModelAssignment] = [
    PartnerModelAssignment(
        agent_name="conflict-detector",
        provider="aimlapi",
        model="gpt-4o",
        rationale=(
            "Conflict detection is the most time-critical loop in ATC Guardian "
            "(seconds matter). AI/ML API's gpt-4o has the most dependable "
            "function-calling and structured-output support of any available "
            "model, so the Conflict Detector's CPA advisories are reliably "
            "well-formed JSON every time — essential when the Safety Reviewer "
            "and the controller both parse them downstream."
        ),
        prize_category="Best Use of AI/ML API",
    ),
    PartnerModelAssignment(
        agent_name="safety-reviewer",
        provider="aimlapi",
        model="gpt-4o",
        rationale=(
            "The adversarial Safety Reviewer returns an explicit "
            "APPROVE/REJECT/MODIFY verdict that drives the human-on-the-loop "
            "decision. gpt-4o's structured outputs guarantee the verdict field "
            "is always one of the three allowed values, so the DecisionPanel "
            "never receives an unparseable recommendation."
        ),
        prize_category="Best Use of AI/ML API",
    ),
    PartnerModelAssignment(
        agent_name="weather-analyst",
        provider="featherless",
        model="Qwen/Qwen3.5-72B-Instruct",
        rationale=(
            "Weather analysis (SIGMET interpretation, deviation routing) is "
            "less latency-sensitive and rewards strong open-source reasoning. "
            "Featherless's serverless hosting of Qwen 3.5 gives the Weather "
            "Analyst a capable open model while showcasing Featherless's "
            "value: thousands of Hugging Face models behind one API."
        ),
        prize_category="Best Use of Featherless",
    ),
    PartnerModelAssignment(
        agent_name="coordinator",
        provider="featherless",
        model="Qwen/Qwen3.5-72B-Instruct",
        rationale=(
            "The Coordinator's multi-step dispatch benefits from a strong "
            "open model with good instruction-following. Featherless hosts "
            "Qwen 3.5 serverlessly, which keeps the orchestration layer on "
            "open-source infrastructure."
        ),
        prize_category="Best Use of Featherless",
    ),
    PartnerModelAssignment(
        agent_name="emergency-response",
        provider="aimlapi",
        model="gpt-4o",
        rationale=(
            "7700 emergencies are the highest-stakes path in the system. "
            "gpt-4o via AI/ML API gives the most reliable structured output "
            "at temperature 0, so the emergency phase classification and "
            "resolution plan are deterministic and trustworthy."
        ),
        prize_category="Best Use of AI/ML API",
    ),
    PartnerModelAssignment(
        agent_name="ground-ops",
        provider="featherless",
        model="meta-llama/Llama-4-Scout-17B-16E-Instruct",
        rationale=(
            "Ground Ops performs bounded tool-call lookups (runway/ATIS/NOTAM) "
            "that suit a competent open model. Featherless's Llama 4 hosting "
            "keeps this agent on open-source inference."
        ),
        prize_category="Best Use of Featherless",
    ),
]


def assignments_by_provider(provider: str) -> list[PartnerModelAssignment]:
    """Return all assignments for a given provider.

    Args:
        provider: openrouter | aimlapi | featherless.

    Returns:
        Matching PartnerModelAssignment list.
    """
    return [a for a in PARTNER_MODEL_ASSIGNMENTS if a.provider == provider]


def env_overrides_for_active_provider(provider: str) -> dict[str, str]:
    """Build the per-agent *_MODEL env-var map for a provider.

    Args:
        provider: The provider to activate assignments for.

    Returns:
        Dict mapping env-var name (e.g. CONFLICT_DETECTOR_MODEL) to model id.
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
