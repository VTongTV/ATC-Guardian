/** ATC Guardian — agent detail page.
 *
 * Full-page view showing a selected agent's role, capabilities,
 * communication patterns, and live statistics.
 * Navigated to via the flash bar or agent team cards.
 */

import React, { useEffect, useState } from "react";
import { useAtcStore } from "../stores/atcStore";
import { AgentIcon, AGENT_COLORS } from "./AgentIcons";

// ─── Static agent data ──────────────────────────────────────────

const AGENT_DETAILS: Record<string, {
  role: string;
  capabilities: string[];
  communications: string[];
}> = {
  coordinator: {
    role: "Orchestrates all agent activity. Receives agent outputs, resolves conflicts between advisories, and surfaces consolidated recommendations to the human controller for decision.",
    capabilities: [
      "Multi-agent output fusion and deconfliction",
      "Advisory priority ranking and human presentation",
      "Scenario phase tracking and agent dispatch",
      "Controller authority gatekeeping",
    ],
    communications: [
      "Receives advisories from Conflict Detector and Weather Analyst",
      "Receives approved clearances from Safety Reviewer",
      "Dispatches Emergency Response on NORDO/7500/7600",
      "Surfaces all decisions to controller for approval",
    ],
  },
  "conflict-detector": {
    role: "Continuously monitors aircraft pairs for loss of separation. Detects Closest Point of Approach (CPA) violations and generates conflict advisories with severity classification.",
    capabilities: [
      "Real-time CPA computation for all aircraft pairs",
      "Severity classification (CRITICAL / CAUTION)",
      "Lateral and vertical separation monitoring",
      "Parallel approach breach detection",
    ],
    communications: [
      "Generates conflict advisories to Coordinator",
      "Notifies Safety Reviewer for approval",
      "Receives aircraft position updates from System Ingest",
    ],
  },
  "weather-analyst": {
    role: "Monitors weather hazards within the terminal area. Detects wind shear, convective cells, and IFR conditions. Issues deviation and missed approach advisories.",
    capabilities: [
      "Wind shear detection across approach corridors",
      "Convective cell proximity analysis",
      "IFR condition assessment (CEIL/VIS)",
      "Missed approach and deviation advisory generation",
    ],
    communications: [
      "Issues weather advisories to Coordinator",
      "Shares weather data with Ground Ops",
      "Notifies Safety Reviewer for clearance approval",
    ],
  },
  "ground-ops": {
    role: "Manages ground movement, runway assignments, and surface traffic. Coordinates with Emergency Response for runway priority during incidents.",
    capabilities: [
      "Nearest suitable runway identification",
      "Surface conflict monitoring",
      "Priority handling coordination",
      "Fuel emergency runway allocation",
    ],
    communications: [
      "Receives runway requests from Emergency Response",
      "Coordinates with Safety Reviewer for priority approach",
      "Provides runway status to Coordinator",
    ],
  },
  "emergency-response": {
    role: "First responder for all emergency declarations (NORDO, 7500, 7600, fuel minimum, unlawful interference). Coordinates immediate response and recruits other agents.",
    capabilities: [
      "Emergency classification and phase determination",
      "NORDO procedure recommendation",
      "Unlawful interference security coordination",
      "Minimum fuel priority handling",
    ],
    communications: [
      "Dispatched by Coordinator on emergency detection",
      "Recruits @ground-ops for runway coordination",
      "Requests Safety Reviewer approval for procedures",
      "Reports resolution status back to Coordinator",
    ],
  },
  "safety-reviewer": {
    role: "Final safety gate before any recommendation reaches the controller. Reviews all agent outputs for regulatory compliance, separation minima, and safety of flight.",
    capabilities: [
      "Regulatory compliance verification",
      "Separation minimum validation",
      "Advisory safety approval or rejection",
      "Risk-benefit analysis for controller decisions",
    ],
    communications: [
      "Reviews advisories from Conflict Detector",
      "Reviews deviation requests from Weather Analyst",
      "Approves emergency procedures from Emergency Response",
      "Issues approved clearances to Coordinator",
    ],
  },
};

// ─── Collaboration graph node shape ────────────────────────────

interface AgentNode {
  name: string;
  label: string;
  framework: string;
  framework_note: string;
  role: string;
  colour: string;
}

interface CollaborationGraph {
  nodes: AgentNode[];
}

// ─── Component ─────────────────────────────────────────────────

interface AgentDetailPageProps {
  onBack: () => void;
}

