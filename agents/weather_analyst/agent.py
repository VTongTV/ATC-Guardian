"""ATC Guardian Weather Analyst Agent — main entry point.

Runs as a Band agent using CrewAIAdapter. Receives SIGMET dispatches
from the Coordinator, analyzes weather hazards, and issues deviation advisories.
"""

import asyncio
import logging
import os

from band import Agent
from band.adapters import CrewAIAdapter

from prompts import WEATHER_ANALYST_SYSTEM_PROMPT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_weather_analyst_adapter() -> CrewAIAdapter:
    """Create the CrewAIAdapter for the Weather Analyst agent.

    Uses CrewAI with AI/ML API as the model provider
    (OpenAI-compatible endpoint for hackathon partner credit).

    Returns:
        Configured CrewAIAdapter instance.
    """
    return CrewAIAdapter(
        model=os.getenv("WEATHER_ANALYST_MODEL", "gpt-4o"),
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
