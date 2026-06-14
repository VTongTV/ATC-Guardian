"""ATC Guardian Conflict Detector Agent — main entry point.

Runs as a Band agent using PydanticAIAdapter. Receives aircraft
pair dispatches from the Coordinator, computes CPA, and issues
structured conflict advisories.
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
from band.adapters import PydanticAIAdapter

from prompts import CONFLICT_DETECTOR_SYSTEM_PROMPT
from shared.llm_config import resolve_llm_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_conflict_detector_adapter() -> PydanticAIAdapter:
    """Create the PydanticAIAdapter for the Conflict Detector agent.

    Uses PydanticAI with the multi-provider LLM configuration resolved
    from shared environment variables.  The resolved API key and base
    URL are injected into ``OPENAI_API_KEY`` and ``OPENAI_BASE_URL``
    env vars so PydanticAI's built-in OpenAI client picks them up.

    Returns:
        Configured PydanticAIAdapter instance.
    """
    base_url, api_key, model_name = resolve_llm_config("CONFLICT_DETECTOR_MODEL")
    logger.info(
        "LLM provider=%s model=%s base_url=%s",
        os.getenv("LLM_PROVIDER", "openrouter"),
        model_name,
        base_url,
    )

    # Set env vars so PydanticAI's OpenAI client uses the resolved provider
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_BASE_URL"] = base_url

    return PydanticAIAdapter(
        model=f"openai:{model_name}",
        custom_section=CONFLICT_DETECTOR_SYSTEM_PROMPT,
    )


async def main() -> None:
    """Start the Conflict Detector agent and connect to Band."""
    from dotenv import load_dotenv

    load_dotenv()

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
