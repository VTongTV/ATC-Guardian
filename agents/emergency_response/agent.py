"""ATC Guardian Emergency Response Agent — main entry point.

Runs as a Band agent using LangGraphAdapter. Receives emergency
dispatches from the Coordinator (squawk 7700/7500/7600), classifies
the emergency phase, and coordinates emergency procedures.
"""

import asyncio
import logging
import os

from band import Agent
from band.adapters import LangGraphAdapter
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from prompts import EMERGENCY_RESPONSE_SYSTEM_PROMPT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_emergency_response_adapter() -> LangGraphAdapter:
    """Create the LangGraphAdapter for the Emergency Response agent.

    Uses ChatOpenAI with AI/ML API as the LLM provider.

    Returns:
        Configured LangGraphAdapter instance.
    """
    llm = ChatOpenAI(
        model=os.getenv("EMERGENCY_RESPONSE_MODEL", "gpt-4o"),
        base_url=os.getenv("EMERGENCY_RESPONSE_BASE_URL", "https://api.aimlapi.com/v1"),
        api_key=os.getenv("AIMLAPI_KEY", ""),
        temperature=0.0,
    )

    return LangGraphAdapter(
        llm=llm,
        checkpointer=InMemorySaver(),
        custom_section=EMERGENCY_RESPONSE_SYSTEM_PROMPT,
    )


async def main() -> None:
    """Start the Emergency Response agent and connect to Band."""
    adapter = create_emergency_response_adapter()

    agent = Agent.create(
        adapter=adapter,
        agent_id=os.environ["EMERGENCY_RESPONSE_AGENT_ID"],
        api_key=os.environ["EMERGENCY_RESPONSE_API_KEY"],
    )

    logger.info("Starting ATC Guardian Emergency Response agent...")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
