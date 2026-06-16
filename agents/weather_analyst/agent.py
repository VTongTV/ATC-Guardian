"""ATC Guardian Weather Analyst Agent — main entry point.

Runs as a Band agent using CrewAIAdapter. Receives SIGMET dispatches
from the Coordinator, analyzes weather hazards, and issues deviation advisories.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Make the project root importable so `shared.*` resolves when this
# agent runs from its own directory with its own venv.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from band import Agent
from band.adapters import CrewAIAdapter

from prompts import WEATHER_ANALYST_SYSTEM_PROMPT
from shared.llm_config import resolve_llm_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _crewai_model_string(provider: str, model_name: str) -> str:
    """Build a litellm-routable model string for CrewAI's ``LLM``.

    CrewAI builds its LLM via ``LLM(model=self.model)`` which routes the
    call through **litellm**. litellm selects the backend purely from a
    provider prefix on the model string (e.g. ``openrouter/...``), so a
    bare model name like ``nex-agi/nex-n2-pro:free`` fails with
    ``LLM Provider NOT provided``. This helper prepends the litellm
    provider prefix when the model doesn't already carry one.

    The Coordinator (``ChatOpenAI``) and PydanticAI agents
    (``openai:<model>``) are unaffected — only CrewAI goes through
    litellm, so this prefixing stays local to the Weather Analyst.

    Args:
        provider: The shared ``LLM_PROVIDER`` value (``openrouter`` /
            ``aimlapi``).
        model_name: Resolved model name from :func:`resolve_llm_config`.

    Returns:
        A model string litellm can route (e.g.
        ``openrouter/nex-agi/nex-n2-pro:free``).
    """
    # litellm-recognised prefixes — leave already-routable strings alone.
    known_prefixes = ("openrouter/", "openai/", "anthropic/", "aimlapi/")
    if any(model_name.startswith(p) for p in known_prefixes):
        return model_name
    if provider == "openrouter":
        return f"openrouter/{model_name}"
    return model_name


def create_weather_analyst_adapter() -> CrewAIAdapter:
    """Create the CrewAIAdapter for the Weather Analyst agent.

    Uses CrewAI with the multi-provider LLM configuration resolved
    from shared environment variables.  The resolved API key and base
    URL are injected into ``OPENAI_API_KEY`` and ``OPENAI_BASE_URL``
    env vars so CrewAI's LLM class picks them up, and the model string
    is prefixed with the litellm provider so CrewAI's litellm-backed
    ``LLM`` can route the call.

    Returns:
        Configured CrewAIAdapter instance.
    """
    base_url, api_key, model_name = resolve_llm_config("WEATHER_ANALYST_MODEL")
    provider = os.getenv("LLM_PROVIDER", "openrouter")
    crewai_model = _crewai_model_string(provider, model_name)
    logger.info(
        "LLM provider=%s model=%s crewai_model=%s base_url=%s",
        provider,
        model_name,
        crewai_model,
        base_url,
    )

    # Set env vars so CrewAI's LLM class uses the resolved provider
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_BASE_URL"] = base_url

    return CrewAIAdapter(
        model=crewai_model,
        role="Weather Analyst",
        goal="Monitor SIGMETs and weather hazards affecting aircraft, issue deviation advisories",
        backstory=(
            "You are an experienced meteorologist specializing in aviation weather. "
            "You understand SIGMETs, AIRMETs, and how weather phenomena impact flight operations. "
            "You provide clear, actionable deviation recommendations."
        ),
        custom_section=WEATHER_ANALYST_SYSTEM_PROMPT,
        enable_execution_reporting=True,
    )


async def main() -> None:
    """Start the Weather Analyst agent and connect to Band."""
    from dotenv import load_dotenv

    load_dotenv()

    adapter = create_weather_analyst_adapter()

    agent = Agent.create(
        adapter=adapter,
        agent_id=os.environ["WEATHER_ANALYST_AGENT_ID"],
        api_key=os.environ["WEATHER_ANALYST_API_KEY"],
    )

    logger.info("Starting ATC Guardian Weather Analyst agent...")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
