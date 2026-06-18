/** ATC Guardian — agent-to-agent chat panel derived from audit message events.
 *
 * Renders each agent message as a structured card with:
 * - Colored sender avatar + name (resolved from UUIDs)
 * - @mention chips with agent colors
 * - Structured data key-value chips
 * - Message type indicator (colored left border)
 * - Per-agent filter and jump-to-latest control
 */

import React, { useEffect, useLayoutEffect, useMemo, useRef, useState, useCallback, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AuditEvent } from "../lib/types";
import { useAtcStore } from "../stores/atcStore";
import { AgentIcon, AGENT_COLORS as SHARED_AGENT_COLORS, SystemIcon } from "./AgentIcons";

// ─── Agent Color & Identity Maps ────────────────────────────────────

const AGENT_COLORS: Record<string, string> = {
  coordinator: "#4488ff",
  "conflict-detector": "#ffaa00",
  "weather-analyst": "#33ccff",
  "ground-ops": "#33ff33",
  "emergency-response": "#ff3333",
  "safety-reviewer": "#aa88ff",
  "system-ingest": "#888888",
};

const AGENT_LABELS: Record<string, string> = {
  coordinator: "Coordinator",
  "conflict-detector": "Conflict Detector",
  "weather-analyst": "Weather Analyst",
  "ground-ops": "Ground Ops",
  "emergency-response": "Emergency Response",
  "safety-reviewer": "Safety Reviewer",
  "system-ingest": "System",
};

const AGENT_SHORT: Record<string, string> = {
  coordinator: "COORD",
  "conflict-detector": "CNFLT",
  "weather-analyst": "WTHR",
  "ground-ops": "GND",
  "emergency-response": "EMRG",
  "safety-reviewer": "SAFE",
  "system-ingest": "SYS",
};

function normalizeAgentHandle(name: string): string {
  if (/^[a-z][\w-]*$/.test(name)) return name;
  return name.toLowerCase().replace(/\s+/g, "-");
}

function agentColor(name: string): string {
  return AGENT_COLORS[normalizeAgentHandle(name)] ?? "#ffffff";
}

function agentLabel(name: string): string {
  return AGENT_LABELS[normalizeAgentHandle(name)] ?? name;
}

function agentShort(name: string): string {
  return AGENT_SHORT[normalizeAgentHandle(name)] ?? name.toUpperCase().slice(0, 5);
}

// ─── UUID Resolution ────────────────────────────────────────────────

/** Build a UUID→handle mapping from audit events by cross-referencing
 *  metadata_json.mentions (which contain resolved handles) with any
 *  @[[uuid]] patterns in content. */
