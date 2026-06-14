/** ATC Guardian — main application component. */

import { RadarView } from "./components/RadarView";
import { useRadarData } from "./hooks/useRadarData";
import { useAtcStore } from "./stores/atcStore";
import { ScenarioControls } from "./components/ScenarioControls";
import { AuditTimeline } from "./components/AuditTimeline";
import { AgentChatPanel } from "./components/AgentChatPanel";
import { DecisionPanel } from "./components/DecisionPanel";

function App(): React.ReactElement {
  useRadarData();
  const aircraft = useAtcStore((s) => s.aircraft);
  const conflicts = useAtcStore((s) => s.conflicts);
  const emergencies = useAtcStore((s) => s.emergencies);
  const error = useAtcStore((s) => s.error);
  const lastUpdated = useAtcStore((s) => s.lastUpdated);
  const scenarioId = useAtcStore((s) => s.activeScenarioId);
  const elapsedSeconds = useAtcStore((s) => s.elapsedSeconds);

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

      {/* Main content: map + two-column right panel */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Radar map — takes most of the space */}
        <div style={{ flex: 1 }}>
          <RadarView />
        </div>

        {/* Left right column — ScenarioControls + AuditTimeline */}
        <div
          style={{
            width: "220px",
            minWidth: "220px",
            display: "flex",
            flexDirection: "column",
            borderLeft: "1px solid #1a3a1a",
            backgroundColor: "#0d0d0d",
            overflow: "hidden",
          }}
        >
          {/* Scenario controls — fixed height */}
          <ScenarioControls />

          {/* Controller decisions — human-on-the-loop approval */}
          <DecisionPanel />

          {/* Audit timeline — fills remaining space */}
          <div style={{ flex: 1, overflow: "hidden" }}>
            <AuditTimeline />
          </div>
        </div>

        {/* Right column — AgentChatPanel + alert summary */}
        <div
          style={{
            width: "280px",
            minWidth: "280px",
            display: "flex",
            flexDirection: "column",
            borderLeft: "1px solid #1a3a1a",
            backgroundColor: "#0d0d0d",
            overflow: "hidden",
          }}
        >
          {/* Alert summary */}
          <div
            style={{
              padding: "0.5rem",
              fontSize: "0.7rem",
              borderBottom: "1px solid #1a3a1a",
              flexShrink: 0,
            }}
          >
            <div style={{ marginBottom: "0.25rem" }}>
              A/C: {aircraft.length} | CNFLT: {conflicts.length} | EMG:{" "}
              {emergencies.length}
            </div>

            {/* Emergency list */}
            {emergencies.length > 0 && (
              <div style={{ marginBottom: "0.25rem" }}>
                <div style={{ color: "#ff3333", fontWeight: "bold", fontSize: "0.7rem" }}>
                  ! EMERGENCIES ({emergencies.length})
                </div>
                {emergencies.map((e) => (
                  <div
                    key={e.emergency_id}
                    style={{
                      border: "1px solid #ff3333",
                      padding: "0.2rem",
                      marginBottom: "0.15rem",
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

            {/* Conflict list */}
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
                      padding: "0.2rem",
                      marginBottom: "0.15rem",
                      fontSize: "0.6rem",
                    }}
                  >
                    <div>
                      {c.cpa.aircraft_a_callsign} &lt;=&gt; {c.cpa.aircraft_b_callsign}
                    </div>
                    <div>
                      CPA: {c.cpa.min_distance_nm}nm / {c.cpa.time_to_cpa_seconds}s
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Agent chat panel — fills remaining space */}
          <div style={{ flex: 1, overflow: "hidden" }}>
            <AgentChatPanel />
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
