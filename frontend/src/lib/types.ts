/** ATC Guardian frontend — TypeScript type definitions.

Mirror the Pydantic models from shared/models.py so the
frontend has type-safe access to backend data.
*/

/** Aircraft state vector from the simulation or live data source. */
export interface AircraftState {
  callsign: string;
  latitude: number;
  longitude: number;
  altitude_ft: number;
  heading_deg: number;
  speed_kts: number;
  vertical_speed_fpm: number;
  squawk: string;
  category: "L" | "M" | "H" | "J";
  timestamp: string;
  on_ground: boolean;
}

/** Severity levels for alerts. */
export type AlertSeverity = "caution" | "warning" | "critical";

/** Conflict status lifecycle. */
export type ConflictStatus = "detected" | "monitoring" | "resolved" | "escalated";

/** CPA calculation result between two aircraft. */
export interface CPAResult {
  aircraft_a_callsign: string;
  aircraft_b_callsign: string;
  min_distance_nm: number;
  time_to_cpa_seconds: number;
  relative_bearing_deg: number;
  altitude_separation_ft: number;
  is_conflict: boolean;
}

/** Conflict advisory from the Conflict Detector agent. */
export interface ConflictAdvisory {
  advisory_id: string;
  timestamp: string;
  severity: AlertSeverity;
  status: ConflictStatus;
  cpa: CPAResult;
  resolution_hints: string[];
}

/** Weather advisory from the Weather Analyst agent. */
export interface WeatherAdvisory {
  advisory_id: string;
  timestamp: string;
  severity: AlertSeverity;
  affected_callsigns: string[];
  deviation_hints: string[];
}

/** Emergency declaration from the Emergency Response agent. */
export interface EmergencyDeclaration {
  emergency_id: string;
  timestamp: string;
  callsign: string;
  phase: "uncertainty" | "alert" | "distress";
  squawk_code: string;
  priority: AlertSeverity;
  grace_period_active: boolean;
}

/** Radar snapshot from the backend API. */
export interface RadarSnapshot {
  timestamp: string;
  center_latitude: number;
  center_longitude: number;
  scenario_id: string;
  elapsed_seconds: number;
  aircraft: AircraftState[];
  conflicts: ConflictAdvisory[];
  weather_advisories: WeatherAdvisory[];
  emergencies: EmergencyDeclaration[];
}

/** Audit event from the /audit/events endpoint. */
export interface AuditEvent {
  id: number;
  timestamp: string;
  agent_name: string;
  event_type: string;
  content: string;
  metadata_json: string | null;
  target_agent: string | null;
  scenario_id: string | null;
}

/** Decision lifecycle status (human-on-the-loop). */
export type DecisionStatus = "pending" | "approved" | "rejected" | "modified";

/** A proposed agent action awaiting controller approval. */
export interface ControllerDecision {
  decision_id: string;
  created_at: string;
  resolved_at: string | null;
  status: DecisionStatus;
  scenario_id: string;
  advisory_kind: string;
  summary: string;
  agent_recommendation: string;
  reviewer_verdict: string;
  evidence: Record<string, unknown>;
  controller_action: string | null;
  controller_note: string | null;
}

/** Request body for resolving a pending decision. */
export interface ResolveDecisionRequest {
  action: "APPROVED" | "REJECTED" | "MODIFIED";
  controller_note?: string;
}
