"""Application configuration loaded from environment variables.

All settings are read from the environment at startup.
No hardcoded values. No defaults that hide missing config.
"""

import os

from pydantic import Field
from pydantic_settings import BaseSettings


class LLMProviderSettings(BaseSettings):
    """LLM provider configuration shared across agents.

    Supports two OpenAI-compatible providers:
    - AI/ML API (hackathon partner, primary for demo) — GPT-5.1 flagship,
      Gemini 3.5 Flash, and more; powers the 'Best Use of AI/ML API' prize.
    - OpenRouter (free models for development / testing)

    Each agent can override the global model via its own env var.

    Budget: we have 4 AI/ML API keys ($10 each, $40 total). Set
    ``AIMLAPI_KEY_1`` .. ``AIMLAPI_KEY_4`` to spread load across them;
    agents rotate through the pool. ``AIMLAPI_KEY`` works as a single-key
    fallback.
    """

    # ---- OpenRouter (free models) ----
    openrouter_api_key: str | None = Field(
        default=None,
        description="OpenRouter API key (free signup at openrouter.ai)",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base URL",
    )
    openrouter_default_model: str = Field(
        default="nex-agi/nex-n2-pro:free",
        description="Default free OpenRouter model for agents (Nex-N2-Pro — 397B/17B-active agentic MoE, $0/M tokens).",
    )

    # ---- AI/ML API (hackathon partner — primary for demo) ----
    aimlapi_key: str | None = Field(
        default=None,
        description="AI/ML API key (single). Use AIMLAPI_KEY_1..4 for a pool.",
    )
    aimlapi_key_1: str | None = Field(default=None, description="AI/ML API pooled key 1")
    aimlapi_key_2: str | None = Field(default=None, description="AI/ML API pooled key 2")
    aimlapi_key_3: str | None = Field(default=None, description="AI/ML API pooled key 3")
    aimlapi_key_4: str | None = Field(default=None, description="AI/ML API pooled key 4")
    aimlapi_base_url: str = Field(
        default="https://api.aimlapi.com/v1",
        description="AI/ML API base URL",
    )
    aimlapi_default_model: str = Field(
        default="deepseek/deepseek-v4-pro",
        description="Default AI/ML API model (DeepSeek V4 Pro — strong reasoning + reliable structured output). The per-agent *_MODEL overrides in partner_routing.py swap in GPT-5.1, GLM-5.1, Kimi K2-6, etc. where they fit best.",
    )

    # ---- Active provider selection ----
    llm_provider: str = Field(
        default="openrouter",
        description="Active LLM provider: openrouter | aimlapi",
    )

    @property
    def aimlapi_pooled_keys(self) -> list[str]:
        """Return the non-empty pooled AI/ML API keys (1..4).

        Returns:
            List of configured pooled keys (may be empty).
        """
        return [k for k in (self.aimlapi_key_1, self.aimlapi_key_2, self.aimlapi_key_3, self.aimlapi_key_4) if k]

    def resolve_base_url(self) -> str:
        """Resolve the base URL for the active LLM provider.

        Returns:
            OpenAI-compatible base URL for the selected provider.

        Raises:
            ValueError: If llm_provider is not one of the supported values.
        """
        match self.llm_provider:
            case "openrouter":
                return self.openrouter_base_url
            case "aimlapi":
                return self.aimlapi_base_url
            case _:
                valid = "openrouter | aimlapi"
                raise ValueError(
                    f"Unknown LLM_PROVIDER '{self.llm_provider}'. Must be one of: {valid}"
                )

    def resolve_api_key(self) -> str:
        """Resolve the API key for the active LLM provider.

        For AI/ML API, prefers the pooled keys (AIMLAPI_KEY_1..4) so demo
        load spreads across all four $10 keys; falls back to the single
        AIMLAPI_KEY.

        Returns:
            API key string for the selected provider.

        Raises:
            ValueError: If the key for the active provider is not set.
        """
        match self.llm_provider:
            case "openrouter":
                if not self.openrouter_api_key:
                    raise ValueError("OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter")
                return self.openrouter_api_key
            case "aimlapi":
                pooled = self.aimlapi_pooled_keys
                if pooled:
                    return pooled[0]
                if not self.aimlapi_key:
                    raise ValueError(
                        "AIMLAPI_KEY (or AIMLAPI_KEY_1..4 pool) is required when LLM_PROVIDER=aimlapi"
                    )
                return self.aimlapi_key
            case _:
                raise ValueError(f"Unknown LLM_PROVIDER '{self.llm_provider}'")

    def resolve_model(self, agent_model_override: str | None = None) -> str:
        """Resolve the model name, with optional per-agent override.

        Args:
            agent_model_override: Per-agent model name from env (e.g. COORDINATOR_MODEL).
                If set, takes priority over the provider default.

        Returns:
            Model name string for the LLM API call.
        """
        if agent_model_override:
            return agent_model_override
        match self.llm_provider:
            case "openrouter":
                return self.openrouter_default_model
            case "aimlapi":
                return self.aimlapi_default_model
            case _:
                return self.openrouter_default_model


