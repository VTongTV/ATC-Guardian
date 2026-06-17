/** AgentTeamPage — dedicated full-page view of the ATC Guardian agent roster.
 *
 * Extracted from the dashboard footer to give agents room to breathe.
 * Fetches the collaboration graph and renders extended agent cards with
 * role descriptions, framework details, and live activity indicators.
 */

import { useEffect, useRef, useState } from "react";
import { useAtcStore } from "../stores/atcStore";

interface AgentNode {
  name: string;
  label: string;
  framework: string;
  framework_note: string;
  role: string;
  colour: string;
}

interface CollaborationEdge {
  source: string;
  target: string;
  weight: number;
}

interface CollaborationGraph {
  nodes: AgentNode[];
  edges: CollaborationEdge[];
  frameworks: Record<string, number>;
}

const FRAMEWORK_COLORS: Record<string, string> = {
  "LangGraph": "#ff6b35",
  "Pydantic AI": "#9b59b6",
  "CrewAI": "#1abc9c",
};

const AGENT_ICONS: Record<string, string> = {
  coordinator: "🎯",
  "conflict-detector": "⚠️",
  "weather-analyst": "🌩️",
  "ground-ops": "✈️",
  "emergency-response": "🚨",
  "safety-reviewer": "🛡️",
  "system-ingest": "📡",
};

