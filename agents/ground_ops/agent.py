"""ATC Guardian Ground Ops Agent — main entry point.

Runs as a Band agent using LangGraphAdapter. Receives ground information
requests from the Coordinator or Emergency Response agent and responds
with airport data (runways, ATIS, NOTAMs).
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

from prompts import GROUND_OPS_SYSTEM_PROMPT
from shared.llm_config import resolve_llm_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_ground_ops_adapter() -> LangGraphAdapter:
    """Create the LangGraphAdapter for the Ground Ops agent.

    Uses ChatOpenAI with the multi-provider LLM configuration resolved
    from shared environment variables.

    Returns:
        Configured LangGraphAdapter instance.
    """
    base_url, api_key, model = resolve_llm_config("GROUND_OPS_MODEL")
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
        max_tokens=512,
        reasoning_effort="low",
    )

    return LangGraphAdapter(
        llm=llm,
        checkpointer=InMemorySaver(),
        custom_section=GROUND_OPS_SYSTEM_PROMPT,
    )


async def main() -> None:
    """Start the Ground Ops agent and connect to Band."""
    from dotenv import load_dotenv

    load_dotenv()

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
