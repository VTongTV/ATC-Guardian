/** ATC Guardian — main application component. */

import React from "react";
import { RadarView } from "./components/RadarView";
import { useRadarData } from "./hooks/useRadarData";
import { useAtcStore } from "./stores/atcStore";
import { ScenarioControls } from "./components/ScenarioControls";
import { AgentChatPanel } from "./components/AgentChatPanel";
import { DecisionPanel } from "./components/DecisionPanel";
import { CollaborationFlow } from "./components/CollaborationFlow";

function App(): React.ReactElement {
  useRadarData();
  const aircraft = useAtcStore((s) => s.aircraft);
  const conflicts = useAtcStore((s) => s.conflicts);
  const emergencies = useAtcStore((s) => s.emergencies);
  const error = useAtcStore((s) => s.error);
  const lastUpdated = useAtcStore((s) => s.lastUpdated);
  const scenarioId = useAtcStore((s) => s.activeScenarioId);
  const elapsedSeconds = useAtcStore((s) => s.elapsedSeconds);

  const [panelWidth, setPanelWidth] = React.useState(() =>
    typeof window !== "undefined" ? Math.max(480, window.innerWidth * 0.55) : 720
  );
  const isDragging = React.useRef(false);

  const handleResizeStart = React.useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDragging.current = true;

    const handleMove = (moveEvent: MouseEvent) => {
      if (!isDragging.current) return;
      const newWidth = window.innerWidth - moveEvent.clientX;
      setPanelWidth(Math.max(480, Math.min(newWidth, window.innerWidth * 0.85)));
    };

    const handleUp = () => {
      isDragging.current = false;
      document.removeEventListener("mousemove", handleMove);
      document.removeEventListener("mouseup", handleUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.addEventListener("mousemove", handleMove);
    document.addEventListener("mouseup", handleUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  return (
    <div
      style={{
        backgroundColor: "#0a0a0a",
        color: "#33ff33",
        fontFamily: "monospace",
        height: "100vh",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Header bar */}
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "0.4rem 1rem",
          backgroundColor: "#0d0d0d",
          borderBottom: "1px solid #1a3a1a",
          flexShrink: 0,
        }}
      >
        <h1 style={{ fontSize: "1rem", margin: 0, letterSpacing: "0.1em" }}>
          ATC GUARDIAN <span style={{ fontSize: "0.65rem", color: "#888" }}>AI-assisted, human-decided</span>
        </h1>
        <div style={{ fontSize: "0.75rem", color: "#888" }}>
          {scenarioId} | T+{Math.round(elapsedSeconds)}s |{" "}
          {lastUpdated
            ? `Update: ${new Date(lastUpdated).toLocaleTimeString()}`
            : "Awaiting data..."}
          {error && <span style={{ color: "#ff3333" }}> | ERR: {error}</span>}
        </div>
      </header>

      {/* Main content: map + resizable side panel */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Radar map — takes remaining space */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <RadarView />
        </div>

        {/* Resize handle */}
        <div
          onMouseDown={handleResizeStart}
          style={{
            width: "4px",
            cursor: "col-resize",
            backgroundColor: "#1a3a1a",
            flexShrink: 0,
            transition: "background-color 0.2s",
          }}
          onMouseEnter={(e) => {
            (e.target as HTMLElement).style.backgroundColor = "#33ff33";
          }}
          onMouseLeave={(e) => {
            (e.target as HTMLElement).style.backgroundColor = "#1a3a1a";
          }}
        />

        {/* Right side panel — 3-row left column + AGENT COMMS spanning right + AGENT TEAM footer
         *
         *  ┌──────────────┬──────────────┐
         *  │  SCENARIO     │              │
         *  ├──────────────┤  AGENT COMMS  │
         *  │  CONFLICTS    │              │
         *  ├──────────────┤              │
         *  │  DECISIONS    │              │
         *  ├──────────────┴──────────────┤
         *  │        AGENT TEAM            │
         *  └──────────────────────────────┘
         */}
        <div
          style={{
            width: `${panelWidth}px`,
            minWidth: "480px",
            display: "grid",
            gridTemplateRows: "1fr 1fr 1fr auto",
            gridTemplateColumns: "1fr 1fr",
            gap: "0px",
            borderLeft: "1px solid #1a3a1a",
            backgroundColor: "#0d0d0d",
            overflow: "hidden",
          }}
        >
          {/* ── Row 1, Col 1: Scenario controls ── */}
          <div style={{ overflow: "auto", borderRight: "1px solid #1a3a1a", borderBottom: "1px solid #1a3a1a" }}>
            <ScenarioControls />
          </div>

          {/* ── Row 1–3, Col 2: Agent comms (spans all 3 rows) ── */}
          <div style={{ overflow: "hidden", gridRow: "1 / 4", gridColumn: "2" }}>
            <AgentChatPanel />
          </div>

          {/* ── Row 2, Col 1: Conflicts / Emergencies ── */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              overflow: "auto",
              borderRight: "1px solid #1a3a1a",
              borderBottom: "1px solid #1a3a1a",
            }}
          >
            <div
              style={{
                padding: "0.4rem 0.5rem",
                fontSize: "0.7rem",
                color: "#888",
              }}
            >
              <div style={{ marginBottom: "0.2rem" }}>
                A/C: {aircraft.length} | CNFLT: {conflicts.length} | EMG:{" "}
                {emergencies.length}
              </div>
              {emergencies.length > 0 && (
                <div style={{ marginBottom: "0.2rem" }}>
                  <div style={{ color: "#ff3333", fontWeight: "bold", fontSize: "0.7rem" }}>
                    ! EMERGENCIES ({emergencies.length})
                  </div>
                  {emergencies.map((e) => (
                    <div
                      key={e.emergency_id}
                      style={{
                        border: "1px solid #ff3333",
                        padding: "0.15rem",
                        marginBottom: "0.1rem",
                        fontSize: "0.6rem",
                      }}
                    >
                      <div style={{ fontWeight: "bold" }}>
                        SQ{e.squawk_code} — {e.callsign}
                      </div>
                      <div>Phase: {e.phase.toUpperCase()}</div>
                    </div>
                  ))}
                </div>
              )}
              {conflicts.length > 0 && (
                <div>
                  <div style={{ color: "#ffaa00", fontWeight: "bold", fontSize: "0.7rem" }}>
                    * CONFLICTS ({conflicts.length})
                  </div>
                  {conflicts.map((c) => (
                    <div
                      key={c.advisory_id}
                      style={{
                        border: "1px solid #ffaa00",
                        padding: "0.15rem",
                        marginBottom: "0.1rem",
                        fontSize: "0.6rem",
                      }}
                    >
                      <div>
                        {c.cpa.aircraft_a_callsign} <=> {c.cpa.aircraft_b_callsign}
                      </div>
                      <div>
                        CPA: {c.cpa.min_distance_nm}nm / {c.cpa.time_to_cpa_seconds}s
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* ── Row 3, Col 1: Controller decisions ── */}
          <div style={{ overflow: "auto", borderRight: "1px solid #1a3a1a" }}>
            <DecisionPanel />
          </div>

          {/* ── Footer: Agent team — spans both columns ── */}
          <div style={{ gridColumn: "1 / -1", overflow: "hidden", borderTop: "1px solid #1a3a1a" }}>
            <CollaborationFlow />
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
