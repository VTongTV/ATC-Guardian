/** ATC Guardian — agent-to-agent chat panel derived from audit message events.
 *
 * Renders each agent message as a colour-coded box (left accent + tinted
 * background keyed off the originating agent) and parses the body as
 * GitHub-flavoured Markdown so tables, headers, bold and bullet lists that
 * the agents emit render legibly instead of as a wall of text. @mentions
 * inside plain text are highlighted in cyan on top of the markdown.
 */

import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AuditEvent } from "../lib/types";
import { useAtcStore } from "../stores/atcStore";

/** Color mapping for agent names. */
const AGENT_COLORS: Record<string, string> = {
  coordinator: "#4488ff",
  "conflict-detector": "#ffaa00",
  "weather-analyst": "#33ccff",
  "ground-ops": "#33ff33",
  "emergency-response": "#ff3333",
  "safety-reviewer": "#aa88ff", // the 6th roster agent was missing
  "system-ingest": "#888888", // backend posts @mentions as this identity
};

/** Short labels for agents. */
const AGENT_SHORT: Record<string, string> = {
  coordinator: "COORD",
  "conflict-detector": "CNFLT",
  "weather-analyst": "WTHR",
  "ground-ops": "GND",
  "emergency-response": "EMRG",
  "safety-reviewer": "SAFE",
  "system-ingest": "SYS",
};

/** Event types that represent a readable agent-to-agent message — i.e.
 *  the conversational content the chat panel should show, as opposed to
 *  internal tool_call / tool_result / thought plumbing. Band tags agent
 *  replies as "text"; "message" is kept for compatibility. */
const CONVERSATIONAL_TYPES: ReadonlySet<string> = new Set(["text", "message"]);

/** Convert a #rrggbb hex colour to an `rgba(r,g,b,a)` string with the
 *  given alpha. Used to tint message boxes without hard-coding shades. */
function withAlpha(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

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

/** Highlight @mentions inside a plain-text string. Only applied to text
 *  nodes (never to code/tables), so markdown structure is preserved. */
function renderTextWithMentions(text: string, keyPrefix: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const regex = /(@\w[\w-]*)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let i = 0;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(<span key={`${keyPrefix}t${i++}`}>{text.slice(lastIndex, match.index)}</span>);
    }
    parts.push(
      <span key={`${keyPrefix}m${i++}`} style={{ color: "#00ffff", fontWeight: "bold" }}>
        {match[1]}
      </span>,
    );
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length) {
    parts.push(<span key={`${keyPrefix}t${i++}`}>{text.slice(lastIndex)}</span>);
  }
  return parts.length > 0 ? parts : [text];
}

/** Shared markdown component styles. Kept as a function of the agent accent
 *  colour so tables/code blend with the per-message tint. */
function markdownComponents(accent: string) {
  return {
    // Re-highlight @mentions in plain text without touching code/tables.
    p: ({ children }: { children?: ReactNode }) => {
      const out: ReactNode[] = [];
      let k = 0;
      const walk = (node: ReactNode): void => {
        if (typeof node === "string") {
          out.push(...renderTextWithMentions(node, `p${k++}`));
        } else if (Array.isArray(node)) {
          node.forEach(walk);
        } else {
          out.push(<span key={`p${k++}`}>{node}</span>);
        }
      };
      (Array.isArray(children) ? children : [children]).forEach(walk);
      return <>{out}</>;
    },
    table: ({ children }: { children?: ReactNode }) => (
      <div style={{ overflowX: "auto", margin: "0.25rem 0" }}>
        <table
          style={{
            borderCollapse: "collapse",
            width: "100%",
            fontSize: "0.6rem",
            color: "#ccc",
          }}
        >
          {children}
        </table>
      </div>
    ),
    th: ({ children }: { children?: ReactNode }) => (
      <th
        style={{
          border: `1px solid ${withAlpha(accent, 0.4)}`,
          padding: "0.1rem 0.25rem",
          textAlign: "left",
          color: accent,
        }}
      >
        {children}
      </th>
    ),
    td: ({ children }: { children?: ReactNode }) => (
      <td
        style={{
          border: `1px solid ${withAlpha(accent, 0.25)}`,
          padding: "0.1rem 0.25rem",
        }}
      >
        {children}
      </td>
    ),
    code: ({ children }: { children?: ReactNode }) => (
      <code
        style={{
          backgroundColor: "rgba(255,255,255,0.08)",
          padding: "0 0.15rem",
          borderRadius: "2px",
          fontFamily: "monospace",
        }}
      >
        {children}
      </code>
    ),
  };
}

