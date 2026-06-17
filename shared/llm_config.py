"""Shared LLM provider configuration resolver.

Centralises the ``resolve_llm_config`` logic that was previously
copy-pasted across every ``agents/*/agent.py``. Each agent now imports
:func:`resolve_llm_config` from here (AGENTS.md §9 forbids copy-pasted
code).

The resolver reads the ``LLM_PROVIDER`` env var (``openrouter`` or
``aimlapi``) plus the corresponding provider credentials, with an
optional per-agent model override. Both providers expose OpenAI-
compatible endpoints, so the returned ``(base_url, api_key, model)``
tuple can be passed straight to a ``ChatOpenAI`` /
``PydanticAIAdapter`` / ``CrewAIAdapter`` client.

AI/ML API is the recommended provider for the demo: it gives access to
GPT-5.1 (flagship, configurable reasoning) plus Gemini 3.5 Flash and
other current models, and powers the 'Best Use of AI/ML API' partner
prize.

Budget note: we have 4 AI/ML API keys ($10 each, $40 total). To spread
load and avoid exhausting one key during a demo, agents rotate through
``AIMLAPI_KEY_1`` .. ``AIMLAPI_KEY_4`` when set; otherwise the single
``AIMLAPI_KEY`` is used.
"""

from __future__ import annotations

import os

#: Supported provider identifiers.
SUPPORTED_PROVIDERS: tuple[str, ...] = ("openrouter", "aimlapi")

#: Number of pooled AI/ML API keys available for rotation.
AIMLAPI_KEY_POOL_SIZE: int = 4


def _resolve_aimlapi_key() -> str:
    """Pick an AI/ML API key, preferring the rotated pool.

    Reads ``AIMLAPI_KEY_1`` .. ``AIMLAPI_KEY_4`` first so demo load
    spreads across all four keys (each has $10). Falls back to the
    single ``AIMLAPI_KEY`` for simple setups.

    Returns:
        A non-empty API key string.

    Raises:
        ValueError: If no AI/ML API key is configured anywhere.
    """
    pooled = [
        os.getenv(f"AIMLAPI_KEY_{i}")
        for i in range(1, AIMLAPI_KEY_POOL_SIZE + 1)
    ]
    pooled = [k for k in pooled if k]
    if pooled:
        # Stable round-robin by process so each agent process gets a
        # different key when started in sequence. Uses a hash of the
        # agent module path to keep it deterministic per process.
        caller = os.getenv("AIMLAPI_CALLER_TAG") or str(os.getpid())
        return pooled[hash(caller) % len(pooled)]
    single = os.getenv("AIMLAPI_KEY", "")
    if single:
        return single
    raise ValueError(
        "AIMLAPI_KEY is missing. Set AIMLAPI_KEY (single) or "
        "AIMLAPI_KEY_1 .. AIMLAPI_KEY_4 (pooled) to distribute load."
    )


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
            "OPENROUTER_DEFAULT_MODEL", "nex-agi/nex-n2-pro:free"
        )
    elif provider == "aimlapi":
        base_url = os.getenv("AIMLAPI_BASE_URL", "https://api.aimlapi.com/v1")
        api_key = _resolve_aimlapi_key()
        default_model = os.getenv(
            "AIMLAPI_DEFAULT_MODEL", "deepseek/deepseek-v4-pro"
        )
    else:
        valid = " | ".join(SUPPORTED_PROVIDERS)
        raise ValueError(
            f"Unknown LLM_PROVIDER '{provider}'. Must be one of: {valid}"
        )

    if not api_key:
        raise ValueError(
            f"API key for provider '{provider}' is missing. "
            f"Set the corresponding environment variable "
            f"(OPENROUTER_API_KEY / AIMLAPI_KEY)."
        )

    model = agent_model or default_model
    return base_url, api_key, model
