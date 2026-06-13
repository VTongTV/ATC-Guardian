"""Canonical Pydantic models for the ATC Guardian system.

Every data structure exchanged between backend, agents, and frontend
is defined here. No raw dicts anywhere else in the codebase.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AlertSeverity(str, Enum):
    """Severity levels for conflict and weather alerts."""

    CAUTION = "caution"
    WARNING = "warning"
    CRITICAL = "critical"


class AircraftCategory(str, Enum):
    """ICAO wake turbulence category."""

    LIGHT = "L"
    MEDIUM = "M"
    HEAVY = "H"
    SUPER = "J"


class ConflictStatus(str, Enum):
    """Lifecycle status of a conflict advisory."""

    DETECTED = "detected"
    MONITORING = "monitoring"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class EmergencyPhase(str, Enum):
    """Emergency response phase per ICAO procedures."""

    UNCERTAINTY = "uncertainty"
    ALERT = "alert"
    DISTRESS = "distress"


class MessageType(str, Enum):
    """Types of messages exchanged between agents via Band."""

    CONFLICT_ADVISORY = "conflict_advisory"
    WEATHER_ADVISORY = "weather_advisory"
    EMERGENCY_DECLARATION = "emergency_declaration"
    GROUND_REQUEST = "ground_request"
    STATUS_UPDATE = "status_update"
    COORDINATION = "coordination"


# ---------------------------------------------------------------------------
# Core domain models
# ---------------------------------------------------------------------------


class AircraftState(BaseModel):
    """Snapshot of an aircraft's current state vector.

    All altitude values are in feet, speeds in knots, headings in degrees.
    Angular values use true north references (0°=N, 90°=E).
    """

    model_config = ConfigDict(frozen=True)

    callsign: str = Field(description="ICAO flight callsign (e.g. UAL123)")
    latitude: float = Field(ge=-90, le=90, description="Decimal degrees, north positive")
    longitude: float = Field(ge=-180, le=180, description="Decimal degrees, east positive")
    altitude_ft: int = Field(ge=0, description="Pressure altitude in feet")
    heading_deg: float = Field(ge=0, lt=360, description="True heading in degrees")
    speed_kts: float = Field(ge=0, description="Ground speed in knots")
    vertical_speed_fpm: int = Field(default=0, description="Vertical speed in feet per minute (+ climb, - descend)")
    squawk: str = Field(default="1200", min_length=4, max_length=4, description="Transponder squawk code")
    category: AircraftCategory = Field(default=AircraftCategory.MEDIUM, description="ICAO wake turbulence category")
    timestamp: datetime = Field(description="UTC time of this state observation")
    on_ground: bool = Field(default=False, description="True if aircraft is on the ground")


class PositionGeographic(BaseModel):
    """A latitude/longitude position with optional altitude."""

    model_config = ConfigDict(frozen=True)

    latitude: float = Field(ge=-90, le=90, description="Decimal degrees, north positive")
    longitude: float = Field(ge=-180, le=180, description="Decimal degrees, east positive")
    altitude_ft: int | None = Field(default=None, ge=0, description="Altitude in feet, if relevant")


# ---------------------------------------------------------------------------
# Conflict detection models
# ---------------------------------------------------------------------------


class CPAResult(BaseModel):
    """Result of a Closest Point of Approach calculation between two aircraft."""

    model_config = ConfigDict(frozen=True)

    aircraft_a_callsign: str = Field(description="Callsign of the first aircraft")
    aircraft_b_callsign: str = Field(description="Callsign of the second aircraft")
    min_distance_nm: float = Field(ge=0, description="Minimum distance at CPA in nautical miles")
    time_to_cpa_seconds: float = Field(ge=0, description="Seconds until CPA from current time")
    relative_bearing_deg: float = Field(ge=0, lt=360, description="Bearing from aircraft A to aircraft B at CPA")
    altitude_separation_ft: int = Field(description="Vertical separation at CPA in feet")
    is_conflict: bool = Field(description="True if CPA violates separation minimums")


class ConflictAdvisory(BaseModel):
    """A conflict advisory issued by the Conflict Detector agent.

    Contains the CPA data plus resolution suggestions.
    """

    model_config = ConfigDict(frozen=True)

    advisory_id: str = Field(description="Unique advisory identifier")
    timestamp: datetime = Field(description="UTC time of advisory creation")
    severity: AlertSeverity = Field(description="Alert severity level")
    status: ConflictStatus = Field(default=ConflictStatus.DETECTED, description="Advisory lifecycle status")
    cpa: CPAResult = Field(description="Closest Point of Approach data")
    resolution_hints: list[str] = Field(default_factory=list, description="Suggested resolution actions")


# ---------------------------------------------------------------------------
# Weather models
# ---------------------------------------------------------------------------


class SIGMETGeometry(BaseModel):
    """Geographic polygon defining a SIGMET area."""

    model_config = ConfigDict(frozen=True)

    points: list[PositionGeographic] = Field(min_length=3, description="Polygon vertices (min 3 for a valid area)")
    buffer_nm: float = Field(default=10.0, ge=0, description="Buffer zone around SIGMET in nautical miles")


class SIGMET(BaseModel):
    """Significant Meteorological Information advisory."""

    model_config = ConfigDict(frozen=True)

    sigmet_id: str = Field(description="Unique SIGMET identifier")
    phenomenon: str = Field(description="Weather phenomenon type (e.g. TS, TURB, ICE)")
    severity: AlertSeverity = Field(description="Weather severity")
    geometry: SIGMETGeometry = Field(description="Geographic area of the SIGMET")
    base_ft: int | None = Field(default=None, ge=0, description="Base altitude in feet")
    top_ft: int | None = Field(default=None, ge=0, description="Top altitude in feet")
    valid_from: datetime = Field(description="SIGMET validity start (UTC)")
    valid_to: datetime = Field(description="SIGMET validity end (UTC)")


class WeatherAdvisory(BaseModel):
    """A weather advisory issued by the Weather Analyst agent."""

    model_config = ConfigDict(frozen=True)

    advisory_id: str = Field(description="Unique advisory identifier")
    timestamp: datetime = Field(description="UTC time of advisory creation")
    severity: AlertSeverity = Field(description="Weather severity level")
    sigmet: SIGMET = Field(description="Source SIGMET data")
    affected_callsigns: list[str] = Field(default_factory=list, description="Aircraft callsigns in the affected area")
    deviation_hints: list[str] = Field(default_factory=list, description="Suggested deviation actions")


# ---------------------------------------------------------------------------
# Emergency models
# ---------------------------------------------------------------------------


class EmergencyDeclaration(BaseModel):
    """An emergency declaration triggered by squawk 7700 or agent escalation."""

    model_config = ConfigDict(frozen=True)

    emergency_id: str = Field(description="Unique emergency identifier")
    timestamp: datetime = Field(description="UTC time of emergency detection")
    callsign: str = Field(description="Aircraft in distress")
    phase: EmergencyPhase = Field(default=EmergencyPhase.DISTRESS, description="ICAO emergency phase")
    squawk_code: str = Field(description="Triggering squawk code")
    current_state: AircraftState = Field(description="Last known aircraft state")
    estimated_position: PositionGeographic = Field(description="Extrapolated position if data is stale")
    priority: AlertSeverity = Field(default=AlertSeverity.CRITICAL, description="Response priority")
    grace_period_active: bool = Field(default=True, description="Whether the initial grace period is still active")


# ---------------------------------------------------------------------------
# Ground operations models
# ---------------------------------------------------------------------------


class GroundRequest(BaseModel):
    """A request from an agent for ground services information."""

    model_config = ConfigDict(frozen=True)

    request_id: str = Field(description="Unique request identifier")
    timestamp: datetime = Field(description="UTC time of request")
    icao_code: str = Field(min_length=4, max_length=4, description="ICAO airport code (e.g. KJFK)")
    request_type: str = Field(description="Type of ground info requested (runway, atis, notam)")
    context_callsign: str | None = Field(default=None, description="Related aircraft callsign, if any")


class GroundResponse(BaseModel):
    """Response from the Ground Ops agent with airport information."""

    model_config = ConfigDict(frozen=True)

    request_id: str = Field(description="Matches the GroundRequest identifier")
    timestamp: datetime = Field(description="UTC time of response")
    icao_code: str = Field(min_length=4, max_length=4, description="ICAO airport code")
    active_runways: list[str] = Field(default_factory=list, description="Active runway designators")
    atis_info: str | None = Field(default=None, description="Current ATIS information code")
    notams: list[str] = Field(default_factory=list, description="Active NOTAMs for the airport")
    weather_summary: str | None = Field(default=None, description="Current METAR summary")


# ---------------------------------------------------------------------------
# Agent communication models
# ---------------------------------------------------------------------------


class AgentMessage(BaseModel):
    """Structured message exchanged between agents via Band.

    This model maps to Band's thenvoi_send_message format.
    """

    model_config = ConfigDict(frozen=True)

    message_id: str = Field(description="Unique message identifier")
    timestamp: datetime = Field(description="UTC time of message")
    sender: str = Field(description="Agent name that sent this message")
    message_type: MessageType = Field(description="Category of this message")
    target_agent: str | None = Field(default=None, description="Target agent name for directed messages")
    payload: ConflictAdvisory | WeatherAdvisory | EmergencyDeclaration | GroundRequest | GroundResponse | dict = Field(
        description="Typed message payload"
    )


# ---------------------------------------------------------------------------
# Scenario models
# ---------------------------------------------------------------------------


class ScenarioStep(BaseModel):
    """A single time-step in a demo scenario."""

    model_config = ConfigDict(frozen=True)

    elapsed_seconds: float = Field(ge=0, description="Seconds since scenario start")
    aircraft_states: list[AircraftState] = Field(description="All aircraft states at this step")
    events: list[AgentMessage] = Field(default_factory=list, description="Agent messages triggered at this step")


class ScenarioDefinition(BaseModel):
    """Complete definition of a demo scenario."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str = Field(description="Unique scenario identifier")
    name: str = Field(description="Human-readable scenario name")
    description: str = Field(description="Short scenario description")
    center_latitude: float = Field(ge=-90, le=90, description="Radar center latitude")
    center_longitude: float = Field(ge=-180, le=180, description="Radar center longitude")
    initial_states: list[AircraftState] = Field(description="Starting aircraft positions")
    steps: list[ScenarioStep] = Field(default_factory=list, description="Scenario time steps")


# ---------------------------------------------------------------------------
# Data snapshot models (backend API responses)
# ---------------------------------------------------------------------------


class RadarSnapshot(BaseModel):
    """A single snapshot of all aircraft states for the radar display."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime = Field(description="UTC time of this snapshot")
    aircraft: list[AircraftState] = Field(description="All tracked aircraft states")
    conflicts: list[ConflictAdvisory] = Field(default_factory=list, description="Active conflict advisories")
    weather_advisories: list[WeatherAdvisory] = Field(default_factory=list, description="Active weather advisories")
    emergencies: list[EmergencyDeclaration] = Field(default_factory=list, description="Active emergencies")
