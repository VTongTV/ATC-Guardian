/** CollaborationFlow — agent node grid with live @mention edges and flash-on-reply. */

import { useEffect, useRef, useState } from "react";
import { useAtcStore } from "../stores/atcStore";

/** Agent node metadata from GET /collaboration/graph. */
interface AgentNode {
  name: string;
  label: string;
  framework: string;
  framework_note: string;
  role: string;
  colour: string;
}

/** @mention edge from the audit log. */
interface CollaborationEdge {
  source: string;
  target: string;
  weight: number;
}

/** Full graph response. */
interface CollaborationGraph {
  nodes: AgentNode[];
  edges: CollaborationEdge[];
  frameworks: Record<string, number>;
}

/** HTTP base URL. In dev, Vite proxies to the backend. */
const HTTP_BASE_URL: string = import.meta.env.VITE_API_URL ?? "";

/** Poll interval for the live graph (ms). */
const POLL_INTERVAL_MS = 5000;

/** Framework badge colour mapping. */
const FRAMEWORK_COLORS: Record<string, string> = {
  "LangGraph": "#ff6b35",
  "Pydantic AI": "#9b59b6",
  "CrewAI": "#1abc9c",
};

/** Role icon per agent handle. */
const AGENT_ICONS: Record<string, string> = {
  coordinator: '🎯',
  'conflict-detector': '⚠️',
  'weather-analyst': '🌩️',
  'ground-ops': '✈️',
  'emergency-response': '🚨',
  'safety-reviewer': '🛡️',
  'system-ingest': '📡',
};

