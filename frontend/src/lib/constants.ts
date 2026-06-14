/** Frontend constants for the ATC Guardian radar display. */

/** Default radar display range in nautical miles. */
export const RADAR_RANGE_NM = 60;

/** Number of historical positions per blip trail. */
export const RADAR_BLIP_TRAIL_LENGTH = 5;

/** Duration of one radar sweep rotation in seconds. */
export const RADAR_SWEEP_DURATION_SECONDS = 4;

/** Polling interval for backend data in milliseconds. */
export const DATA_POLL_INTERVAL_MS = 4000;

// ─── Radar Display Colors ──────────────────────────────────────────
/** Blip color for non-emergency aircraft. */
export const COLOR_NORMAL = "#33ff33";

/** Blip color for emergency squawk 7700 (Mayday). */
export const COLOR_7700 = "#ff3333";

/** Blip color for emergency squawk 7500 (Hijack). */
export const COLOR_7500 = "#ff8800";

/** Blip color for emergency squawk 7600 (Comms failure). */
export const COLOR_7600 = "#ffaa00";

/** Conflict line color for caution/warning severity. */
export const COLOR_CONFLICT_CAUTION = "#ffaa00";

/** Conflict line color for critical severity. */
export const COLOR_CONFLICT_CRITICAL = "#ff3333";

/** Range ring color (dim green). */
export const COLOR_RANGE_RING = "#1a4a1a";

/** Range ring label color. */
export const COLOR_RANGE_RING_LABEL = "#2a5a2a";

/** Selected aircraft highlight ring color. */
export const COLOR_SELECTED_RING = "#ffffff";

// ─── Blink Animation Intervals ─────────────────────────────────────
/** Blink interval for 7700 emergency (fast). */
export const BLINK_INTERVAL_7700_MS = 500;

/** Blink interval for 7500 emergency (medium). */
export const BLINK_INTERVAL_7500_MS = 800;

/** Blink interval for 7600 emergency (slow). */
export const BLINK_INTERVAL_7600_MS = 1200;

// ─── Heading Vectors ───────────────────────────────────────────────
/** Heading projection distance in nautical miles. */
export const HEADING_PROJECTION_NM = 4;

// ─── Radar Sweep ───────────────────────────────────────────────────
/** Opacity of the radar sweep gradient start. */
export const SWEEP_GRADIENT_OPACITY = 0.15;

/** Angle in degrees for the sweep gradient fade. */
export const SWEEP_GRADIENT_ANGLE_DEG = 30;