function withAlpha(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

let _flashStyleInjected = false;
function injectFlashKeyframes(): void {
  if (_flashStyleInjected || typeof document === "undefined") return;
  _flashStyleInjected = true;
  const sheet = document.createElement("style");
  sheet.textContent = `
    @keyframes agentFlash {
      0%   { box-shadow: 0 0 0px transparent; }
      30%  { box-shadow: 0 0 16px 4px var(--flash-colour); }
      100% { box-shadow: 0 0 0px transparent; }
    }
    .agent-flash { animation: agentFlash 1.2s ease-out; }
  `;
  document.head.appendChild(sheet);
}

export function AgentTeamPage(): React.ReactElement {
  const [graph, setGraph] = useState<CollaborationGraph | null>(null);
  const [flash, setFlash] = useState<{ agent: string; tick: number } | null>(null);
  const lastReplyAgent = useAtcStore((s) => s.lastReplyAgent);
  const lastReplyTick = useAtcStore((s) => s.lastReplyTick);
  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => { injectFlashKeyframes(); }, []);

  useEffect(() => {
    if (!lastReplyAgent || lastReplyTick === 0) return;
    setFlash({ agent: lastReplyAgent, tick: lastReplyTick });
    if (flashTimer.current) clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setFlash(null), 1500);
    return () => { if (flashTimer.current) clearTimeout(flashTimer.current); };
  }, [lastReplyAgent, lastReplyTick]);

  useEffect(() => {
    let alive = true;
    async function fetchGraph(): Promise<void> {
      try {
        const res = await fetch("/collaboration/graph");
        if (!res.ok) return;
        const data: CollaborationGraph = await res.json();
        if (alive) setGraph(data);
      } catch { /* backend offline */ }
    }
    fetchGraph();
    const timer = window.setInterval(fetchGraph, 5000);
    return () => { alive = false; window.clearInterval(timer); };
  }, []);

  const nodes = graph?.nodes ?? [];
  const edges = graph?.edges ?? [];
  const frameworks = graph?.frameworks ?? {};

  const incomingWeight: Record<string, number> = {};
  for (const e of edges) {
    incomingWeight[e.target] = (incomingWeight[e.target] ?? 0) + e.weight;
    incomingWeight[e.source] = (incomingWeight[e.source] ?? 0) + e.weight;
  }

  return (
    <div style={{
      flex: 1,
      overflowY: "auto",
      padding: "var(--sp-6)",
    }}>
      {/* Page title */}
      <div style={{
        marginBottom: "var(--sp-6)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexWrap: "wrap",
        gap: "var(--sp-3)",
      }}>
        <div>
          <h2 style={{
            fontSize: "var(--fs-header)",
            fontWeight: 600,
            color: "var(--color-nominal)",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            animation: "glow-phosphor 4s ease-in-out infinite",
            margin: 0,
          }}>
            AGENT TEAM
          </h2>
          <p style={{
            fontSize: "var(--fs-meta)",
            color: "var(--text-dim)",
            marginTop: "var(--sp-1)",
          }}>
            Six specialised AI agents collaborating in real time across three frameworks
          </p>
        </div>
        {/* Framework diversity badges */}
        <div style={{ display: "flex", gap: "var(--sp-2)", flexWrap: "wrap" }}>
          {Object.entries(frameworks).map(([fw, n]) => (
            <span key={fw} style={{
              padding: "var(--sp-1) var(--sp-3)",
              borderRadius: "6px",
              fontSize: "var(--fs-meta)",
              backgroundColor: withAlpha(FRAMEWORK_COLORS[fw] ?? "#888", 0.12),
              color: FRAMEWORK_COLORS[fw] ?? "#888",
              border: `1px solid ${withAlpha(FRAMEWORK_COLORS[fw] ?? "#888", 0.3)}`,
              fontWeight: 500,
            }}>
              {fw} ×{n}
            </span>
          ))}
        </div>
      </div>

      {/* Agent cards grid */}
      <div className="atc-agent-team-grid">
        {nodes.map((node) => {
          const fwColour = FRAMEWORK_COLORS[node.framework] ?? "#888";
          const activity = incomingWeight[node.name] ?? 0;
          const isActive = activity > 0;
          const isFlashing = flash?.agent === node.name;
          const icon = AGENT_ICONS[node.name] ?? "🤖";

          return (
            <div
              key={`${node.name}-${isFlashing ? flash!.tick : ""}`}
              title={node.framework_note}
              className={`atc-agent-card-extended ${isFlashing ? "agent-flash" : ""}`}
              style={{
                border: `1px solid ${isActive ? node.colour : "var(--border-mid)"}`,
                borderLeft: `4px solid ${node.colour}`,
                backgroundColor: isActive ? "var(--bg-surface)" : "var(--bg-mid)",
                ["--card-glow-rgb" as string]: node.colour.replace("#", "").match(/.{2}/g)?.map(h => parseInt(h, 16)).join(",") ?? "51,255,51",
                ["--flash-colour" as string]: node.colour,
              } as React.CSSProperties}
            >
              {/* Header row */}
              <div style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--sp-2)",
                marginBottom: "var(--sp-3)",
              }}>
                {/* Icon */}
                <span style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: "36px",
                  height: "36px",
                  borderRadius: "8px",
                  backgroundColor: withAlpha(node.colour, 0.15),
                  border: `1px solid ${withAlpha(node.colour, 0.3)}`,
                  fontSize: "1.1rem",
                  flexShrink: 0,
                }}>
                  {icon}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "var(--sp-2)",
                  }}>
                    <span style={{
                      color: node.colour,
                      fontWeight: 700,
                      fontSize: "var(--fs-body)",
                    }}>
                      {node.label}
                    </span>
                    {/* Activity indicator */}
                    <span style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "3px",
                      fontSize: "var(--fs-micro)",
                      color: isActive ? "#33ff33" : "var(--text-muted)",
                    }}>
                      <span style={{
                        width: "6px",
                        height: "6px",
                        borderRadius: "50%",
                        backgroundColor: isActive ? "#33ff33" : "#333",
                        boxShadow: isActive ? "0 0 4px #33ff33" : "none",
                        animation: isActive ? "pulse-live 2s ease-in-out infinite" : "none",
                        display: "inline-block",
                      }} />
                      {isActive ? `${activity} mentions` : "Idle"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Framework badge */}
              <div style={{ marginBottom: "var(--sp-2)" }}>
                <span style={{
                  display: "inline-block",
                  padding: "2px var(--sp-2)",
                  borderRadius: "8px",
                  fontSize: "var(--fs-micro)",
                  fontWeight: 600,
                  backgroundColor: withAlpha(fwColour, 0.12),
                  color: fwColour,
                  border: `1px solid ${withAlpha(fwColour, 0.3)}`,
                  letterSpacing: "0.02em",
                }}>
                  {node.framework}
                </span>
              </div>

              {/* Role */}
              {node.role && (
                <div style={{
                  color: "var(--text-secondary)",
                  fontSize: "var(--fs-meta)",
                  lineHeight: 1.45,
                  marginBottom: "var(--sp-2)",
                }}>
                  {node.role}
                </div>
              )}

              {/* Framework note */}
              {node.framework_note && (
                <div style={{
                  color: "var(--text-dim)",
                  fontSize: "var(--fs-micro)",
                  lineHeight: 1.4,
                  fontStyle: "italic",
                  borderTop: "1px solid var(--border-dim)",
                  paddingTop: "var(--sp-2)",
                }}>
                  {node.framework_note}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
