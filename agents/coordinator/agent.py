"""ATC Guardian Coordinator Agent — main entry point.

Runs as a Band agent using LangGraphAdapter. Connects to the
Band platform via WebSocket and dispatches @mentions to specialist
agents based on incoming aircraft data and events.
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
from band.adapters import LangGraphAdapter
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from prompts import COORDINATOR_SYSTEM_PROMPT
from shared.llm_config import resolve_llm_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_coordinator_adapter() -> LangGraphAdapter:
    """Create the LangGraphAdapter for the Coordinator agent.

    Uses ChatOpenAI with the multi-provider LLM configuration resolved
    from shared environment variables.

    Returns:
        Configured LangGraphAdapter instance.
    """
    base_url, api_key, model = resolve_llm_config("COORDINATOR_MODEL")
    logger.info(
        "LLM provider=%s model=%s base_url=%s",
        os.getenv("LLM_PROVIDER", "openrouter"),
        model,
        base_url,
    )

    llm = ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=0.1,
        max_tokens=1024,
        reasoning_effort="low",
    )

    return LangGraphAdapter(
        llm=llm,
        checkpointer=InMemorySaver(),
        custom_section=COORDINATOR_SYSTEM_PROMPT,
    )


async def main() -> None:
    """Start the Coordinator agent and connect to Band."""
    from dotenv import load_dotenv

    load_dotenv()

    adapter = create_coordinator_adapter()

    agent = Agent.create(
        adapter=adapter,
        agent_id=os.environ["COORDINATOR_AGENT_ID"],
        api_key=os.environ["COORDINATOR_API_KEY"],
    )

    logger.info("Starting ATC Guardian Coordinator agent...")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
