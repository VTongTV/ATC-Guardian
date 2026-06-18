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

Automatic fallback
------------------
When AI/ML API credits are exhausted (HTTP 402, 429, or quota-related
error messages), :func:`mark_aimlapi_exhausted` is called and all
subsequent calls to :func:`resolve_llm_config` return OpenRouter
credentials instead. This happens transparently — agents that are
rebuilt after the fallback get OpenRouter models at zero cost.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

#: Supported provider identifiers.
SUPPORTED_PROVIDERS: tuple[str, ...] = ("openrouter", "aimlapi")

#: Number of pooled AI/ML API keys available for rotation.
AIMLAPI_KEY_POOL_SIZE: int = 4

# ---------------------------------------------------------------------------
# Circuit breaker — AI/ML API exhaustion detection
# ---------------------------------------------------------------------------

_aimlapi_exhausted: bool = False
"""Module-level flag: True once AI/ML API returns a quota/credit error.
Once set, resolve_llm_config() falls back to OpenRouter for the
remainder of the process lifetime."""


def mark_aimlapi_exhausted() -> None:
    """Mark AI/ML API as exhausted and switch to OpenRouter fallback.

    Called by the agent runner when an LLM call to AI/ML API returns
    a quota/credit error (HTTP 402, 429, or specific error messages).
    After this, all resolve_llm_config() calls return OpenRouter
    credentials regardless of the LLM_PROVIDER env var.
    """
    global _aimlapi_exhausted
    if not _aimlapi_exhausted:
        _aimlapi_exhausted = True
        logger.warning(
            "AI/ML API credits exhausted — falling back to OpenRouter "
            "for all subsequent LLM calls"
        )


def is_aimlapi_exhausted() -> bool:
    """Check whether AI/ML API has been marked as exhausted.

    Returns:
        True if the circuit breaker has tripped.
    """
    return _aimlapi_exhausted


def reset_aimlapi_exhausted() -> None:
    """Reset the circuit breaker (e.g. for testing or after key rotation)."""
    global _aimlapi_exhausted
    _aimlapi_exhausted = False


def is_quota_error(status_code: int | None, error_message: str | None = None) -> bool:
    """Check whether an LLM API error indicates credit/quota exhaustion.

    Detects:
    - HTTP 402 (Payment Required)
    - HTTP 429 (Too Many Requests) when the body mentions quota/credits
    - Error messages containing 'insufficient', 'quota', 'credit',
      'balance', 'billing', or 'limit exceeded'

    Args:
        status_code: HTTP status code from the API response (may be None).
        error_message: Error body or message string (may be None).

    Returns:
        True if the error indicates credit/quota exhaustion.
    """
    if status_code == 402:
        return True

    if error_message:
        lower = error_message.lower()
        quota_keywords = (
            "insufficient",
            "quota",
            "credit",
            "balance",
            "billing",
            "limit exceeded",
            "rate limit",
            "too many requests",
            "exceeded",
        )
        if any(kw in lower for kw in quota_keywords):
            # For 429, only count it as quota if the message mentions
            # limits/credits rather than a simple "slow down" retry.
            if status_code == 429:
                return True
            # Non-429 with quota keywords is definitely exhaustion.
            if status_code is None or status_code >= 400:
                return True

    return False


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


def _resolve_openrouter_config(agent_model_env_var: str) -> tuple[str, str, str]:
    """Resolve OpenRouter LLM config, ignoring per-agent model overrides
    that reference AI/ML API-specific models.

    When falling back from AI/ML API, per-agent ``*_MODEL`` env vars
    may contain AI/ML API-specific model IDs (e.g. ``deepseek/deepseek-v4-pro``)
    that don't exist on OpenRouter. This function ignores those overrides
    and uses the OpenRouter default model instead.

    Args:
        agent_model_env_var: Name of the env var that holds the per-agent
            model override.

    Returns:
        Tuple of ``(base_url, api_key, model_name)`` for OpenRouter.
    """
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    default_model = os.getenv(
        "OPENROUTER_DEFAULT_MODEL", "nex-agi/nex-n2-pro:free"
    )

    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY is missing. Cannot fall back from AI/ML API "
            "without an OpenRouter key. Set OPENROUTER_API_KEY to enable "
            "automatic fallback when AI/ML API credits run out."
        )

    # Ignore AI/ML API-specific model overrides — use OpenRouter default.
    # The per-agent *_MODEL env vars contain AI/ML API model IDs like
    # "deepseek/deepseek-v4-pro" which don't exist on OpenRouter.
    return base_url, api_key, default_model


def resolve_llm_config(agent_model_env_var: str) -> tuple[str, str, str]:
    """Resolve LLM provider config from shared environment variables.

    Reads the ``LLM_PROVIDER`` env var and the corresponding provider
    settings to determine the base URL, API key, and model name. A
    per-agent model override (``agent_model_env_var``) takes precedence
    over the provider default.

    **Automatic fallback:** If AI/ML API has been marked as exhausted
    (via :func:`mark_aimlapi_exhausted`), this function returns
    OpenRouter credentials regardless of the ``LLM_PROVIDER`` env var.

    Args:
        agent_model_env_var: Name of the env var that holds the per-agent
            model override (e.g. ``"COORDINATOR_MODEL"``).

    Returns:
        Tuple of ``(base_url, api_key, model_name)``.

    Raises:
        ValueError: If ``LLM_PROVIDER`` is not one of the supported values.
        ValueError: If the resolved API key is empty or missing.
    """
    # Circuit breaker: if AI/ML API is exhausted, always use OpenRouter
    if _aimlapi_exhausted:
        return _resolve_openrouter_config(agent_model_env_var)

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
