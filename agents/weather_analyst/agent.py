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


def resolve_llm_config(agent_model_env_var: str) -> tuple[str, str, str]:
    """Resolve LLM provider config from shared environment variables.

    Reads the ``LLM_PROVIDER`` env var and the corresponding provider
    settings to determine the base URL, API key, and model name.  A
    per-agent model override (``agent_model_env_var``) takes precedence
    over the provider default.

    Args:
        agent_model_env_var: Name of the env var that holds the per-agent
            model override (e.g. ``"WEATHER_ANALYST_MODEL"``).

    Returns:
        Tuple of ``(base_url, api_key, model_name)``.

    Raises:
        ValueError: If ``LLM_PROVIDER`` is not one of the supported values.
        ValueError: If the resolved API key is empty or missing.
    """
    provider = os.getenv("LLM_PROVIDER", "openrouter")
    agent_model = os.getenv(agent_model_env_var)

    if provider == "openrouter":
        base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        default_model = os.getenv(
            "OPENROUTER_DEFAULT_MODEL", "meta-llama/llama-3.3-70b-instruct:free"
        )
    elif provider == "aimlapi":
        base_url = os.getenv("AIMLAPI_BASE_URL", "https://api.aimlapi.com/v1")
        api_key = os.getenv("AIMLAPI_KEY", "")
        default_model = os.getenv("AIMLAPI_DEFAULT_MODEL", "gpt-4o")
    elif provider == "featherless":
        base_url = os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")
        api_key = os.getenv("FEATHERLESS_KEY", "")
        default_model = "featherless/default"
    else:
        valid = "openrouter | aimlapi | featherless"
        raise ValueError(
            f"Unknown LLM_PROVIDER '{provider}'. Must be one of: {valid}"
        )

    if not api_key:
        raise ValueError(
            f"API key for provider '{provider}' is missing. "
            f"Set the corresponding environment variable "
            f"(OPENROUTER_API_KEY / AIMLAPI_KEY / FEATHERLESS_KEY)."
        )

    model = agent_model or default_model
    return base_url, api_key, model


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
