"""ATC Guardian Coordinator Agent — main entry point.

Runs as a Band agent using LangGraphAdapter. Connects to the
Band platform via WebSocket and dispatches @mentions to specialist
agents based on incoming aircraft data and events.
"""

import asyncio
import logging
import os

from band import Agent
from band.adapters import LangGraphAdapter
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from prompts import COORDINATOR_SYSTEM_PROMPT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_coordinator_adapter() -> LangGraphAdapter:
    """Create the LangGraphAdapter for the Coordinator agent.

    Uses ChatOpenAI with AI/ML API as the LLM provider
    (OpenAI-compatible endpoint for hackathon partner credit).

    Returns:
        Configured LangGraphAdapter instance.
    """
    llm = ChatOpenAI(
        model=os.getenv("COORDINATOR_MODEL", "gpt-4o"),
        base_url=os.getenv("COORDINATOR_BASE_URL", "https://api.aimlapi.com/v1"),
        api_key=os.getenv("AIMLAPI_KEY", ""),
        temperature=0.1,
    )

    return LangGraphAdapter(
        llm=llm,
        checkpointer=InMemorySaver(),
        custom_section=COORDINATOR_SYSTEM_PROMPT,
    )


async def main() -> None:
    """Start the Coordinator agent and connect to Band."""
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
