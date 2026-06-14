/** ATC Guardian — scenario selection and data-mode controls. */

import { useCallback, useState } from "react";
import { useAtcStore } from "../stores/atcStore";

/** Available scenario definitions. */
const SCENARIOS: { id: string; label: string }[] = [
  { id: "SCN-A", label: "Converging Courses" },
  { id: "SCN-B", label: "Thunderstorm Line" },
  { id: "SCN-C", label: "Mayday at FL350" },
];

/** ScenarioControls — dropdown, live/sim toggle, status indicators. */
export function ScenarioControls(): React.ReactElement {
  const activeScenarioId = useAtcStore((s) => s.activeScenarioId);
  const elapsedSeconds = useAtcStore((s) => s.elapsedSeconds);
  const aircraftCount = useAtcStore((s) => s.aircraft.length);
  const setActiveScenario = useAtcStore((s) => s.setActiveScenario);

  const [isLive, setIsLive] = useState(false);
  const [switching, setSwitching] = useState(false);

  const handleScenarioChange = useCallback(
    async (e: React.ChangeEvent<HTMLSelectElement>) => {
      const newId = e.target.value;
      setSwitching(true);
      try {
        const res = await fetch(`/data/scenario/${newId}`, { method: "POST" });
        if (res.ok) {
          setActiveScenario(newId);
        }
      } catch {
        /* backend offline */
      } finally {
        setSwitching(false);
      }
    },
    [setActiveScenario],
  );

  const handleToggleLive = useCallback(() => {
    setIsLive((prev) => !prev);
  }, []);

  const panelStyle: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: "0.5rem",
    backgroundColor: "#0a0a0a",
    padding: "0.5rem",
    borderBottom: "1px solid #1a3a1a",
  };

  const labelStyle: React.CSSProperties = {
    fontSize: "0.65rem",
    color: "#888",
    letterSpacing: "0.05em",
  };

  const selectStyle: React.CSSProperties = {
    backgroundColor: "#111",
    color: "#33ff33",
    border: "1px solid #1a3a1a",
    fontFamily: "monospace",
    fontSize: "0.7rem",
    padding: "0.25rem",
    width: "100%",
    outline: "none",
  };

  const toggleRowStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "0.5rem",
  };

  const toggleTrackStyle: React.CSSProperties = {
    width: "32px",
    height: "16px",
    borderRadius: "8px",
    backgroundColor: isLive ? "#33ff33" : "#333",
    cursor: "pointer",
    position: "relative",
    transition: "background-color 0.2s",
    flexShrink: 0,
  };

  const toggleThumbStyle: React.CSSProperties = {
    width: "12px",
    height: "12px",
    borderRadius: "50%",
    backgroundColor: "#fff",
    position: "absolute",
    top: "2px",
    left: isLive ? "18px" : "2px",
    transition: "left 0.2s",
  };

  const statRowStyle: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    fontSize: "0.65rem",
    color: "#888",
  };

  return (
    <div style={panelStyle}>
      {/* Header */}
      <div style={{ ...labelStyle, color: "#33ff33", fontSize: "0.7rem" }}>
        SCENARIO
      </div>

      {/* Scenario dropdown */}
      <select
        style={selectStyle}
        value={activeScenarioId}
        onChange={handleScenarioChange}
        disabled={switching}
      >
        {SCENARIOS.map((sc) => (
          <option key={sc.id} value={sc.id}>
            {sc.id} — {sc.label}
          </option>
        ))}
      </select>

      {/* Live / Simulated toggle */}
      <div style={toggleRowStyle}>
        <span style={{ ...labelStyle, color: isLive ? "#33ff33" : "#888" }}>
          {isLive ? "LIVE" : "SIM"}
        </span>
        <div style={toggleTrackStyle} onClick={handleToggleLive} role="button" tabIndex={0}>
          <div style={toggleThumbStyle} />
        </div>
      </div>

      {/* Status indicators */}
      <div style={statRowStyle}>
        <span>ELAPSED</span>
        <span style={{ color: "#33ff33" }}>T+{Math.round(elapsedSeconds)}s</span>
      </div>
      <div style={statRowStyle}>
        <span>AIRCRAFT</span>
        <span style={{ color: "#33ff33" }}>{aircraftCount}</span>
      </div>
    </div>
  );
}