class AppSettings(BaseSettings):
    """Application-level settings for the ATC Guardian backend.

    Values are read from environment variables or a .env file.
    Required fields without defaults will raise if not set.
    """

    app_name: str = Field(default="ATC Guardian", description="Application name for logging and headers")
    debug: bool = Field(default=False, description="Enable debug mode with verbose logging")
    host: str = Field(default="0.0.0.0", description="HTTP server bind address")
    port: int = Field(default=8000, ge=1, le=65535, description="HTTP server bind port")

    # CORS
    cors_origin: str = Field(default="http://localhost:5173", description="Allowed CORS origin for frontend")

    # Simulation
    default_scenario_id: str = Field(default="SCN-A", description="Default scenario to load on startup")
    simulation_interval_seconds: float = Field(
        default=4.0, gt=0, description="Seconds between simulated data updates"
    )

    # OpenSky (optional — simulation-only mode if not set)
    opensky_username: str | None = Field(default=None, description="OpenSky Network username")
    opensky_password: str | None = Field(default=None, description="OpenSky Network password")

    # Band (optional — simulation-only mode if not set)
    band_mode: str = Field(
        default="sim",
        description="Band transport mode: sim (offline in-process) | live (real Band REST)",
    )
    band_api_key: str | None = Field(default=None, description="Band API key for the system-ingest identity")
    band_room_id: str | None = Field(default=None, description="Band room ID for agent communication")

    # LLM provider settings (embedded for backend convenience)
    # Agents load these independently, but the backend may need them for
    # proxying or audit purposes.
    llm: LLMProviderSettings = Field(default_factory=LLMProviderSettings)

    # Per-agent model overrides (env vars like COORDINATOR_MODEL, etc.)
    coordinator_model: str | None = Field(default=None, description="Override model for Coordinator agent")
    conflict_detector_model: str | None = Field(default=None, description="Override model for Conflict Detector agent")
    weather_analyst_model: str | None = Field(default=None, description="Override model for Weather Analyst agent")
    ground_ops_model: str | None = Field(default=None, description="Override model for Ground Ops agent")
    emergency_response_model: str | None = Field(default=None, description="Override model for Emergency Response agent")
    safety_reviewer_model: str | None = Field(default=None, description="Override model for Safety Reviewer agent")

    # Coordinator Agent (Band credentials)
    coordinator_agent_id: str | None = Field(default=None, description="Band agent ID for Coordinator")
    coordinator_api_key: str | None = Field(default=None, description="Band API key for Coordinator")

    # Conflict Detector Agent (Band credentials)
    conflict_detector_agent_id: str | None = Field(default=None, description="Band agent ID for Conflict Detector")
    conflict_detector_api_key: str | None = Field(default=None, description="Band API key for Conflict Detector")

    # Weather Analyst Agent (Band credentials)
    weather_analyst_agent_id: str | None = Field(default=None, description="Band agent ID for Weather Analyst")
    weather_analyst_api_key: str | None = Field(default=None, description="Band API key for Weather Analyst")

    # Ground Ops Agent (Band credentials)
    ground_ops_agent_id: str | None = Field(default=None, description="Band agent ID for Ground Ops")
    ground_ops_api_key: str | None = Field(default=None, description="Band API key for Ground Ops")

    # Emergency Response Agent (Band credentials)
    emergency_response_agent_id: str | None = Field(default=None, description="Band agent ID for Emergency Response")
    emergency_response_api_key: str | None = Field(default=None, description="Band API key for Emergency Response")

    # Safety Reviewer Agent (Band credentials) — adversarial reviewer
    safety_reviewer_agent_id: str | None = Field(default=None, description="Band agent ID for Safety Reviewer")
    safety_reviewer_api_key: str | None = Field(default=None, description="Band API key for Safety Reviewer")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


def get_settings() -> AppSettings:
    """Create and return application settings from environment.

    Returns:
        AppSettings instance populated from env vars / .env file.
    """
    return AppSettings()


def get_llm_settings() -> LLMProviderSettings:
    """Create and return LLM provider settings from environment.

    Returns:
        LLMProviderSettings instance populated from env vars / .env file.
    """
    return LLMProviderSettings()
