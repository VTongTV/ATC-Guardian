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
      try {
        await fetch("/data/demo/stop", { method: "POST" });
      } catch {
        /* backend offline */
      }
      return;
    }
    // Start the simulation + agent collaboration loops
    try {
      await fetch("/data/demo/start", { method: "POST" });
    } catch {
      /* backend offline */
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
        // Start simulation loops if not already running
        await fetch("/data/demo/start", { method: "POST" });
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

  const activeScenario = SCENARIOS.find((s) => s.id === activeScenarioId);

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      gap: "0.6rem",
      backgroundColor: "var(--bg-deep)",
      padding: "0.6rem",
      borderBottom: "1px solid var(--border-mid)",
      fontFamily: "var(--font-mono)",
    }}>
      {/* Header */}
      <div className="atc-panel-header">
        <span className="atc-panel-title">SCENARIO</span>
      </div>

      {/* Scenario dropdown */}
      <div style={{ position: "relative" }}>
        <select
          aria-label="Select active scenario"
          style={{
            backgroundColor: "var(--bg-surface)",
            color: "var(--color-nominal)",
            border: "1px solid var(--border-bright)",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--fs-body)",
            borderRadius: "var(--radius-lg)",
            padding: "0.45rem 0.6rem",
            width: "100%",
            outline: "none",
            cursor: "pointer",
            appearance: "none" as const,
            WebkitAppearance: "none" as const,
            backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2333ff33'/%3E%3C/svg%3E")`,
            backgroundRepeat: "no-repeat",
            backgroundPosition: "right 0.5rem center",
            backgroundSize: "10px 6px",
            paddingRight: "1.6rem",
            transition: "border-color var(--transition-fast), box-shadow var(--transition-fast)",
            boxShadow: "var(--shadow-sm)",
          }}
          value={activeScenarioId}
          onChange={handleScenarioChange}
          disabled={switching}
          onFocus={(e) => {
            e.target.style.borderColor = "var(--color-nominal)";
            e.target.style.boxShadow = "0 0 0 2px rgba(51, 255, 51, 0.12), var(--shadow-sm)";
          }}
          onBlur={(e) => {
            e.target.style.borderColor = "var(--border-bright)";
            e.target.style.boxShadow = "var(--shadow-sm)";
          }}
        >
          {SCENARIOS.map((sc) => (
            <option key={sc.id} value={sc.id}>
              {sc.id} — {sc.label}
            </option>
          ))}
        </select>
      </div>

      {/* Scenario description */}
      <div style={{
        fontSize: "var(--fs-meta)",
        color: "var(--text-secondary)",
        lineHeight: 1.55,
        borderLeft: "2px solid var(--color-nominal)",
        paddingLeft: "0.5rem",
        fontFamily: "var(--font-mono)",
        backgroundColor: "rgba(51, 255, 51, 0.03)",
        padding: "0.4rem 0.6rem",
        borderRadius: "0 var(--radius-lg) var(--radius-lg) 0",
      }}>
        <span style={{ color: "var(--color-nominal)", fontWeight: 600 }}>{activeScenario?.id}</span>
        <span style={{ color: "var(--text-dim)", margin: "0 0.3rem" }}>—</span>
        {activeScenario?.description ?? "Select a scenario."}
      </div>

      {/* Guided demo button */}
      <button
        type="button"
        onClick={startGuidedDemo}
        style={{
          backgroundColor: demoPlaying ? "rgba(255, 51, 51, 0.12)" : "rgba(51, 255, 51, 0.08)",
          color: demoPlaying ? "var(--color-critical)" : "var(--color-nominal)",
          border: `1px solid ${demoPlaying ? "rgba(255, 51, 51, 0.4)" : "rgba(51, 255, 51, 0.35)"}`,
          fontFamily: "var(--font-mono)",
          fontSize: "var(--fs-body)",
          fontWeight: 600,
          borderRadius: "var(--radius-lg)",
          padding: "0.5rem 0.7rem",
          cursor: "pointer",
          letterSpacing: "0.08em",
          transition: "all var(--transition-fast)",
          boxShadow: demoPlaying
            ? "0 2px 8px rgba(255, 51, 51, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.03)"
            : "0 2px 8px rgba(51, 255, 51, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.03)",
        }}
        onMouseEnter={(e) => {
          if (!demoPlaying) {
            e.currentTarget.style.backgroundColor = "rgba(51, 255, 51, 0.14)";
            e.currentTarget.style.boxShadow = "0 4px 12px rgba(51, 255, 51, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.04)";
            e.currentTarget.style.transform = "translateY(-1px)";
          }
        }}
        onMouseLeave={(e) => {
          if (!demoPlaying) {
            e.currentTarget.style.backgroundColor = "rgba(51, 255, 51, 0.08)";
            e.currentTarget.style.boxShadow = "0 2px 8px rgba(51, 255, 51, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.03)";
            e.currentTarget.style.transform = "translateY(0)";
          }
        }}
      >
        {demoPlaying ? "■  STOP DEMO" : "▶  PLAY GUIDED DEMO"}
      </button>

      {/* Narration */}
      {narration && (
        <div style={{
          fontSize: "var(--fs-meta)",
          color: "var(--color-warning)",
          padding: "0.4rem 0.6rem",
          borderLeft: "2px solid var(--color-warning)",
          backgroundColor: "rgba(255, 170, 0, 0.06)",
          borderRadius: "0 var(--radius-lg) var(--radius-lg) 0",
          fontFamily: "var(--font-mono)",
          lineHeight: 1.5,
        }}>
          {narration}
        </div>
      )}

      {/* Status indicators */}
      <div style={{
        display: "flex",
        gap: "0.5rem",
        marginTop: "0.1rem",
      }}>
        <div style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          padding: "0.4rem 0.5rem",
          backgroundColor: "var(--bg-surface)",
          border: "1px solid var(--border-dim)",
          borderRadius: "var(--radius-lg)",
          boxShadow: "var(--shadow-sm)",
          transition: "border-color var(--transition-fast), box-shadow var(--transition-fast)",
        }}>
          <span style={{ color: "var(--text-dim)", fontSize: "var(--fs-micro)", letterSpacing: "0.06em" }}>ELAPSED</span>
          <span style={{ color: "var(--color-nominal)", fontWeight: 700, fontSize: "var(--fs-body)" }}>
            T+{Math.round(elapsedSeconds)}s
          </span>
        </div>
        <div style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          padding: "0.4rem 0.5rem",
          backgroundColor: "var(--bg-surface)",
          border: "1px solid var(--border-dim)",
          borderRadius: "var(--radius-lg)",
          boxShadow: "var(--shadow-sm)",
          transition: "border-color var(--transition-fast), box-shadow var(--transition-fast)",
        }}>
          <span style={{ color: "var(--text-dim)", fontSize: "var(--fs-micro)", letterSpacing: "0.06em" }}>AIRCRAFT</span>
          <span style={{ color: "var(--color-nominal)", fontWeight: 700, fontSize: "var(--fs-body)" }}>
            {aircraftCount}
          </span>
        </div>
      </div>
    </div>
  );
}
