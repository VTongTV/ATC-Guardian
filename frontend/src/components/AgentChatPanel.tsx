/** ATC Guardian — agent-to-agent chat panel derived from audit message events. */

import { useEffect, useRef, useState } from "react";
import type { AuditEvent } from "../lib/types";

/** Color mapping for agent names. */
const AGENT_COLORS: Record<string, string> = {
  coordinator:         "#4488ff",
  "conflict-detector": "#ffaa00",
  "weather-analyst":   "#33ccff",
  "ground-ops":        "#33ff33",
  "emergency-response": "#ff3333",
};

/** Short labels for agents. */
const AGENT_SHORT: Record<string, string> = {
  coordinator:       "COORD",
  "conflict-detector": "CNFLT",
  "weather-analyst":   "WTHR",
  "ground-ops":        "GND",
  "emergency-response": "EMRG",
};

/** Format ISO timestamp to HH:MM:SS. */
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

/** Get colour for an agent, falling back to white. */
function agentColor(name: string): string {
  return AGENT_COLORS[name] ?? "#ffffff";
}

/** Get short label for an agent. */
function agentShort(name: string): string {
  return AGENT_SHORT[name] ?? name.toUpperCase().slice(0, 5);
}

/** Highlight @mentions in a message string. Splits on @word patterns and
 *  returns spans with cyan colour for matched mentions. */
function renderContent(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const regex = /(@\w[\w-]*)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(
        <span key={`t${lastIndex}`}>{text.slice(lastIndex, match.index)}</span>,
      );
    }
    parts.push(
      <span key={`m${match.index}`} style={{ color: "#00ffff", fontWeight: "bold" }}>
        {match[1]}
      </span>,
    );
    lastIndex = regex.lastIndex;
  }

  if (lastIndex < text.length) {
    parts.push(<span key={`t${lastIndex}`}>{text.slice(lastIndex)}</span>);
  }

  return parts.length > 0 ? parts : [<span key="empty">{text}</span>];
}

/** AgentChatPanel — polls audit message events and renders a chat-room view. */
export function AgentChatPanel(): React.ReactElement {
  const [messages, setMessages] = useState<AuditEvent[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;

    async function fetchMessages(): Promise<void> {
      try {
        const res = await fetch("/audit/events?event_type=message&limit=50");
        if (!res.ok) return;
        const data: AuditEvent[] = await res.json();
        if (alive) setMessages(data);
      } catch {
        /* backend offline */
      }
    }

    fetchMessages();
    const timer = window.setInterval(fetchMessages, 5000);

    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  // Auto-scroll when new messages arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const panelStyle: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    backgroundColor: "#0a0a0a",
    overflow: "hidden",
  };

  const headerStyle: React.CSSProperties = {
    fontSize: "0.7rem",
    color: "#33ff33",
    padding: "0.3rem 0.5rem",
    borderBottom: "1px solid #1a3a1a",
    flexShrink: 0,
    letterSpacing: "0.05em",
  };

  const listStyle: React.CSSProperties = {
    flex: 1,
    overflowY: "auto",
    padding: "0.25rem 0.5rem",
  };

  return (
    <div style={panelStyle}>
      <div style={headerStyle}>AGENT COMMS ({messages.length})</div>
      <div style={listStyle}>
        {messages.map((evt) => {
          const isTarget = evt.target_agent != null;
          const agentName = isTarget ? evt.target_agent! : evt.agent_name;
          const fromName = isTarget ? evt.agent_name : "system";
          const color = agentColor(agentName);
          const fromColor = agentColor(fromName);

          return (
            <div
              key={evt.id}
              style={{
                fontSize: "0.65rem",
                fontFamily: "monospace",
                padding: "0.2rem 0",
                borderBottom: "1px solid #111",
                textAlign: isTarget ? "right" : "left",
              }}
            >
              <div style={{ marginBottom: "0.1rem" }}>
                {/* Timestamp */}
                <span style={{ color: "#555" }}>
                  {formatTime(evt.timestamp)}{" "}
                </span>
                {/* From label */}
                <span style={{ color: fromColor }}>
                  [{agentShort(fromName)}]
                </span>
                <span style={{ color: "#555" }}> to </span>
                {/* To label */}
                <span style={{ color: color, fontWeight: "bold" }}>
                  [{agentShort(agentName)}]
                </span>
              </div>
              <div
                style={{
                  color: "#ccc",
                  paddingLeft: isTarget ? "0" : "1rem",
                  paddingRight: isTarget ? "1rem" : "0",
                }}
              >
                {renderContent(evt.content)}
              </div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
