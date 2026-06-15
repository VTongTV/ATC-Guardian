"""Shared LLM provider configuration resolver.

Centralises the ``resolve_llm_config`` logic that was previously
copy-pasted across every ``agents/*/agent.py``. Each agent now imports
:func:`resolve_llm_config` from here (AGENTS.md §9 forbids copy-pasted
code).

The resolver reads the ``LLM_PROVIDER`` env var (``openrouter``,
``aimlapi``, or ``featherless``) plus the corresponding provider
credentials, with an optional per-agent model override. All three
providers expose OpenAI-compatible endpoints, so the returned
``(base_url, api_key, model)`` tuple can be passed straight to a
``ChatOpenAI`` / ``PydanticAIAdapter`` / ``CrewAIAdapter`` client.
"""

from __future__ import annotations

import os

#: Supported provider identifiers.
SUPPORTED_PROVIDERS: tuple[str, ...] = ("openrouter", "aimlapi", "featherless")


def resolve_llm_config(agent_model_env_var: str) -> tuple[str, str, str]:
    """Resolve LLM provider config from shared environment variables.

    Reads the ``LLM_PROVIDER`` env var and the corresponding provider
    settings to determine the base URL, API key, and model name. A
    per-agent model override (``agent_model_env_var``) takes precedence
    over the provider default.

    Args:
        agent_model_env_var: Name of the env var that holds the per-agent
            model override (e.g. ``"COORDINATOR_MODEL"``).

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
        valid = " | ".join(SUPPORTED_PROVIDERS)
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