/** Convert a hex colour to rgba with the given alpha. */
function withAlpha(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** Inject a one-shot CSS keyframe for the flash animation. */
let _styleInjected = false;
function injectFlashKeyframes(): void {
  if (_styleInjected || typeof document === "undefined") return;
  _styleInjected = true;
  const sheet = document.createElement("style");
  sheet.textContent = `
    @keyframes agentFlash {
      0%   { box-shadow: 0 0 0px transparent; }
      30%  { box-shadow: 0 0 12px 2px var(--flash-colour); }
      100% { box-shadow: 0 0 0px transparent; }
    }
    .agent-flash { animation: agentFlash 1.2s ease-out; }
    @keyframes pulse-live {
      0%, 100% { opacity: 1; }
      50%      { opacity: 0.35; }
    }
  `;
  document.head.appendChild(sheet);
}

/** CollaborationFlow — agent node grid with live @mention edges and flash-on-reply. */
export function CollaborationFlow(): React.ReactElement {
  const [graph, setGraph] = useState<CollaborationGraph | null>(null);
  const [flash, setFlash] = useState<{ agent: string; tick: number } | null>(null);
  const lastReplyAgent = useAtcStore((s) => s.lastReplyAgent);
  const lastReplyTick = useAtcStore((s) => s.lastReplyTick);
  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Inject the keyframe CSS once.
  useEffect(() => { injectFlashKeyframes(); }, []);

  // When the store signals a new reply, arm a flash for that agent.
  useEffect(() => {
    if (!lastReplyAgent || lastReplyTick === 0) return;
    setFlash({ agent: lastReplyAgent, tick: lastReplyTick });
    if (flashTimer.current) clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setFlash(null), 1500);
    return () => {
      if (flashTimer.current) clearTimeout(flashTimer.current);
    };
  }, [lastReplyAgent, lastReplyTick]);

  useEffect(() => {
    let alive = true;

    async function fetchGraph(): Promise<void> {
      try {
        const res = await fetch(`${HTTP_BASE_URL}/collaboration/graph`);
        if (!res.ok) return;
        const data: CollaborationGraph = await res.json();
        if (alive) setGraph(data);
      } catch {
        /* backend offline */
      }
    }

    fetchGraph();
    const timer = window.setInterval(fetchGraph, POLL_INTERVAL_MS);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  const nodes = graph?.nodes ?? [];
  const edges = graph?.edges ?? [];
  const frameworks = graph?.frameworks ?? {};

  // Map of target -> total incoming weight, to highlight active nodes.
  const incomingWeight: Record<string, number> = {};
  for (const e of edges) {
    incomingWeight[e.target] = (incomingWeight[e.target] ?? 0) + e.weight;
    incomingWeight[e.source] = (incomingWeight[e.source] ?? 0) + e.weight;
  }

  const panelStyle: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    backgroundColor: "var(--bg-deep)",
    fontFamily: "var(--font-mono)",
    overflow: "hidden",
  };

  return (
    <div style={panelStyle}>
      <div className="atc-panel-header" style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '0.2rem' }}>
        <span className="atc-panel-title">AGENT TEAM</span>
        <span style={{ display: 'flex', flexWrap: 'wrap', gap: '0.15rem', marginLeft: 'auto' }}>
          {Object.entries(frameworks).map(([fw, n]) => (
            <span key={fw} style={{
              padding: '0.05rem 0.3rem',
              borderRadius: '6px',
              fontSize: '0.5rem',
              backgroundColor: withAlpha(FRAMEWORK_COLORS[fw] ?? '#888', 0.15),
              color: FRAMEWORK_COLORS[fw] ?? '#888',
              border: `1px solid ${withAlpha(FRAMEWORK_COLORS[fw] ?? '#888', 0.3)}`,
            }}>
              {fw} ×{n}
            </span>
          ))}
        </span>
      </div>
      <div
        style={{
          overflowY: "auto",
          padding: "0.3rem 0.5rem",
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "0.25rem",
        }}
      >
        {nodes.map((node) => {
          const fwColour = FRAMEWORK_COLORS[node.framework] ?? "#888";
          const activity = incomingWeight[node.name] ?? 0;
          const isActive = activity > 0;
          const isFlashing = flash?.agent === node.name;
          return (
            <div
              key={`${node.name}-${isFlashing ? flash!.tick : ""}`}
              title={node.framework_note}
              className={isFlashing ? "agent-flash" : undefined}
              style={{
                border: `1px solid ${isActive ? node.colour : 'var(--border-mid)'}`,
                borderLeft: `3px solid ${node.colour}`,
                backgroundColor: isActive ? 'var(--bg-surface)' : 'var(--bg-mid)',
                borderRadius: '4px',
                padding: '0.4rem 0.5rem 0.35rem',
                fontSize: '0.6rem',
                position: 'relative',
                overflow: 'visible',
                ["--flash-colour" as string]: node.colour,
              } as React.CSSProperties}
            >
              {/* Status dot — top-right corner */}
              <span style={{
                position: 'absolute',
                top: '0.35rem',
                right: '0.35rem',
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                backgroundColor: isActive ? '#33ff33' : '#333',
                display: 'inline-block',
                boxShadow: isActive ? '0 0 4px #33ff33' : 'none',
                animation: isActive ? 'pulse-live 2s ease-in-out infinite' : 'none',
              }} />
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                <span style={{ fontSize: '0.7rem' }}>
                  {AGENT_ICONS[node.name] ?? '🤖'}
                </span>
                <span style={{ color: node.colour, fontWeight: 'bold' }}>
                  {node.label}
                </span>
                {activity > 0 && (
                  <span style={{
                    color: '#33ff33',
                    fontSize: '0.55rem',
                    marginLeft: 'auto',
                    padding: '0 4px',
                    borderRadius: '8px',
                    backgroundColor: 'rgba(51,255,51,0.1)',
                    border: '1px solid rgba(51,255,51,0.2)',
                    whiteSpace: 'nowrap',
                  }}>
                    {activity}
                  </span>
                )}
              </div>
              <div style={{ marginTop: '0.15rem' }}>
                <span style={{
                  display: 'inline-block',
                  padding: '0.08rem 0.35rem',
                  borderRadius: '8px',
                  fontSize: '0.5rem',
                  fontWeight: 500,
                  backgroundColor: withAlpha(fwColour, 0.12),
                  color: fwColour,
                  border: `1px solid ${withAlpha(fwColour, 0.3)}`,
                  letterSpacing: '0.02em',
                  marginTop: '0.15rem',
                }}>
                  {node.framework}
                </span>
              </div>
              {node.role && (
                <div style={{ color: 'var(--text-dim)', fontSize: '0.5rem', marginTop: '0.15rem' }}>
                  {node.role}
                </div>
              )}
            </div>
          );
        })}
      </div>

    </div>
  );
}
