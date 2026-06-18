/** ATC Guardian — agent detail page (bento grid redesign).
 *
 * Full-page view with animated SVG illustration, model info,
 * capabilities, communications, and live statistics in a bento layout.
 */

import React, { useEffect, useState } from "react";
import { useAtcStore } from "../stores/atcStore";
import { AgentIcon, AGENT_COLORS } from "./AgentIcons";

// ─── SVG imports ──────────────────────────────────────────────────

import coordinatorSvg from "../assets/agents/coordinator.svg";
import conflictDetectorSvg from "../assets/agents/conflict-detector.svg";
import weatherAnalystSvg from "../assets/agents/weather-analyst.svg";
import groundOpsSvg from "../assets/agents/ground-ops.svg";
import emergencyResponseSvg from "../assets/agents/emergency-response.svg";
import safetyReviewerSvg from "../assets/agents/safety-reviewer.svg";

const AGENT_SVGS: Record<string, string> = {
  coordinator: coordinatorSvg,
  "conflict-detector": conflictDetectorSvg,
  "weather-analyst": weatherAnalystSvg,
  "ground-ops": groundOpsSvg,
  "emergency-response": emergencyResponseSvg,
  "safety-reviewer": safetyReviewerSvg,
};

// ─── Agent detail data ─────────────────────────────────────────────

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

// ─── Model info ────────────────────────────────────────────────────

const AGENT_MODELS: Record<string, {
  primary: string;
  provider: string;
  reasoning: string;
  maxTokens: string;
}> = {
  coordinator: {
    primary: "deepseek/deepseek-v4-pro",
    provider: "AI/ML API",
    reasoning: "low",
    maxTokens: "1024",
  },
  "conflict-detector": {
    primary: "deepseek/deepseek-v4-pro",
    provider: "AI/ML API",
    reasoning: "low",
    maxTokens: "1024",
  },
  "weather-analyst": {
    primary: "deepseek/deepseek-v4-pro",
    provider: "AI/ML API",
    reasoning: "low",
    maxTokens: "1024",
  },
  "ground-ops": {
    primary: "deepseek/deepseek-v4-pro",
    provider: "AI/ML API",
    reasoning: "low",
    maxTokens: "512",
  },
  "emergency-response": {
    primary: "deepseek/deepseek-v4-pro",
    provider: "AI/ML API",
    reasoning: "low",
    maxTokens: "1024",
  },
  "safety-reviewer": {
    primary: "deepseek/deepseek-v4-pro",
    provider: "AI/ML API",
    reasoning: "low",
    maxTokens: "1024",
  },
};

// ─── Collaboration graph node shape ────────────────────────────────

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

// ─── Component ─────────────────────────────────────────────────────

interface AgentDetailPageProps {
  onBack: () => void;
}

export function AgentDetailPage({ onBack }: AgentDetailPageProps): React.ReactElement {
  const selectedHandle = useAtcStore((s) => s.selectedAgentHandle);
  const handle = selectedHandle ?? "coordinator";
  const color = AGENT_COLORS[handle] ?? "#888";
  const details = AGENT_DETAILS[handle];
  const model = AGENT_MODELS[handle];
  const svgSrc = AGENT_SVGS[handle];

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
      <button className="agent-detail-back" onClick={onBack}>
        <span style={{ fontSize: "0.7rem" }}>←</span>
        BACK
      </button>

      {/* Bento grid */}
      <div className="agent-bento">
        {/* ── Cell 1: Hero + SVG illustration (spans 2 cols) ── */}
        <div className="agent-bento-hero" style={{ "--agent-color": color } as React.CSSProperties}>
          <div className="agent-bento-hero-info">
            <div className="agent-bento-hero-icon">
              <AgentIcon handle={handle} size={28} color={color} />
            </div>
            <div>
              <h2 className="agent-bento-hero-title" style={{ color }}>
                {shortLabel}
              </h2>
              <div className="agent-bento-hero-label">
                {node?.label ?? handle}
              </div>
              {node?.framework && (
                <div className="agent-bento-hero-framework">
                  {node.framework}{node.framework_note ? ` — ${node.framework_note}` : ""}
                </div>
              )}
            </div>
          </div>
          <div className="agent-bento-hero-svg">
            {svgSrc && <img src={svgSrc} alt={`${handle} illustration`} />}
          </div>
        </div>

        {/* ── Cell 2: Model Info ── */}
        {model && (
          <div className="agent-bento-model" style={{ "--agent-color": color } as React.CSSProperties}>
            <div className="agent-bento-cell-title">Model</div>
            <div className="agent-bento-model-id">{model.primary}</div>
            <div className="agent-bento-model-props">
              <div className="agent-bento-model-prop">
                <span className="agent-bento-model-prop-key">Provider</span>
                <span className="agent-bento-model-prop-val">{model.provider}</span>
              </div>
              <div className="agent-bento-model-prop">
                <span className="agent-bento-model-prop-key">Reasoning</span>
                <span className="agent-bento-model-prop-val">{model.reasoning}</span>
              </div>
              <div className="agent-bento-model-prop">
                <span className="agent-bento-model-prop-key">Max Tokens</span>
                <span className="agent-bento-model-prop-val">{model.maxTokens}</span>
              </div>
            </div>
          </div>
        )}

        {/* ── Cell 3: Role ── */}
        {details && (
          <div className="agent-bento-role" style={{ "--agent-color": color } as React.CSSProperties}>
            <div className="agent-bento-cell-title">Role</div>
            <div className="agent-bento-role-text">{details.role}</div>
          </div>
        )}

        {/* ── Cell 4: Capabilities ── */}
        {details && (
          <div className="agent-bento-caps" style={{ "--agent-color": color } as React.CSSProperties}>
            <div className="agent-bento-cell-title">Capabilities</div>
            <ul className="agent-bento-list">
              {details.capabilities.map((cap, i) => (
                <li key={i}>
                  <span style={{ color, fontWeight: 700 }}>▸</span> {cap}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* ── Cell 5: Communications ── */}
        {details && (
          <div className="agent-bento-comms" style={{ "--agent-color": color } as React.CSSProperties}>
            <div className="agent-bento-cell-title">Communications</div>
            <ul className="agent-bento-list">
              {details.communications.map((comm, i) => (
                <li key={i}>
                  <span style={{ color: "var(--color-info)", fontWeight: 700 }}>▸</span> {comm}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* ── Cell 6: Live Stats ── */}
        <div className="agent-bento-stats" style={{ "--agent-color": color } as React.CSSProperties}>
          <div className="agent-bento-cell-title">Live Stats</div>
          <div className="agent-bento-stat">
            <span className="agent-bento-stat-key">Recent messages</span>
            <span className="agent-bento-stat-val" style={{ color }}>{msgCount}</span>
          </div>
          <div className="agent-bento-stat">
            <span className="agent-bento-stat-key">Framework</span>
            <span className="agent-bento-stat-val">{node?.framework ?? "—"}</span>
          </div>
          <div className="agent-bento-stat">
            <span className="agent-bento-stat-key">Agent color</span>
            <span className="agent-bento-stat-val" style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
              <span style={{ width: 10, height: 10, borderRadius: "50%", backgroundColor: color, display: "inline-block" }} />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-micro)" }}>{color}</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
