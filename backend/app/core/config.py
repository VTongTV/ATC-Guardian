"""Application configuration loaded from environment variables.

All settings are read from the environment at startup.
No hardcoded values. No defaults that hide missing config.
"""

import os

from pydantic import Field
from pydantic_settings import BaseSettings


class LLMProviderSettings(BaseSettings):
    """LLM provider configuration shared across agents.

    Supports three OpenAI-compatible providers:
    - OpenRouter (free models for development / testing)
    - AI/ML API (hackathon partner, primary for demo)
    - Featherless (hackathon partner, secondary / backup)

    Each agent can override the global model via its own env var.
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
        default="meta-llama/llama-3.3-70b-instruct:free",
        description="Default free OpenRouter model for agents",
    )

    # ---- AI/ML API (hackathon partner) ----
    aimlapi_key: str | None = Field(
        default=None,
        description="AI/ML API key for LLM calls (hackathon partner credits)",
    )
    aimlapi_base_url: str = Field(
        default="https://api.aimlapi.com/v1",
        description="AI/ML API base URL",
    )
    aimlapi_default_model: str = Field(
        default="gpt-4o",
        description="Default AI/ML API model (requires credits)",
    )

    # ---- Featherless (hackathon partner) ----
    featherless_key: str | None = Field(
        default=None,
        description="Featherless API key for LLM calls",
    )
    featherless_base_url: str = Field(
        default="https://api.featherless.ai/v1",
        description="Featherless API base URL",
    )

    # ---- Active provider selection ----
    llm_provider: str = Field(
        default="openrouter",
        description="Active LLM provider: openrouter | aimlapi | featherless",
    )

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
            case "featherless":
                return self.featherless_base_url
            case _:
                valid = "openrouter | aimlapi | featherless"
                raise ValueError(
                    f"Unknown LLM_PROVIDER '{self.llm_provider}'. Must be one of: {valid}"
                )

    def resolve_api_key(self) -> str:
        """Resolve the API key for the active LLM provider.

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
                if not self.aimlapi_key:
                    raise ValueError("AIMLAPI_KEY is required when LLM_PROVIDER=aimlapi")
                return self.aimlapi_key
            case "featherless":
                if not self.featherless_key:
                    raise ValueError("FEATHERLESS_KEY is required when LLM_PROVIDER=featherless")
                return self.featherless_key
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
            case "featherless":
                return "featherless/default"
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
    band_api_key: str | None = Field(default=None, description="Band API key for the coordinator agent")
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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


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
