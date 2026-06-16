/** ATC Guardian — scenario selection and data-mode controls. */

import { useCallback, useRef, useState } from "react";
import { useAtcStore } from "../stores/atcStore";

/** Available scenario definitions. */
const SCENARIOS: { id: string; label: string; description: string }[] = [
  { id: "SCN-A", label: "Converging Conflict", description: "Two aircraft on converging headings at FL350 trigger a conflict advisory." },
  { id: "SCN-B", label: "Thunderstorm Line", description: "SIGMET for severe turbulence forces aircraft to deviate from approach." },
  { id: "SCN-C", label: "Mayday at FL350", description: "Aircraft declares emergency (7700) and begins rapid descent from FL350." },
  { id: "SCN-D", label: "Parallel Approach", description: "Two aircraft on parallel ILS approaches with lateral separation eroding." },
  { id: "SCN-E", label: "Lost Communication", description: "Aircraft squawking 7600 (radio failure) near arrival corridor." },
  { id: "SCN-F", label: "Microburst Alert", description: "Wind shear / microburst detected on final approach path." },
  { id: "SCN-G", label: "Missed Approach", description: "Go-around conflicts with departing traffic below." },
  { id: "SCN-H", label: "Hijack Code", description: "Aircraft squawking 7500 (unlawful interference) at FL280." },
  { id: "SCN-I", label: "Fuel Emergency", description: "Aircraft declaring minimum fuel emergency on approach." },
  { id: "SCN-J", label: "Runway Incursion", description: "Ground conflict between departing and arriving aircraft." },
];

/** Narration beats for the guided demo, per scenario + elapsed seconds. */
const DEMO_NARRATION: Record<string, Record<number, string>> = {
  "SCN-A": {
    0: "Converging courses: UAL123 and DAL456 at FL350.",
    8: "Conflict Detector flags CPA under 5nm → Safety Reviewer.",
    16: "Reviewer APPROVES → Coordinator surfaces to controller.",
  },
  "SCN-B": {
    0: "Severe-turbulence SIGMET over BAW200's approach.",
    8: "Weather Analyst detects overlap → deviation advisory.",
    16: "Reviewer APPROVES → Coordinator surfaces deviation.",
  },
  "SCN-C": {
    0: "SWA770 squawks 7700, emergency descent.",
    8: "Emergency Response DISTRESS → recruits Ground Ops.",
    16: "KJFK runway info → Reviewer approves resolution.",
  },
  "SCN-D": {
    0: "Parallel approaches: AAL200 and UAL300 lateral separation eroding.",
    8: "Conflict Detector flags parallel approach breach → Safety Reviewer.",
    16: "Reviewer APPROVES → Coordinator surfaces lateral separation advisory.",
  },
  "SCN-E": {
    0: "RDU100 squawks 7600 — radio failure on approach.",
    8: "Emergency Response: treat as NORDO → vector for visual approach.",
    16: "Reviewer APPROVES → Coordinator surfaces NORDO procedures.",
  },
  "SCN-F": {
    0: "Microburst SIGMET on final approach corridor.",
    8: "Weather Analyst: wind shear detected → missed approach advisory.",
    16: "Reviewer APPROVES → Coordinator surfaces go-around command.",
  },
  "SCN-G": {
    0: "SWA500 executing missed approach, AAL600 departing below.",
    8: "Conflict Detector: climbing traffic conflict → vertical separation advisory.",
    16: "Reviewer APPROVES → Coordinator surfaces altitude restriction.",
  },
  "SCN-H": {
    0: "TFR800 squawks 7500 — hijack code at FL280.",
    8: "Emergency Response: unlawful interference → coordinate with security.",
    16: "Reviewer APPROVES → Coordinator surfaces security protocol.",
  },
  "SCN-I": {
    0: "JBU900 declares fuel emergency, descending through FL120.",
    8: "Emergency Response: minimum fuel → priority handling.",
    16: "Ground Ops: nearest suitable → Reviewer approves priority approach.",
  },
  "SCN-J": {
    0: "Runway incursion: EDF200 on runway, EDF100 on approach.",
    8: "Conflict Detector: surface conflict → immediate go-around advisory.",
    16: "Reviewer APPROVES → Coordinator surfaces go-around command.",
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

      {/* Scenario description */}
      <div style={{ fontSize: "0.6rem", color: "#888", padding: "0.2rem 0", lineHeight: 1.4 }}>
        {SCENARIOS.find((s) => s.id === activeScenarioId)?.description ?? "Select a scenario."}
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
