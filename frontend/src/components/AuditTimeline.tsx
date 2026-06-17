/** ATC Guardian — scrollable audit timeline of agent decisions and communications. */

import { useEffect, useRef, useState } from "react";
import type { AuditEvent } from "../lib/types";

/** Color and icon mapping for event types. */
const EVENT_STYLE: Record<string, { color: string; icon: string }> = {
  thought:     { color: "#888888", icon: "*" },
  task:        { color: "#33ff33", icon: ">" },
  message:     { color: "#4488ff", icon: "->" },
  error:       { color: "#ff3333", icon: "!" },
  tool_call:   { color: "#ffaa00", icon: "+" },
  tool_result: { color: "#aa88ff", icon: "=" },
};

/** Short agent name labels. */
const AGENT_SHORT: Record<string, string> = {
  coordinator:       "COORD",
  "conflict-detector": "CNFLT",
  "weather-analyst":   "WTHR",
  "ground-ops":        "GND",
  "emergency-response": "EMRG",
};

/** Format an ISO timestamp to HH:MM:SS. */
function formatTime(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  } catch {
    return "??:??:??";
  }
}

/** Resolve style for an event type. */
function getEventStyle(eventType: string): { color: string; icon: string } {
  return EVENT_STYLE[eventType] ?? { color: "#888888", icon: "-" };
}

/** Resolve short agent label. */
function getAgentLabel(name: string): string {
  return AGENT_SHORT[name] ?? name.toUpperCase().slice(0, 5);
}

/** AuditTimeline — polls /audit/events and renders a scrolling event log. */
export function AuditTimeline(): React.ReactElement {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;

    async function fetchEvents(): Promise<void> {
      try {
        const res = await fetch("/audit/events?limit=50");
        if (!res.ok) return;
        const data: AuditEvent[] = await res.json();
        if (alive) setEvents(data);
      } catch {
        /* backend offline — keep showing last known events */
      }
    }

    fetchEvents();
    const timer = window.setInterval(fetchEvents, 5000);

    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  // Auto-scroll when new events arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  const panelStyle: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    backgroundColor: "var(--bg-deep)",
    overflow: "hidden",
  };

  const headerStyle: React.CSSProperties = {
    fontSize: "0.7rem",
    color: "var(--color-nominal)",
    padding: "0.3rem 0.5rem",
    borderBottom: "1px solid var(--border-mid)",
    flexShrink: 0,
    letterSpacing: "0.05em",
    background: "linear-gradient(180deg, var(--bg-overlay) 0%, var(--bg-mid) 100%)",
    borderRadius: "var(--radius-lg) var(--radius-lg) 0 0",
  };

  const listStyle: React.CSSProperties = {
    flex: 1,
    overflowY: "auto",
    padding: "0.25rem 0.5rem",
  };

  return (
    <div style={panelStyle}>
      <div style={headerStyle}>AUDIT LOG ({events.length})</div>
      <div style={listStyle}>
        {events.map((evt) => {
          const style = getEventStyle(evt.event_type);
          const agentLabel = getAgentLabel(evt.agent_name);
          const targetLabel = evt.target_agent
            ? ` -> ${getAgentLabel(evt.target_agent)}`
            : "";

          return (
            <div
              key={evt.id}
              style={{
                fontSize: "0.65rem",
                fontFamily: "var(--font-mono)",
                padding: "0.15rem 0",
                borderBottom: "1px solid var(--border-dim)",
                lineHeight: "1.3",
                transition: "background-color var(--transition-fast)",
              }}
            >
              {/* Timestamp */}
              <span style={{ color: "var(--text-muted)" }}>{formatTime(evt.timestamp)} </span>
              {/* Agent label */}
              <span style={{ color: style.color, fontWeight: "bold" }}>
                [{agentLabel}]
              </span>
              {/* Event type badge */}
              <span
                style={{
                  color: style.color,
                  margin: "0 0.2rem",
                  opacity: 0.8,
                }}
              >
                {style.icon}
              </span>
              {/* Target agent if present */}
              {targetLabel && (
                <span style={{ color: "var(--text-muted)" }}>{targetLabel} </span>
              )}
              {/* Content */}
              <span style={{ color: "var(--text-primary)" }}>{evt.content}</span>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
