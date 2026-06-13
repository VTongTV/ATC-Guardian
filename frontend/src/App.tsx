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

  return (
    <div
      style={{
        backgroundColor: "#050505",
        color: "#33ff33",
        fontFamily: "monospace",
        minHeight: "100vh",
        display: "flex",
        gap: "1rem",
        padding: "1rem",
      }}
    >
      {/* Radar display */}
      <div>
        <h1 style={{ fontSize: "1.2rem", margin: "0 0 0.5rem 0" }}>
          ATC GUARDIAN — RADAR
        </h1>
        <RadarView />
      </div>

      {/* Side panel — alerts and status */}
      <div style={{ flex: 1, minWidth: "200px" }}>
        <h2 style={{ fontSize: "1rem", margin: "0 0 0.5rem 0" }}>STATUS</h2>
        <p style={{ fontSize: "0.8rem", color: "#888" }}>
          {lastUpdated
            ? `Last update: ${new Date(lastUpdated).toLocaleTimeString()}`
            : "Awaiting data..."}
        </p>
        <p style={{ fontSize: "0.8rem" }}>
          Aircraft: {aircraft.length} | Conflicts: {conflicts.length} | Emergencies:{" "}
          {emergencies.length}
        </p>

        {error && (
          <p style={{ color: "#ff3333", fontSize: "0.8rem" }}>ERROR: {error}</p>
        )}

        {/* Conflict list */}
        {conflicts.length > 0 && (
          <div style={{ marginTop: "1rem" }}>
            <h3 style={{ color: "#ffaa00", fontSize: "0.9rem" }}>
              CONFLICTS ({conflicts.length})
            </h3>
            {conflicts.map((c) => (
              <div
                key={c.advisory_id}
                style={{
                  border: "1px solid #ffaa00",
                  padding: "0.5rem",
                  margin: "0.25rem 0",
                  fontSize: "0.75rem",
                }}
              >
                <div>
                  {c.cpa.aircraft_a_callsign} ↔ {c.cpa.aircraft_b_callsign}
                </div>
                <div>
                  CPA: {c.cpa.min_distance_nm} nm in {c.cpa.time_to_cpa_seconds}s
                </div>
                <div>Severity: {c.severity.toUpperCase()}</div>
              </div>
            ))}
          </div>
        )}

        {/* Emergency list */}
        {emergencies.length > 0 && (
          <div style={{ marginTop: "1rem" }}>
            <h3 style={{ color: "#ff3333", fontSize: "0.9rem" }}>
              EMERGENCIES ({emergencies.length})
            </h3>
            {emergencies.map((e) => (
              <div
                key={e.emergency_id}
                style={{
                  border: "1px solid #ff3333",
                  padding: "0.5rem",
                  margin: "0.25rem 0",
                  fontSize: "0.75rem",
                }}
              >
                <div>SQUAWK {e.squawk_code} — {e.callsign}</div>
                <div>Phase: {e.phase.toUpperCase()}</div>
              </div>
            ))}
          </div>
        )}

        {/* Aircraft list */}
        <div style={{ marginTop: "1rem" }}>
          <h3 style={{ fontSize: "0.9rem" }}>AIRCRAFT</h3>
          {aircraft.map((ac) => (
            <div
              key={ac.callsign}
              style={{
                fontSize: "0.7rem",
                color: ac.squawk === "7700" ? "#ff3333" : "#33ff33",
                padding: "0.1rem 0",
              }}
            >
              {ac.callsign} FL{Math.round(ac.altitude_ft / 100).toString().padStart(3, "0")}{" "}
              {Math.round(ac.heading_deg)}° {Math.round(ac.speed_kts)}kt
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default App;
