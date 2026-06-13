"""ATC Guardian Conflict Detector Agent — main entry point.

Runs as a Band agent using PydanticAIAdapter. Receives aircraft
pair dispatches from the Coordinator, computes CPA, and issues
structured conflict advisories.
"""

import asyncio
import logging
import os

from band import Agent
from band.adapters import PydanticAIAdapter

from prompts import CONFLICT_DETECTOR_SYSTEM_PROMPT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_conflict_detector_adapter() -> PydanticAIAdapter:
    """Create the PydanticAIAdapter for the Conflict Detector agent.

    Uses PydanticAI with AI/ML API as the model provider
    (OpenAI-compatible endpoint for hackathon partner credit).

    Returns:
        Configured PydanticAIAdapter instance.
    """
    base_url = os.getenv("AIMLAPI_BASE_URL", "https://api.aimlapi.com/v1")
    model_name = os.getenv("CONFLICT_DETECTOR_MODEL", "gpt-4o")

    return PydanticAIAdapter(
        model=f"openai:{model_name}",
        custom_section=CONFLICT_DETECTOR_SYSTEM_PROMPT,
    )


async def main() -> None:
    """Start the Conflict Detector agent and connect to Band."""
    adapter = create_conflict_detector_adapter()

    agent = Agent.create(
        adapter=adapter,
        agent_id=os.environ["CONFLICT_DETECTOR_AGENT_ID"],
        api_key=os.environ["CONFLICT_DETECTOR_API_KEY"],
    )

    logger.info("Starting ATC Guardian Conflict Detector agent...")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