export function AgentDetailPage({ onBack }: AgentDetailPageProps): React.ReactElement {
  const selectedHandle = useAtcStore((s) => s.selectedAgentHandle);
  const handle = selectedHandle ?? "coordinator";
  const color = AGENT_COLORS[handle] ?? "#888";
  const details = AGENT_DETAILS[handle];

  // Live stats from collaboration graph
  const [node, setNode] = useState<AgentNode | null>(null);
  const [msgCount, setMsgCount] = useState(0);
  const auditEvents = useAtcStore((s) => s.aircraft); // trigger re-render on update

  useEffect(() => {
    fetch("/data/collaboration/graph")
      .then((r) => r.json())
      .then((g: CollaborationGraph) => {
        const n = g.nodes?.find((n) => n.name === handle);
        if (n) setNode(n);
      })
      .catch(() => {});
  }, [handle]);

  // Count recent messages for this agent from audit events
  useEffect(() => {
    fetch("/data/audit/events?limit=100")
      .then((r) => r.json())
      .then((events: { agent_name?: string }[]) => {
        setMsgCount(events.filter((e) => e.agent_name === handle).length);
      })
      .catch(() => {});
  }, [handle, auditEvents]);

  const shortLabel = handle
    .split("-")
    .map((w) => w[0].toUpperCase())
    .join("");

  return (
    <div className="agent-detail-page">
      {/* Back button */}
      <button
        onClick={onBack}
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--sp-1)",
          padding: "var(--sp-1) var(--sp-3)",
          backgroundColor: "var(--bg-surface)",
          border: "1px solid var(--border-mid)",
          borderRadius: "var(--radius-md)",
          color: "var(--color-nominal)",
          fontSize: "var(--fs-meta)",
          fontFamily: "var(--font-mono)",
          cursor: "pointer",
          letterSpacing: "0.04em",
          boxShadow: "var(--shadow-sm)",
          alignSelf: "flex-start",
        }}
      >
        <span style={{ fontSize: "0.7rem" }}>←</span>
        BACK
      </button>

      {/* Hero */}
      <div className="agent-detail-hero">
        <div className="agent-detail-icon-wrap">
          <AgentIcon handle={handle} size={36} color={color} />
        </div>
        <div>
          <h2 style={{ fontSize: "var(--fs-title)", fontWeight: 700, color, margin: 0, letterSpacing: "0.08em" }}>
            {shortLabel}
          </h2>
          <div style={{ fontSize: "var(--fs-body)", color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}>
            {node?.label ?? handle}
          </div>
          {node?.framework && (
            <div style={{ fontSize: "var(--fs-micro)", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
              {node.framework} {node.framework_note ? `— ${node.framework_note}` : ""}
            </div>
          )}
        </div>
      </div>

      {/* Role */}
      {details && (
        <div className="agent-detail-section">
          <div className="agent-detail-section-title">Role</div>
          <div className="atc-body">{details.role}</div>
        </div>
      )}

      {/* Capabilities */}
      {details && (
        <div className="agent-detail-section">
          <div className="agent-detail-section-title">Capabilities</div>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {details.capabilities.map((cap, i) => (
              <li
                key={i}
                style={{
                  position: "relative",
                  paddingLeft: "1.2rem",
                  marginBottom: "0.3rem",
                  fontSize: "var(--fs-meta)",
                  color: "var(--text-body)",
                }}
              >
                <span style={{ position: "absolute", left: 0, color, fontWeight: 700 }}>▸</span>
                {cap}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Communications */}
      {details && (
        <div className="agent-detail-section">
          <div className="agent-detail-section-title">Communications</div>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {details.communications.map((comm, i) => (
              <li
                key={i}
                style={{
                  position: "relative",
                  paddingLeft: "1.2rem",
                  marginBottom: "0.3rem",
                  fontSize: "var(--fs-meta)",
                  color: "var(--text-body)",
                }}
              >
                <span style={{ position: "absolute", left: 0, color: "var(--color-info)", fontWeight: 700 }}>▸</span>
                {comm}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Live Stats */}
      <div className="agent-detail-section">
        <div className="agent-detail-section-title">Live Stats</div>
        <div className="agent-detail-stat">
          <span style={{ color: "var(--text-dim)" }}>Recent messages</span>
          <span style={{ color, fontWeight: 600 }}>{msgCount}</span>
        </div>
        <div className="agent-detail-stat">
          <span style={{ color: "var(--text-dim)" }}>Framework</span>
          <span style={{ color: "var(--text-secondary)" }}>{node?.framework ?? "—"}</span>
        </div>
        <div className="agent-detail-stat">
          <span style={{ color: "var(--text-dim)" }}>Agent color</span>
          <span style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
            <span style={{ width: 10, height: 10, borderRadius: "50%", backgroundColor: color, display: "inline-block" }} />
            <span style={{ color: "var(--text-secondary)", fontFamily: "var(--font-mono)", fontSize: "var(--fs-micro)" }}>{color}</span>
          </span>
        </div>
      </div>
    </div>
  );
}
