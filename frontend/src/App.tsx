/** ATC Guardian — main application component. */

import { RadarView } from "./components/RadarView";
import { useRadarData } from "./hooks/useRadarData";
import { useAtcStore } from "./stores/atcStore";

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
          ATC GUARDIAN
        </h1>
        <div style={{ fontSize: "0.75rem", color: "#888" }}>
          {scenarioId} | T+{Math.round(elapsedSeconds)}s |{" "}
          {lastUpdated
            ? `Update: ${new Date(lastUpdated).toLocaleTimeString()}`
            : "Awaiting data..."}
          {error && <span style={{ color: "#ff3333" }}> | ERR: {error}</span>}
        </div>
      </header>

      {/* Main content: map + side panel */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Radar map — takes most of the space */}
        <div style={{ flex: 1 }}>
          <RadarView />
        </div>

        {/* Side panel — alerts and status */}
        <div
          style={{
            width: "260px",
            minWidth: "260px",
            padding: "0.5rem",
            overflowY: "auto",
            borderLeft: "1px solid #1a3a1a",
            backgroundColor: "#0d0d0d",
          }}
        >
          <div style={{ fontSize: "0.8rem", marginBottom: "0.5rem" }}>
            A/C: {aircraft.length} | Conflicts: {conflicts.length} | EMG:{" "}
            {emergencies.length}
          </div>

          {/* Emergency list */}
          {emergencies.length > 0 && (
            <div style={{ marginBottom: "0.5rem" }}>
              <h3 style={{ color: "#ff3333", fontSize: "0.8rem", margin: "0 0 0.25rem 0" }}>
                ▲ EMERGENCIES ({emergencies.length})
              </h3>
              {emergencies.map((e) => (
                <div
                  key={e.emergency_id}
                  style={{
                    border: "1px solid #ff3333",
                    padding: "0.3rem",
                    marginBottom: "0.25rem",
                    fontSize: "0.7rem",
                  }}
                >
                  <div style={{ fontWeight: "bold" }}>
                    SQUAWK {e.squawk_code} — {e.callsign}
                  </div>
                  <div>Phase: {e.phase.toUpperCase()}</div>
                </div>
              ))}
            </div>
          )}

          {/* Conflict list */}
          {conflicts.length > 0 && (
            <div style={{ marginBottom: "0.5rem" }}>
              <h3 style={{ color: "#ffaa00", fontSize: "0.8rem", margin: "0 0 0.25rem 0" }}>
                ◆ CONFLICTS ({conflicts.length})
              </h3>
              {conflicts.map((c) => (
                <div
                  key={c.advisory_id}
                  style={{
                    border: "1px solid #ffaa00",
                    padding: "0.3rem",
                    marginBottom: "0.25rem",
                    fontSize: "0.7rem",
                  }}
                >
                  <div>
                    {c.cpa.aircraft_a_callsign} ↔ {c.cpa.aircraft_b_callsign}
                  </div>
                  <div>
                    CPA: {c.cpa.min_distance_nm}nm / {c.cpa.time_to_cpa_seconds}s
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Aircraft list */}
          <div>
            <h3 style={{ fontSize: "0.8rem", margin: "0 0 0.25rem 0" }}>
              ✈ AIRCRAFT
            </h3>
            {aircraft.map((ac) => (
              <div
                key={ac.callsign}
                style={{
                  fontSize: "0.7rem",
                  color: ac.squawk === "7700" ? "#ff3333" : "#33ff33",
                  padding: "0.15rem 0",
                  borderBottom: "1px solid #1a2a1a",
                }}
              >
                {ac.callsign} FL
                {Math.round(ac.altitude_ft / 100)
                  .toString()
                  .padStart(3, "0")}{" "}
                {Math.round(ac.heading_deg).toString().padStart(3, "0")}°{" "}
                {Math.round(ac.speed_kts)}kt
                {ac.squawk !== "1200" && (
                  <span style={{ color: "#ff8800", marginLeft: "0.3rem" }}>
                    SQ{ac.squawk}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
