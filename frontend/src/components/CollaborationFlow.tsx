/** ATC Guardian — collaboration flow visualiser.

Renders the six-agent team as a node grid with framework badges and
highlights live @mention edges derived from the audit log. Makes the
cross-framework collaboration (LangGraph / Pydantic AI / CrewAI) — a
genuine competitive edge — visible to judges.
*/

import { useEffect, useState } from "react";

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

/** CollaborationFlow — agent node grid with live @mention edges. */
export function CollaborationFlow(): React.ReactElement {
  const [graph, setGraph] = useState<CollaborationGraph | null>(null);

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
    display: "flex",
    justifyContent: "space-between",
  };

  return (
    <div style={panelStyle}>
      <div style={headerStyle}>
        <span>AGENT TEAM</span>
        <span style={{ color: "#888", fontSize: "0.6rem" }}>
          {Object.entries(frameworks)
            .map(([fw, n]) => `${fw}×${n}`)
            .join(" · ")}
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
          return (
            <div
              key={node.name}
              title={node.framework_note}
              style={{
                border: `1px solid ${isActive ? node.colour : "#222"}`,
                borderLeft: `3px solid ${node.colour}`,
                backgroundColor: isActive ? "#0f1a0f" : "#0d0d0d",
                padding: "0.25rem",
                fontSize: "0.6rem",
                position: "relative",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ color: node.colour, fontWeight: "bold" }}>
                  {node.label}
                </span>
                {activity > 0 && (
                  <span style={{ color: "#33ff33", fontSize: "0.55rem" }}>
                    ●{activity}
                  </span>
                )}
              </div>
              <div
                style={{
                  color: fwColour,
                  fontSize: "0.55rem",
                  marginTop: "0.1rem",
                }}
              >
                {node.framework}
              </div>
            </div>
          );
        })}
      </div>

    </div>
  );
}
