/** ATC Guardian — scenario selection and data-mode controls. */

import { useCallback, useRef, useState } from "react";
import { useAtcStore } from "../stores/atcStore";

/** Available scenario definitions. */
const SCENARIOS: { id: string; label: string }[] = [
  { id: "SCN-A", label: "Converging Courses" },
  { id: "SCN-B", label: "Thunderstorm Line" },
  { id: "SCN-C", label: "Mayday at FL350" },
];

/** Narration beats for the guided demo, per scenario + elapsed seconds. */
const DEMO_NARRATION: Record<string, Record<number, string>> = {
  "SCN-A": {
    0: "Converging courses: UAL123 and DAL456 at FL350.",
    8: "Conflict Detector flags CPA under 5nm -> Safety Reviewer.",
    16: "Reviewer APPROVES -> Coordinator surfaces to controller.",
  },
  "SCN-B": {
    0: "Severe-turbulence SIGMET over BAW200's approach.",
    8: "Weather Analyst detects overlap -> deviation advisory.",
    16: "Reviewer APPROVES -> Coordinator surfaces deviation.",
  },
  "SCN-C": {
    0: "SWA770 squawks 7700, emergency descent.",
    8: "Emergency Response DISTRESS -> recruits Ground Ops.",
    16: "KJFK runway info -> Reviewer approves resolution.",
  },
};

/** Seconds to dwell on each scenario during the guided demo. */
const DEMO_SCENARIO_SECONDS = 24;

/** ScenarioControls — dropdown, live/sim toggle, status indicators. */
export function ScenarioControls(): React.ReactElement {
  const activeScenarioId = useAtcStore((s) => s.activeScenarioId);
  const elapsedSeconds = useAtcStore((s) => s.elapsedSeconds);
  const aircraftCount = useAtcStore((s) => s.aircraft.length);
  const setActiveScenario = useAtcStore((s) => s.setActiveScenario);

  const [isLive, setIsLive] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [demoPlaying, setDemoPlaying] = useState(false);
  const [narration, setNarration] = useState<string>("");
  const demoTimers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const clearDemoTimers = useCallback(() => {
    demoTimers.current.forEach((t) => clearTimeout(t));
    demoTimers.current = [];
  }, []);

  const startGuidedDemo = useCallback(async () => {
    if (demoPlaying) {
      clearDemoTimers();
      setDemoPlaying(false);
      setNarration("");
      return;
    }
    setDemoPlaying(true);
    for (const scenario of SCENARIOS) {
      // Switch scenario
      try {
        await fetch(`/data/scenario/${scenario.id}`, { method: "POST" });
        setActiveScenario(scenario.id);
      } catch {
        /* backend offline */
      }
      // Schedule narration beats
      const beats = DEMO_NARRATION[scenario.id] ?? {};
      for (const [elapsedStr, cue] of Object.entries(beats)) {
        const elapsed = Number(elapsedStr);
        const t = setTimeout(() => setNarration(cue), elapsed * 1000);
        demoTimers.current.push(t);
      }
      // Dwell before next scenario
      await new Promise((resolve) => setTimeout(resolve, DEMO_SCENARIO_SECONDS * 1000));
    }
    setDemoPlaying(false);
    setNarration("Guided demo complete.");
    const t = setTimeout(() => setNarration(""), 4000);
    demoTimers.current.push(t);
  }, [demoPlaying, clearDemoTimers, setActiveScenario]);

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

      {/* Guided demo button */}
      <button
        type="button"
        onClick={startGuidedDemo}
        style={{
          backgroundColor: demoPlaying ? "#3a1a1a" : "#1a3a1a",
          color: demoPlaying ? "#ff3333" : "#33ff33",
          border: `1px solid ${demoPlaying ? "#ff3333" : "#33ff33"}`,
          fontFamily: "monospace",
          fontSize: "0.65rem",
          padding: "0.3rem",
          cursor: "pointer",
          letterSpacing: "0.05em",
        }}
      >
        {demoPlaying ? "■ STOP DEMO" : "▶ PLAY GUIDED DEMO"}
      </button>
      {narration && (
        <div style={{ fontSize: "0.6rem", color: "#ffaa00", padding: "0.2rem", borderLeft: "2px solid #ffaa00" }}>
          {narration}
        </div>
      )}

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