/** AgentChatPanel — polls audit message events and renders a chat-room view. */
export function AgentChatPanel(): React.ReactElement {
  const [messages, setMessages] = useState<AuditEvent[]>([]);
  const listRef = useRef<HTMLDivElement>(null);
  const prevLenRef = useRef(0);
  const noteAgentReply = useAtcStore((s) => s.noteAgentReply);

  useEffect(() => {
    let alive = true;

    async function fetchMessages(): Promise<void> {
      try {
        // Agent replies are stored as event_type "text" (Band's ChatMessage
        // type) — never literally "message". Pull the full recent set and
        // keep only the conversational types so the chat view stays clean
        // (no thought/tool_call/tool_result plumbing). The backend's
        // event_type filter is single-valued, so we filter client-side.
        const res = await fetch("/audit/events?limit=100");
        if (!res.ok) return;
        const data: AuditEvent[] = await res.json();
        if (alive) {
          // Backend returns newest-first; a chat reads oldest-first, so
          // take the most recent conversational events and reverse them.
          const next = data
            .filter((e) => CONVERSATIONAL_TYPES.has(e.event_type))
            .slice(0, 50)
            .reverse();
          // When new messages arrive, signal the AGENT TEAM panel to flash
          // the node of the agent that sent the most recent one.
          if (next.length > prevLenRef.current && next.length > 0) {
            noteAgentReply(next[next.length - 1].agent_name);
          }
          setMessages(next);
        }
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
  }, [noteAgentReply]);

  // Auto-scroll to the newest message. useLayoutEffect fires before
  // the browser paints so there is no "flash of top-then-bottom".
  useLayoutEffect(() => {
    const el = listRef.current;
    if (!el) return;
    const prevLen = prevLenRef.current;
    prevLenRef.current = messages.length;
    const grew = messages.length > prevLen;
    const firstPopulate = prevLen === 0 && messages.length > 0;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    // Always scroll on first populate or when new messages arrive.
    // When count is unchanged, only re-stick if user is near bottom.
    if (grew || firstPopulate || nearBottom) {
      el.scrollTop = el.scrollHeight;
    }
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
    padding: "0.4rem 0.5rem",
    display: "flex",
    flexDirection: "column",
    gap: "0.3rem",
  };

  const emptyStyle: React.CSSProperties = {
    color: "#666",
    fontSize: "0.6rem",
    fontFamily: "monospace",
    padding: "0.5rem",
    lineHeight: 1.5,
    fontStyle: "italic",
  };

  // Markdown components are stable per-render; memoise per accent colour so
  // tables/code don't needlessly re-create between polls.
  const componentsCache = useMemo(() => {
    const cache: Record<string, ReturnType<typeof markdownComponents>> = {};
    return (accent: string) => (cache[accent] ??= markdownComponents(accent));
  }, []);

  return (
    <div style={panelStyle}>
      <div style={headerStyle}>AGENT COMMS ({messages.length})</div>
      <div ref={listRef} style={listStyle}>
        {messages.length === 0 ? (
          <div style={emptyStyle}>
            No agent messages yet.
          </div>
        ) : null}
        {messages.map((evt) => {
          // fromName = the agent that SENT the message (drives colour)
          // agentName = the recipient (or sender if no target)
          const fromName = evt.agent_name;
          const agentName = evt.target_agent ?? evt.agent_name;
          const color = agentColor(agentName);
          const fromColor = agentColor(fromName);
          // Box is colour-coded to the SENDER.
          const accent = fromColor;

          return (
            <div
              key={evt.id}
              style={{
                border: `1px solid ${withAlpha(accent, 0.35)}`,
                borderLeft: `3px solid ${accent}`,
                backgroundColor: withAlpha(accent, 0.08),
                borderRadius: "3px",
                padding: "0.25rem 0.35rem",
                fontSize: "0.65rem",
                fontFamily: "monospace",
                textAlign: "left",
              }}
            >
              <div style={{ marginBottom: "0.15rem", whiteSpace: "nowrap" }}>
                <span style={{ color: "#555" }}>{formatTime(evt.timestamp)} </span>
                <span style={{ color: fromColor }}>[{agentShort(fromName)}]</span>
                <span style={{ color: "#555" }}> to </span>
                <span style={{ color, fontWeight: "bold" }}>[{agentShort(agentName)}]</span>
              </div>
              <div style={{ color: "#ccc", lineHeight: 1.35 }}>
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={componentsCache(accent)}
                >
                  {evt.content}
                </ReactMarkdown>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
