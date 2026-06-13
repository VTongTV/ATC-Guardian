"""Application configuration loaded from environment variables.

All settings are read from the environment at startup.
No hardcoded values. No defaults that hide missing config.
"""

import os

from pydantic import Field
from pydantic_settings import BaseSettings


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

    # AI/ML API (primary LLM provider)
    aimlapi_key: str | None = Field(default=None, description="AI/ML API key for LLM calls")

    # Featherless (secondary LLM provider)
    featherless_key: str | None = Field(default=None, description="Featherless API key for LLM calls")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


def get_settings() -> AppSettings:
    """Create and return application settings from environment.

    Returns:
        AppSettings instance populated from env vars / .env file.
    """
    return AppSettings()