function buildUuidMap(events: AuditEvent[]): Map<string, string> {
  const map = new Map<string, string>();
  for (const evt of events) {
    // Parse metadata to get resolved mentions
    let mentions: string[] = [];
    if (evt.metadata_json) {
      try {
        const meta = JSON.parse(evt.metadata_json);
        if (Array.isArray(meta.mentions)) {
          mentions = meta.mentions.filter((m: unknown): m is string => typeof m === "string");
        }
      } catch { /* not JSON */ }
    }
    // Find @[[uuid]] patterns in content
    const uuidPattern = /@\[\[([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\]\]/gi;
    const uuidsInContent = new Set<string>();
    let match: RegExpExecArray | null;
    while ((match = uuidPattern.exec(evt.content)) !== null) {
      uuidsInContent.add(match[1].toLowerCase());
    }
    // Also match @[uuid] without double brackets
    const singlePattern = /@\[([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\]/gi;
    while ((match = singlePattern.exec(evt.content)) !== null) {
      uuidsInContent.add(match[1].toLowerCase());
    }
    // Map: if we have UUIDs in content and resolved mentions, map first UUID to first mention
    // This is heuristic — in practice, messages mention one agent at a time
    if (uuidsInContent.size > 0 && mentions.length > 0) {
      for (const uuid of uuidsInContent) {
        if (!map.has(uuid)) {
          // Find the best matching mention (prefer non-system-ingest)
          const handle = mentions.find(m => m !== "system-ingest") ?? mentions[0];
          map.set(uuid, handle);
        }
      }
    }
  }
  return map;
}

// ─── Text Processing ────────────────────────────────────────────────

const CONVERSATIONAL_TYPES: ReadonlySet<string> = new Set(["text", "message"]);

function withAlpha(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** Normalize plain-text numbered/bulleted lists into proper markdown.
 *  Agents often write "1. Step one\n2. Step two" without the blank line
 *  that markdown requires, causing ReactMarkdown to render them inline.
 *  This function detects such patterns and adds the required newlines. */
function normalizeMarkdownLists(text: string): string {
  const lines = text.split("\n");
  const result: string[] = [];
  let inList = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const isNumberedItem = /^\d+\.\s/.test(line);
    const isBulletItem = /^[-*•]\s/.test(line);
    const isListItem = isNumberedItem || isBulletItem;

    if (isListItem && !inList) {
      // Add blank line before first list item if previous line is not blank
      if (result.length > 0 && result[result.length - 1].trim() !== "") {
        result.push("");
      }
      inList = true;
    } else if (!isListItem && inList) {
      inList = false;
    }

    result.push(line);
  }

  return result.join("\n");
}

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

/** Detect message type from content keywords for severity coloring. */
function detectMessageType(content: string): "warning" | "escalation" | "advisory" | "situation" {
  const lower = content.toLowerCase();
  if (lower.includes("emergency") || lower.includes("7700") || lower.includes("mayday") || lower.includes("panic") || lower.includes("loss of separation"))
    return "warning";
  if (lower.includes("escalat") || lower.includes("urgent") || lower.includes("critical") || lower.includes("immediate"))
    return "escalation";
  if (lower.includes("advisory") || lower.includes("conflict") || lower.includes("cpa") || lower.includes("sigmet") || lower.includes("deviation"))
    return "advisory";
  return "situation";
}

const TYPE_COLORS: Record<string, string> = {
  warning: "#ff3333",
  escalation: "#ff8800",
  advisory: "#ffaa00",
  situation: "#4488ff",
};

const TYPE_LABELS: Record<string, string> = {
  warning: "⚠ WARNING",
  escalation: "↑ ESCALATION",
  advisory: "◆ ADVISORY",
  situation: "● SITUATION",
};

// ─── Structured Data Extraction ─────────────────────────────────────

interface StructuredField {
  key: string;
  value: string;
}

function extractStructuredFields(content: string): [StructuredField[], string] {
  const fields: StructuredField[] = [];
  const lines = content.split('\n');
  const remaining: string[] = [];

  // Patterns to extract as structured chips — only match explicit key:value patterns
  const patterns: Array<{ key: string; regex: RegExp }> = [
    { key: "CPA", regex: /CPA\s+(?:Distance\s*)?[:\|=]?\s*([\d.]+)\s*(?:nm|NM)/i },
    { key: "Time to CPA", regex: /(?:Time?\s*to\s*CPA|T\s*CPA)\s*[:\|=]\s*([\d.]+)\s*s/i },
    { key: "Separation", regex: /(?:Separation|Sep(?:aration)?\s*Dist(?:ance)?)\s*[:\|=]\s*([\d.]+)\s*(?:nm|NM|ft)/i },
    { key: "Squawk", regex: /(?:SQ|Squawk)\s*[:\|=]?\s*(\d{4})/i },
    { key: "Altitude", regex: /(?:Alt(?:itude)?)\s*[:\|=]\s*([\d,]+)\s*(?:ft)?/i },
    { key: "Phase", regex: /(?:Emergency\s*Phase|Phase)\s*[:\|=]\s*(\w+)/i },
    { key: "Severity", regex: /(?:Severity)\s*[:\|=]\s*(\w+)/i },
    { key: "HDG", regex: /(?:Heading|HDG|Deviation\s*Heading)\s*[:\|=]?\s*(\d{3})\s*°?/i },
    { key: "ICAO Min", regex: /(?:ICAO\s*(?:Min(?:imum)?|sep))\s*[:\|=]\s*([\d.]+)\s*(?:nm|NM)/i },
    { key: "SIGMET", regex: /(?:SIGMET\s*(?:ID)?)\s*[:\|=]\s*(\S+)/i },
  ];

  for (const line of lines) {
    let matched = false;
    for (const { key, regex } of patterns) {
      const m = line.match(regex);
      if (m && m.index !== undefined) {
        // Only extract if the pattern appears as a clear key:value or standalone data point
        const beforeMatch = line.slice(0, m.index).trim();
        // Only match if the key is at the start of the line or preceded by minimal text
        if (beforeMatch.length <= 3 || /[:\|=]\s*$/.test(beforeMatch)) {
          fields.push({ key, value: m[1] || m[0] });
          matched = true;
          break;
        }
      }
    }
    if (!matched) {
      remaining.push(line);
    }
  }

  return [fields, remaining.join('\n').trim()];
}

// ─── Mention Rendering ──────────────────────────────────────────────

/** Collapsible message body — shows first 2 lines by default, expand on click. */
function CollapsibleMessageBody({
  children,
  accent,
}: {
  children: ReactNode;
  accent: string;
}): React.ReactElement {
  const [expanded, setExpanded] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const [isLong, setIsLong] = useState(false);

  useEffect(() => {
    const el = contentRef.current;
    if (el) {
      // Check if content exceeds ~4 lines (line-height 1.65 × 13px ≈ 86px)
      setIsLong(el.scrollHeight > 90);
    }
  }, [children]);

  return (
    <div style={{ position: "relative" }}>
      <div
        ref={contentRef}
        style={{
          maxHeight: expanded ? "none" : "4.2em",
          overflow: expanded ? "visible" : "hidden",
          transition: "max-height var(--transition-med)",
        }}
      >
        {children}
      </div>
      {isLong && (
        <button
          onClick={() => setExpanded(!expanded)}
          aria-label={expanded ? "Collapse message" : "Expand full message"}
          style={{
            display: "block",
            width: "100%",
            padding: "4px 0",
            marginTop: "2px",
            background: "none",
            border: "none",
            color: accent,
            fontSize: "var(--fs-micro)",
            fontFamily: "var(--font-mono)",
            cursor: "pointer",
            textAlign: "center",
            letterSpacing: "0.04em",
            opacity: 0.7,
            transition: "opacity var(--transition-fast)",
          }}
          onMouseEnter={(e) => { (e.target as HTMLElement).style.opacity = "1"; }}
          onMouseLeave={(e) => { (e.target as HTMLElement).style.opacity = "0.7"; }}
        >
          {expanded ? "▾ COLLAPSE" : "▸ SHOW FULL"}
        </button>
      )}
      {!expanded && isLong && (
        <div style={{
          position: "absolute",
          bottom: "18px",
          left: 0,
          right: 0,
          height: "24px",
          background: "linear-gradient(0deg, var(--bg-deep) 20%, transparent 100%)",
          pointerEvents: "none",
        }} />
      )}
    </div>
  );
}

/** Render text with @mentions as colored chips. */
function renderMentionChips(
  text: string,
  uuidMap: Map<string, string>,
  keyPrefix: string,
): ReactNode[] {
  const parts: ReactNode[] = [];
  // Match @[[uuid]], @[uuid], and @agent-name patterns
  const regex = /@\[\[([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\]\]|@\[([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\]|@(\w[\w-]*)/gi;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let i = 0;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(<span key={`${keyPrefix}t${i++}`}>{text.slice(lastIndex, match.index)}</span>);
    }

    let handle: string | null = null;
    if (match[1]) {
      // @[[uuid]] format
      handle = uuidMap.get(match[1].toLowerCase()) ?? null;
    } else if (match[2]) {
      // @[uuid] format
      handle = uuidMap.get(match[2].toLowerCase()) ?? null;
    } else if (match[3]) {
      // @agent-name format
      handle = normalizeAgentHandle(match[3]);
    }

    if (handle && AGENT_COLORS[handle]) {
      const color = AGENT_COLORS[handle];
      const label = agentLabel(handle);
      parts.push(
        <span
          key={`${keyPrefix}m${i++}`}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "2px",
            padding: "0 5px",
            borderRadius: "var(--radius-sm)",
            fontSize: "0.58rem",
            fontWeight: 600,
            backgroundColor: withAlpha(color, 0.15),
            color: color,
            border: `1px solid ${withAlpha(color, 0.3)}`,
            whiteSpace: "nowrap",
            lineHeight: "1.4",
            verticalAlign: "middle",
            transition: "background-color var(--transition-fast)",
          }}
        >
          <AgentIcon handle={handle} size={10} color={AGENT_COLORS[handle] ?? "#fff"} />
          {label}
        </span>,
      );
    } else {
      // Unresolved mention — show as a generic chip
      parts.push(
        <span
          key={`${keyPrefix}m${i++}`}
          style={{
            display: "inline-flex",
            alignItems: "center",
            padding: "0 5px",
            borderRadius: "var(--radius-sm)",
            fontSize: "0.58rem",
            fontWeight: 500,
            backgroundColor: "rgba(136,136,136,0.15)",
            color: "#888",
            border: "1px solid rgba(136,136,136,0.3)",
            whiteSpace: "nowrap",
            lineHeight: "1.4",
            verticalAlign: "middle",
          }}
        >
          🤖 Agent
        </span>,
      );
    }
    lastIndex = regex.lastIndex;
  }

  if (lastIndex < text.length) {
    parts.push(<span key={`${keyPrefix}t${i++}`}>{text.slice(lastIndex)}</span>);
  }
  return parts.length > 0 ? parts : [text];
}

// ─── Markdown Components ────────────────────────────────────────────

function markdownComponents(accent: string, uuidMap: Map<string, string>) {
  return {
    p: ({ children }: { children?: ReactNode }) => {
      const out: ReactNode[] = [];
      let k = 0;
      const walk = (node: ReactNode): void => {
        if (typeof node === "string") {
          out.push(...renderMentionChips(node, uuidMap, `p${k++}`));
        } else if (Array.isArray(node)) {
          node.forEach(walk);
        } else if (React.isValidElement(node)) {
          out.push(node);
        } else {
          out.push(<span key={`p${k++}`}>{String(node ?? "")}</span>);
        }
      };
      (Array.isArray(children) ? children : [children]).forEach(walk);
      return (
        <p style={{ margin: "0 0 0.5em", lineHeight: 1.6 }}>{out}</p>
      );
    },
    table: ({ children }: { children?: ReactNode }) => (
      <div style={{
        overflowX: "auto",
        margin: "0.4rem 0",
        borderRadius: "var(--radius-sm)",
        border: "1px solid var(--border-mid)",
        backgroundColor: "rgba(0,0,0,0.15)",
        WebkitOverflowScrolling: "touch",
      }}>
        <table
          style={{
            borderCollapse: "collapse",
            width: "100%",
            minWidth: "320px",
            fontSize: "var(--fs-micro)",
            color: "var(--text-body)",
            whiteSpace: "nowrap",
          }}
        >
          {children}
        </table>
      </div>
    ),
    th: ({ children }: { children?: ReactNode }) => (
      <th
        style={{
          border: `1px solid ${withAlpha(accent, 0.35)}`,
          padding: "4px 8px",
          textAlign: "left",
          color: accent,
          fontWeight: 600,
          whiteSpace: "nowrap",
          backgroundColor: withAlpha(accent, 0.1),
          fontSize: "var(--fs-micro)",
          letterSpacing: "0.03em",
        }}
      >
        {children}
      </th>
    ),
    td: ({ children }: { children?: ReactNode }) => (
      <td
        style={{
          border: `1px solid ${withAlpha(accent, 0.2)}`,
          padding: "4px 8px",
          whiteSpace: "nowrap",
          color: "var(--text-body)",
          fontSize: "var(--fs-micro)",
        }}
      >
        {children}
      </td>
    ),
    code: ({ children }: { children?: ReactNode }) => (
      <code
        style={{
          backgroundColor: withAlpha(accent, 0.12),
          color: accent,
          padding: "0.1em 0.3em",
          borderRadius: "var(--radius-sm)",
          fontFamily: "var(--font-mono, 'IBM Plex Mono', monospace)",
          fontSize: "0.95em",
          border: `1px solid ${withAlpha(accent, 0.2)}`,
        }}
      >
        {children}
      </code>
    ),
    ol: ({ children }: { children?: ReactNode }) => (
      <ol>{children}</ol>
    ),
    ul: ({ children }: { children?: ReactNode }) => (
      <ul>{children}</ul>
    ),
    li: ({ children }: { children?: ReactNode }) => (
      <li>{children}</li>
    ),
    strong: ({ children }: { children?: ReactNode }) => (
      <strong style={{ color: accent, fontWeight: 600 }}>{children}</strong>
    ),
    em: ({ children }: { children?: ReactNode }) => (
      <em style={{ color: "var(--text-secondary)", fontStyle: "italic" }}>{children}</em>
    ),
    hr: () => (
      <hr style={{ border: "none", borderTop: `1px solid ${withAlpha(accent, 0.2)}`, margin: "0.5rem 0" }} />
    ),
    a: ({ children, href }: { children?: ReactNode; href?: string }) => (
      <a href={href} style={{ color: accent, textDecoration: "underline", textUnderlineOffset: "2px" }}>{children}</a>
    ),
  };
}

// ─── AgentChatPanel Component ───────────────────────────────────────

export function AgentChatPanel(): React.ReactElement {
  const [messages, setMessages] = useState<AuditEvent[]>([]);
  const [allEvents, setAllEvents] = useState<AuditEvent[]>([]);
  const [filterAgent, setFilterAgent] = useState<string>("all");
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const msgCountRef = useRef(0);
  const noteAgentReply = useAtcStore((s) => s.noteAgentReply);

  // Fetch messages
  useEffect(() => {
    let alive = true;

    async function fetchMessages(): Promise<void> {
      try {
        const res = await fetch("/audit/events?limit=100");
        if (!res.ok) return;
        const data: AuditEvent[] = await res.json();
        if (alive) {
          const conversational = data.filter((e) => CONVERSATIONAL_TYPES.has(e.event_type));
          const next = conversational.slice(0, 50).reverse();
          if (next.length > 0 && next.length > msgCountRef.current) {
            noteAgentReply(next[next.length - 1].agent_name);
          }
          msgCountRef.current = next.length;
          setMessages(next);
          setAllEvents(data); // Keep all events for UUID resolution
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

  // Build UUID→handle mapping from all events
  const uuidMap = useMemo(() => buildUuidMap(allEvents), [allEvents]);

  // Get unique agent names for filter
  const agentNames = useMemo(() => {
    const names = new Set<string>();
    for (const msg of messages) {
      names.add(msg.agent_name);
    }
    return Array.from(names).sort();
  }, [messages]);

  // Filter messages by agent
  const filteredMessages = useMemo(() => {
    if (filterAgent === "all") return messages;
    return messages.filter((m) => m.agent_name === filterAgent);
  }, [messages, filterAgent]);

  // Auto-scroll to bottom only if user is already near bottom
  const isNearBottomRef = useRef(true);

  useLayoutEffect(() => {
    const el = listRef.current;
    if (!el) return;
    if (isNearBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [filteredMessages]);

  // Track scroll position for jump-to-latest button
  const handleScroll = useCallback(() => {
    const el = listRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    isNearBottomRef.current = nearBottom;
    setShowJumpToLatest(!nearBottom);
  }, []);

  const jumpToLatest = useCallback(() => {
    const el = listRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    setShowJumpToLatest(false);
  }, []);

  const componentsCache = useMemo(() => {
    const cache: Record<string, ReturnType<typeof markdownComponents>> = {};
    return (accent: string) => (cache[accent] ??= markdownComponents(accent, uuidMap));
  }, [uuidMap]);

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      height: "100%",
      backgroundColor: "var(--bg-deep)",
      overflow: "hidden",
      fontFamily: "var(--font-mono)",
      position: "relative",
    }}>
      {/* Header with filter */}
      <div className="atc-panel-header" style={{
        flexDirection: "column",
        alignItems: "stretch",
        gap: "var(--sp-1)",
        padding: "var(--sp-2) var(--sp-3)",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span className="atc-panel-title">
            AGENT COMMS ({filterAgent === "all" ? messages.length : filteredMessages.length})
          </span>
        </div>
        {/* Per-agent filter */}
        <div style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
          <button
            onClick={() => setFilterAgent("all")}
            className={`atc-filter-tab ${filterAgent === "all" ? "atc-filter-tab--active" : ""}`}
            aria-pressed={filterAgent === "all"}
            aria-label="Show all agent messages"
          >
            ALL
          </button>
          {agentNames.map((name) => {
            const color = agentColor(name);
            const isActive = filterAgent === name;
            return (
              <button
                key={name}
                onClick={() => setFilterAgent(isActive ? "all" : name)}
                className={`atc-filter-tab ${isActive ? "atc-filter-tab--active" : ""}`}
                style={isActive ? {
                  backgroundColor: withAlpha(color, 0.18),
                  borderColor: color,
                  color: color,
                  boxShadow: `0 0 6px ${withAlpha(color, 0.15)}`,
                } : undefined}
                aria-pressed={isActive}
                aria-label={`Filter by ${agentLabel(name)}`}
              >
                <AgentIcon handle={name} size={12} color={agentColor(name)} />
                {agentShort(name)}
              </button>
            );
          })}
        </div>
      </div>

      {/* Message list — scrollable area with padding for footer */}
      <div
        ref={listRef}
        onScroll={handleScroll}
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "var(--sp-2) var(--sp-3)",
          paddingBottom: showJumpToLatest ? "44px" : "var(--sp-2)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--sp-2)",
          transition: "padding-bottom var(--transition-fast)",
        }}
      >
        {filteredMessages.length === 0 ? (
          <div className="atc-empty-state">
            <div className="atc-empty-state-icon">📡</div>
            <div className="atc-empty-state-title">No agent messages yet</div>
            <div className="atc-empty-state-desc">
              Agent communications will appear here as they collaborate on the active scenario.
            </div>
          </div>
        ) : null}

        {filteredMessages.map((evt) => {
          const fromName = evt.agent_name;
          const fromColor = agentColor(fromName);
          const fromHandle = normalizeAgentHandle(fromName);
          const msgType = detectMessageType(evt.content);
          const typeColor = TYPE_COLORS[msgType];
          const typeLabel = TYPE_LABELS[msgType];
          const [fields, freeText] = extractStructuredFields(evt.content);

          return (
            <div
              key={evt.id}
              style={{
                borderLeft: `3px solid ${typeColor}`,
                borderRight: `1px solid ${withAlpha(fromColor, 0.12)}`,
                borderTop: `1px solid ${withAlpha(fromColor, 0.08)}`,
                borderBottom: `1px solid ${withAlpha(fromColor, 0.08)}`,
                backgroundColor: withAlpha(fromColor, 0.04),
                borderRadius: "0 var(--radius-lg) var(--radius-lg) 0",
                overflow: "hidden",
                minHeight: "48px",
                flexShrink: 0,
                boxShadow: "var(--shadow-sm)",
                transition: "box-shadow var(--transition-fast), background-color var(--transition-fast)",
              }}
            >
              {/* Sender header row — Tier 1: routing metadata */}
              <div style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "6px 10px",
                backgroundColor: withAlpha(fromColor, 0.08),
                borderBottom: `1px solid ${withAlpha(fromColor, 0.12)}`,
              }}>
                {/* Avatar icon */}
                <span style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: "22px",
                  height: "22px",
                  borderRadius: "var(--radius-md)",
                  backgroundColor: withAlpha(fromColor, 0.2),
                  border: `1px solid ${withAlpha(fromColor, 0.3)}`,
                  fontSize: "0.7rem",
                  flexShrink: 0,
                  transition: "background-color var(--transition-fast)",
                }}>
                  <AgentIcon handle={fromHandle} size={14} color={fromColor} />
                </span>
                {/* Sender name */}
                <span style={{
                  color: fromColor,
                  fontWeight: 700,
                  fontSize: "var(--fs-micro)",
                  letterSpacing: "0.02em",
                }}>
                  {agentLabel(fromHandle)}
                </span>
                {/* Message type badge — severity-weighted */}
                <span
                  className={`atc-severity-badge ${
                    msgType === "warning" ? "atc-severity-badge--critical" :
                    msgType === "escalation" ? "atc-severity-badge--warning" :
                    msgType === "advisory" ? "atc-severity-badge--caution" :
                    "atc-severity-badge--info"
                  }`}
                  style={{ marginLeft: "auto" }}
                >
                  {typeLabel}
                </span>
                {/* Timestamp */}
                <span style={{
                  fontSize: "var(--fs-micro)",
                  color: "var(--text-dim)",
                  whiteSpace: "nowrap",
                }}>
                  {formatTime(evt.timestamp)}
                </span>
              </div>

              {/* Structured data chips — Tier 2: parsed fields */}
              {fields.length > 0 && (
                <div style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: '4px',
                  padding: '5px 10px',
                  borderBottom: `1px solid ${withAlpha(fromColor, 0.08)}`,
                  backgroundColor: withAlpha(fromColor, 0.03),
                }}>
                  {fields.map((f, i) => (
                    <div key={i} style={{
                      display: 'inline-flex',
                      fontSize: 'var(--fs-micro)',
                      borderRadius: 'var(--radius-sm)',
                      border: `1px solid ${withAlpha(fromColor, 0.3)}`,
                      overflow: 'hidden',
                    }}>
                      <span style={{
                        padding: '2px 6px',
                        backgroundColor: withAlpha(fromColor, 0.18),
                        color: fromColor,
                        fontWeight: 600,
                        whiteSpace: 'nowrap',
                        letterSpacing: '0.02em',
                      }}>{f.key}</span>
                      <span style={{
                        padding: '2px 6px',
                        color: 'var(--text-primary)',
                        whiteSpace: 'nowrap',
                        backgroundColor: withAlpha(fromColor, 0.06),
                      }}>{f.value}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Message body — Tier 3: free-text content */}
              <CollapsibleMessageBody accent={fromColor}>
                <div className="atc-msg-body" style={{
                  padding: '8px 10px 10px',
                  color: 'var(--text-body)',
                  fontSize: 'var(--fs-body)',
                  lineHeight: 1.65,
                  whiteSpace: 'normal',
                  wordBreak: 'break-word',
                  overflowWrap: 'break-word',
                }}>
                  {freeText ? (
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={componentsCache(fromColor)}
                    >
                      {normalizeMarkdownLists(freeText)}
                    </ReactMarkdown>
                  ) : (
                    <span style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}>
                      {evt.content.slice(0, 200)}
                    </span>
                  )}
                </div>
              </CollapsibleMessageBody>
            </div>
          );
        })}
      </div>

      {/* Jump to latest — sticky footer bar, never overlaps content */}
      <div
        style={{
          position: "sticky",
          bottom: 0,
          display: "flex",
          justifyContent: "center",
          padding: "6px 0",
          background: "linear-gradient(0deg, var(--bg-deep) 60%, transparent 100%)",
          pointerEvents: showJumpToLatest ? "auto" : "none",
          opacity: showJumpToLatest ? 1 : 0,
          transition: "opacity var(--transition-fast)",
          zIndex: 10,
          flexShrink: 0,
        }}
      >
        <button
          onClick={jumpToLatest}
          aria-label="Scroll to latest messages"
          style={{
            padding: "5px 14px",
            backgroundColor: "var(--bg-raised)",
            border: "1px solid var(--color-nominal)",
            borderRadius: "var(--radius-lg)",
            color: "var(--color-nominal)",
            fontSize: "var(--fs-micro)",
            fontFamily: "var(--font-mono)",
            cursor: "pointer",
            boxShadow: "0 2px 10px rgba(0,0,0,0.4), 0 0 8px rgba(51, 255, 51, 0.12)",
            letterSpacing: "0.04em",
            transition: "box-shadow var(--transition-fast), background-color var(--transition-fast)",
          }}
        >
          ↓ JUMP TO LATEST
        </button>
      </div>
    </div>
  );
}
