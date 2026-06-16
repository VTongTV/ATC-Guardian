"""Constants for the ATC Guardian system.

All numeric literals used across the project are defined here.
No magic numbers anywhere else.
"""

# ---------------------------------------------------------------------------
# Separation minima
# ---------------------------------------------------------------------------

SEPARATION_MINIMUM_NM: float = 5.0
"""Lateral separation minimum in nautical miles for conflict detection."""

VERTICAL_SEPARATION_MINIMUM_FT: int = 1000
"""Vertical separation minimum in feet (FL290 and below: 1000 ft RVSM)."""

VERTICAL_SEPARATION_MINIMUM_RVSM_FT: int = 1000
"""RVSM vertical separation (FL290–FL410) in feet."""

# ---------------------------------------------------------------------------
# Conflict detection thresholds
# ---------------------------------------------------------------------------

CPA_ALERT_THRESHOLD_NM: float = 5.0
"""Distance threshold at which a CPA alert is generated."""

CPA_CRITICAL_THRESHOLD_NM: float = 3.0
"""Distance threshold for a critical (red) CPA alert."""

CPA_TIME_HORIZON_SECONDS: int = 300
"""Look-ahead time window for CPA calculation (5 minutes)."""

# ---------------------------------------------------------------------------
# Unit conversion factors
# ---------------------------------------------------------------------------

METERS_TO_FEET: float = 3.28084
"""Multiply meters by this to convert to feet."""

FEET_TO_METERS: float = 0.3048
"""Multiply feet by this to convert to meters."""

METERS_PER_SECOND_TO_KNOTS: float = 1.94384
"""Multiply m/s by this to convert to knots."""

KNOTS_TO_METERS_PER_SECOND: float = 0.514444
"""Multiply knots by this to convert to m/s."""

METERS_PER_SECOND_TO_FPM: float = 196.85
"""Multiply m/s vertical speed by this to convert to feet per minute."""

FPM_TO_METERS_PER_SECOND: float = 0.00508
"""Multiply feet per minute by this to convert to m/s."""

# ---------------------------------------------------------------------------
# Earth geometry
# ---------------------------------------------------------------------------

EARTH_RADIUS_NM: float = 3440.065
"""Mean Earth radius in nautical miles."""

EARTH_RADIUS_KM: float = 6371.0
"""Mean Earth radius in kilometers."""

# ---------------------------------------------------------------------------
# Transponder / squawk codes
# ---------------------------------------------------------------------------

EMERGENCY_SQUAWK_CODE: str = "7700"
"""Standard transponder code for an aircraft emergency."""

HIJACK_SQUAWK_CODE: str = "7500"
"""Standard transponder code for hijack."""

RADIO_FAILURE_SQUAWK_CODE: str = "7600"
"""Standard transponder code for radio failure."""

# ---------------------------------------------------------------------------
# Emergency descent parameters
# ---------------------------------------------------------------------------

EMERGENCY_DESCENT_RATE_FPM: int = 1500
"""Typical emergency descent rate in feet per minute."""

EMERGENCY_DESCENT_RATE_MAX_FPM: int = 2000
"""Maximum realistic emergency descent rate in feet per minute."""

EMERGENCY_SPEED_KTS: int = 220
"""Typical emergency approach speed in knots."""

EMERGENCY_GRACE_PERIOD_SECONDS: int = 60
"""Grace period after emergency declaration before escalating (seconds)."""

# ---------------------------------------------------------------------------
# Altitude references
# ---------------------------------------------------------------------------

TRANSITION_ALTITUDE_FT: int = 18000
"""Transition altitude in feet (US airspace)."""

RVSM_LOWER_BOUND_FT: int = 29000
"""Lower bound of RVSM airspace in feet (FL290)."""

RVSM_UPPER_BOUND_FT: int = 41000
"""Upper bound of standard RVSM airspace in feet (FL410)."""

# ---------------------------------------------------------------------------
# Data refresh intervals
# ---------------------------------------------------------------------------

SIMULATED_DATA_INTERVAL_SECONDS: float = 4.0
"""Interval between simulated data updates in seconds."""

