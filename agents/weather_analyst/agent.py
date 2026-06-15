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


def create_weather_analyst_adapter() -> CrewAIAdapter:
    """Create the CrewAIAdapter for the Weather Analyst agent.

    Uses CrewAI with the multi-provider LLM configuration resolved
    from shared environment variables.  The resolved API key and base
    URL are injected into ``OPENAI_API_KEY`` and ``OPENAI_BASE_URL``
    env vars so CrewAI's LLM class picks them up.

    Returns:
        Configured CrewAIAdapter instance.
    """
    base_url, api_key, model_name = resolve_llm_config("WEATHER_ANALYST_MODEL")
    logger.info(
        "LLM provider=%s model=%s base_url=%s",
        os.getenv("LLM_PROVIDER", "openrouter"),
        model_name,
        base_url,
    )

    # Set env vars so CrewAI's LLM class uses the resolved provider
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_BASE_URL"] = base_url

    return CrewAIAdapter(
        model=model_name,
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
