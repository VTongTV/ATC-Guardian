/** ATC Guardian — animated SVG agent + system icons.
 *
 * Every agent gets a distinctive inline SVG with CSS keyframe animation.
 * SystemIcon provides reusable glyphs (warning, check, chevrons, diamond, dish).
 * All colours come from AGENT_COLORS — same palette used across the app.
 */

import React from "react";

// ─── Agent Identity Maps ──────────────────────────────────────────

export const AGENT_COLORS: Record<string, string> = {
  coordinator:        "#4488ff",
  "conflict-detector": "#ffaa00",
  "weather-analyst":   "#33ccff",
  "ground-ops":        "#33ff33",
  "emergency-response": "#ff3333",
  "safety-reviewer":   "#aa88ff",
  "system-ingest":     "#888888",
};

export const AGENT_HANDLES: string[] = [
  "coordinator",
  "conflict-detector",
  "weather-analyst",
  "ground-ops",
  "emergency-response",
  "safety-reviewer",
];

// ─── AgentIcon ────────────────────────────────────────────────────

interface AgentIconProps {
  handle: string;
  size?: number;
  color?: string;
}

export function AgentIcon({ handle, size = 16, color }: AgentIconProps): React.ReactElement {
  const c = color ?? AGENT_COLORS[handle] ?? "#888";
  const cls = "agent-icon-anim";

  switch (handle) {
    // ── Coordinator: radar crosshair with sweeping line ──
    case "coordinator":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" className={cls}>
          <circle cx="12" cy="12" r="9" fill="none" stroke={c} strokeWidth="1.5" opacity="0.4" />
          <circle cx="12" cy="12" r="5" fill="none" stroke={c} strokeWidth="1" opacity="0.3" />
          <line x1="12" y1="3" x2="12" y2="7" stroke={c} strokeWidth="1.5" />
          <line x1="12" y1="17" x2="12" y2="21" stroke={c} strokeWidth="1.5" />
          <line x1="3" y1="12" x2="7" y2="12" stroke={c} strokeWidth="1.5" />
          <line x1="17" y1="12" x2="21" y2="12" stroke={c} strokeWidth="1.5" />
          <g style={{ transformOrigin: "12px 12px", animation: "radar-sweep 3s linear infinite" }}>
            <line x1="12" y1="12" x2="12" y2="4" stroke={c} strokeWidth="2" strokeLinecap="round" />
          </g>
        </svg>
      );

    // ── Conflict Detector: alert triangle with pulsing "!" ──
    case "conflict-detector":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" className={cls}>
          <path d="M12 3 L22 20 H2 Z" fill="none" stroke={c} strokeWidth="1.5" strokeLinejoin="round" />
          <g style={{ animation: "alert-pulse 1.5s ease-in-out infinite" }}>
            <line x1="12" y1="10" x2="12" y2="14.5" stroke={c} strokeWidth="2.5" strokeLinecap="round" />
            <circle cx="12" cy="17" r="1.2" fill={c} />
          </g>
        </svg>
      );

    // ── Weather Analyst: cloud with lightning bolt ──
    case "weather-analyst":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" className={cls}>
          <path d="M6 15 Q2 15 2 11.5 Q2 8 6 8 Q6 4 10 4 Q14 4 14.5 7 Q18 6.5 19 9 Q21 10 20 13 Q19 15 16 15 Z" fill="none" stroke={c} strokeWidth="1.3" />
          <g style={{ animation: "lightning-flash 4s ease-in-out infinite" }}>
            <polygon points="11,15 9.5,19 12.5,18 11,22" fill={c} />
          </g>
        </svg>
      );

    // ── Ground Ops: aircraft silhouette banking ──
    case "ground-ops":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" className={cls}>
          <g style={{ transformOrigin: "12px 12px", animation: "aircraft-bank 2.5s ease-in-out infinite" }}>
            <path d="M12 4 L14 9 L21 11 L14 12 L13 18 L12 20 L11 18 L10 12 L3 11 L10 9 Z"
              fill="none" stroke={c} strokeWidth="1.5" strokeLinejoin="round" />
          </g>
        </svg>
      );

    // ── Emergency Response: rotating beacon ──
    case "emergency-response":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" className={cls}>
          <rect x="7" y="15" width="10" height="5" rx="1.5" fill="none" stroke={c} strokeWidth="1.3" />
          <g style={{ animation: "beacon-dome-pulse 1s ease-in-out infinite" }}>
            <path d="M8.5 15 Q8.5 10.5 12 10 Q15.5 10.5 15.5 15" fill="none" stroke={c} strokeWidth="1.5" />
          </g>
          <g style={{ transformOrigin: "12px 12px", animation: "beacon-rotate 2s linear infinite" }}>
            <line x1="12" y1="4" x2="12" y2="7" stroke={c} strokeWidth="1" opacity="0.6" />
            <line x1="19" y1="7" x2="17.5" y2="9" stroke={c} strokeWidth="1" opacity="0.6" />
            <line x1="5" y1="7" x2="6.5" y2="9" stroke={c} strokeWidth="1" opacity="0.6" />
          </g>
        </svg>
      );

    // ── Safety Reviewer: shield with checkmark ──
    case "safety-reviewer":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" className={cls}>
          <path d="M12 2 L20 6 V12 Q20 18 12 22 Q4 18 4 12 V6 Z"
            fill="none" stroke={c} strokeWidth="1.5" strokeLinejoin="round" />
          <polyline
            points="8,12 11,15 16,9"
            fill="none"
            stroke={c}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray="24"
            style={{ animation: "shield-draw 1.5s ease-out forwards" }}
          />
        </svg>
      );

    // ── System Ingest: dish with signal arcs ──
    case "system-ingest":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" className={cls}>
          <path d="M5 18 Q3 16 4 12 Q5 8 8 6" fill="none" stroke={c} strokeWidth="1.5" strokeLinecap="round" />
          <circle cx="14" cy="16" r="2" fill={c} opacity="0.7" />
          <g style={{ animation: "signal-arc 2s ease-out infinite", transformOrigin: "14px 16px" }}>
            <path d="M10 12 Q14 8 18 12" fill="none" stroke={c} strokeWidth="1.2" />
          </g>
          <g style={{ animation: "signal-arc 2s ease-out infinite 0.6s", transformOrigin: "14px 16px" }}>
            <path d="M8 9 Q14 4 20 9" fill="none" stroke={c} strokeWidth="1" opacity="0.5" />
          </g>
        </svg>
      );

    // ── Fallback: robot head with blinking eyes ──
    default:
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" className={cls}>
          <rect x="5" y="6" width="14" height="12" rx="3" fill="none" stroke={c} strokeWidth="1.5" />
          <line x1="12" y1="3" x2="12" y2="6" stroke={c} strokeWidth="1.5" />
          <circle cx="12" cy="3" r="1.2" fill={c} />
          <g style={{ animation: "eye-blink 5s ease-in-out infinite" }}>
            <circle cx="9" cy="11" r="1.5" fill={c} />
            <circle cx="15" cy="11" r="1.5" fill={c} />
          </g>
        </svg>
      );
  }
}