OPENSKY_POLL_INTERVAL_SECONDS: float = 10.0
"""Minimum interval between OpenSky API polls in seconds."""

BAND_POLL_INTERVAL_SECONDS: float = 3.0
"""Interval between Band REST API message polls in seconds."""

# ---------------------------------------------------------------------------
# API rate limits
# ---------------------------------------------------------------------------

OPENSKY_DAILY_CREDIT_LIMIT: int = 4000
"""OpenSky free account daily credit limit."""

AWC_RATE_LIMIT_PER_MINUTE: int = 100
"""AWC API rate limit in requests per minute."""

# ---------------------------------------------------------------------------
# Band platform limits
# ---------------------------------------------------------------------------

BAND_DATA_RETENTION_HOURS: int = 24
"""Band free tier data retention period in hours."""

BAND_MESSAGE_PAGE_SIZE: int = 50
"""Number of messages to fetch per Band REST API poll."""

# ---------------------------------------------------------------------------
# Scenario timing
# ---------------------------------------------------------------------------

SCENARIO_DURATION_SECONDS: int = 300
"""Default scenario duration for demos (5 minutes)."""

SCENARIO_WARMUP_SECONDS: int = 10
"""Warmup period before scenario events begin (seconds)."""

# ---------------------------------------------------------------------------
# Frontend display
# ---------------------------------------------------------------------------

RADAR_RANGE_NM: float = 60.0
"""Default radar display range in nautical miles."""

RADAR_SWEEP_DURATION_SECONDS: float = 4.0
"""Duration of one radar sweep rotation in seconds."""

RADAR_BLIP_TRAIL_LENGTH: int = 5
"""Number of historical positions to show as a trailing dot."""

# ---------------------------------------------------------------------------
# LLM provider endpoints (OpenRouter — free models for development)
# ---------------------------------------------------------------------------

OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
"""OpenRouter API base URL (OpenAI-compatible)."""

OPENROUTER_DEFAULT_MODEL: str = "nex-agi/nex-n2-pro:free"
"""Default free OpenRouter model — Nex-N2-Pro is a 397B total / 17B active
agentic MoE that excels at tool-calling and multi-step reasoning, ideal for
the agent collaboration loop. Free ($0/M tokens). Verified 2026-06."""

OPENROUTER_ROUTER_MODEL: str = "openrouter/free"
"""OpenRouter free router — auto-selects best free model per request."""

OPENROUTER_FREE_MODELS: dict[str, str] = {
    "agentic": "nex-agi/nex-n2-pro:free",
    "reasoning": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "coding": "qwen/qwen3-coder:free",
    "general": "meta-llama/llama-3.3-70b-instruct:free",
    "lightweight": "openai/gpt-oss-20b:free",
    "multimodal": "google/gemma-4-31b-it:free",
}
"""Curated free OpenRouter models by use-case. All support tool calling."""

OPENROUTER_RATE_LIMIT_RPM: int = 20
"""Free-tier rate limit in requests per minute (per model)."""

OPENROUTER_RATE_LIMIT_RPD: int = 200
"""Free-tier rate limit in requests per day (per model)."""

# ---------------------------------------------------------------------------
# AI/ML API (hackathon partner — primary LLM for demo)
# ---------------------------------------------------------------------------

AIMLAPI_BASE_URL: str = "https://api.aimlapi.com/v1"
"""AI/ML API base URL (OpenAI-compatible)."""

AIMLAPI_DEFAULT_MODEL: str = "deepseek/deepseek-v4-pro"
"""Default AI/ML API model. DeepSeek V4 Pro pairs strong analytical
reasoning with reliable structured JSON output — the safest single
fallback when an agent has no per-agent model override. Other models in
the pool (GPT-5.1, Gemini 3.5 Flash, GLM-5.1, Kimi K2-6) are applied via
the per-agent overrides in partner_routing.py."""

AIMLAPI_REASONING_MODEL: str = "openai/gpt-5-1"
"""AI/ML API reasoning variant for analysis-heavy agents."""

AIMLAPI_FAST_MODEL: str = "google/gemini-3.5-flash"
"""Low-latency AI/ML API model for tool-call-heavy agents."""
