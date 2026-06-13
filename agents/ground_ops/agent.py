"""ATC Guardian Ground Ops Agent — main entry point.

Runs as a Band agent using LangGraphAdapter. Receives ground information
requests from the Coordinator or Emergency Response agent and responds
with airport data (runways, ATIS, NOTAMs).
"""

import asyncio
import logging
import os

from band import Agent
from band.adapters import LangGraphAdapter
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from prompts import GROUND_OPS_SYSTEM_PROMPT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_ground_ops_adapter() -> LangGraphAdapter:
    """Create the LangGraphAdapter for the Ground Ops agent.

    Uses ChatOpenAI with AI/ML API as the LLM provider.

    Returns:
        Configured LangGraphAdapter instance.
    """
    llm = ChatOpenAI(
        model=os.getenv("GROUND_OPS_MODEL", "gpt-4o"),
        base_url=os.getenv("GROUND_OPS_BASE_URL", "https://api.aimlapi.com/v1"),
        api_key=os.getenv("AIMLAPI_KEY", ""),
        temperature=0.1,
    )

    return LangGraphAdapter(
        llm=llm,
        checkpointer=InMemorySaver(),
        custom_section=GROUND_OPS_SYSTEM_PROMPT,
    )


async def main() -> None:
    """Start the Ground Ops agent and connect to Band."""
    adapter = create_ground_ops_adapter()

    agent = Agent.create(
        adapter=adapter,
        agent_id=os.environ["GROUND_OPS_AGENT_ID"],
        api_key=os.environ["GROUND_OPS_API_KEY"],
    )

    logger.info("Starting ATC Guardian Ground Ops agent...")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