// ─── SystemIcon ───────────────────────────────────────────────────

interface SystemIconProps {
  type: "warning" | "check" | "chevron-right" | "chevron-left" | "diamond" | "dish";
  size?: number;
  color?: string;
}

export function SystemIcon({ type, size = 12, color }: SystemIconProps): React.ReactElement {
  const c = color ?? "currentColor";

  switch (type) {
    case "warning":
      return (
        <svg width={size} height={size} viewBox="0 0 16 16">
          <path d="M8 1.5 L14.5 14 H1.5 Z" fill="none" stroke={c} strokeWidth="1.2" strokeLinejoin="round" />
          <line x1="8" y1="6.5" x2="8" y2="9.5" stroke={c} strokeWidth="1.5" strokeLinecap="round" />
          <circle cx="8" cy="11.5" r="0.7" fill={c} />
        </svg>
      );
    case "check":
      return (
        <svg width={size} height={size} viewBox="0 0 16 16">
          <polyline points="3,8.5 6.5,12 13,4" fill="none" stroke={c} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "chevron-right":
      return (
        <svg width={size} height={size} viewBox="0 0 12 12">
          <polyline points="4,2 8,6 4,10" fill="none" stroke={c} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "chevron-left":
      return (
        <svg width={size} height={size} viewBox="0 0 12 12">
          <polyline points="8,2 4,6 8,10" fill="none" stroke={c} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "diamond":
      return (
        <svg width={size} height={size} viewBox="0 0 12 12">
          <polygon points="6,1 11,6 6,11 1,6" fill="none" stroke={c} strokeWidth="1.2" strokeLinejoin="round" />
        </svg>
      );
    case "dish":
      return (
        <svg width={size} height={size} viewBox="0 0 16 16">
          <path d="M2 13 Q0 10 2 7 Q4 4 7 3" fill="none" stroke={c} strokeWidth="1.3" strokeLinecap="round" />
          <path d="M4 13 Q3 11 4 9 Q5 7 7 6" fill="none" stroke={c} strokeWidth="1" strokeLinecap="round" opacity="0.6" />
          <circle cx="10" cy="11" r="1.5" fill={c} opacity="0.7" />
        </svg>
      );
  }
}
