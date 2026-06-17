/** ATC Guardian — main application component. */

import React from "react";
import { RadarView } from "./components/RadarView";
import { useRadarData } from "./hooks/useRadarData";
import { useAtcStore } from "./stores/atcStore";
import { ScenarioControls } from "./components/ScenarioControls";
import { AgentChatPanel } from "./components/AgentChatPanel";
import { DecisionPanel } from "./components/DecisionPanel";
import { AgentTeamPage } from "./components/AgentTeamPage";

/** Simple page-level routing via state. No router library needed. */
type Page = "dashboard" | "agent-team";

/** Connection status derived from error + lastUpdated state. */
function useConnectionStatus(error: string | null, lastUpdated: string | null) {
  if (error) return { color: "var(--color-warning)", label: "RECONNECTING", animation: "pulse-reconnect 2s ease-in-out infinite" } as const;
  if (!lastUpdated) return { color: "var(--text-dim)", label: "OFFLINE", animation: "none" } as const;
  return { color: "var(--color-nominal)", label: "LIVE", animation: "pulse-live 2s ease-in-out infinite" } as const;
}

/** Inline favicon SVG for header. */
function FaviconIcon(): React.ReactElement {
  return (
    <svg width="20" height="20" viewBox="0 0 64 64" style={{ flexShrink: 0 }}>
      <rect width="64" height="64" rx="10" fill="#04150a" />
      <path d="M32 32 L13 9 A30 30 0 0 1 51 9 Z" fill="#2dff6b" opacity="0.22" />
      <circle cx="32" cy="32" r="24" fill="none" stroke="#2dff6b" strokeWidth="2" opacity="0.55" />
      <line x1="32" y1="4" x2="32" y2="9" stroke="#2dff6b" strokeWidth="2" opacity="0.6" />
      <line x1="32" y1="55" x2="32" y2="60" stroke="#2dff6b" strokeWidth="2" opacity="0.6" />
      <line x1="4" y1="32" x2="9" y2="32" stroke="#2dff6b" strokeWidth="2" opacity="0.6" />
      <line x1="55" y1="32" x2="60" y2="32" stroke="#2dff6b" strokeWidth="2" opacity="0.6" />
      <polygon points="32,20 39,44 32,39 25,44" fill="#39ff7a" />
    </svg>
  );
}

function App(): React.ReactElement {
  useRadarData();
  const aircraft = useAtcStore((s) => s.aircraft);
  const conflicts = useAtcStore((s) => s.conflicts);
  const emergencies = useAtcStore((s) => s.emergencies);
  const error = useAtcStore((s) => s.error);
  const lastUpdated = useAtcStore((s) => s.lastUpdated);
  const scenarioId = useAtcStore((s) => s.activeScenarioId);
  const elapsedSeconds = useAtcStore((s) => s.elapsedSeconds);

  const [page, setPage] = React.useState<Page>("dashboard");

  const [panelWidth, setPanelWidth] = React.useState(() =>
    typeof window !== "undefined" ? Math.max(480, window.innerWidth * 0.55) : 720
  );
  const isDragging = React.useRef(false);

  // Dismissible error toast state
  const [dismissedError, setDismissedError] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (!error) setDismissedError(null);
  }, [error]);

  const connStatus = useConnectionStatus(error, lastUpdated);

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

  // ── Agent Team page ──────────────────────────────────────────────
  if (page === "agent-team") {
    return (
      <div className="atc-agent-team-page">
        {/* Header */}
        <header
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "var(--sp-2) var(--sp-4)",
            backgroundColor: "var(--bg-mid)",
            borderBottom: "1px solid var(--border-mid)",
            flexShrink: 0,
            boxShadow: "0 2px 8px rgba(0, 0, 0, 0.2)",
            position: "relative",
            zIndex: 10,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
            <FaviconIcon />
            <h1 style={{ fontSize: "var(--fs-header)", fontWeight: 600, margin: 0, letterSpacing: "0.1em" }}>
              ATC GUARDIAN{" "}
              <span style={{ fontSize: "var(--fs-meta)", color: "var(--text-dim)", fontWeight: 400 }}>
                AI-assisted, human-decided
              </span>
            </h1>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-3)" }}>
            <button
              onClick={() => setPage("dashboard")}
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
              }}
            >
              <span style={{ fontSize: "0.7rem" }}>←</span>
              DASHBOARD
            </button>
          </div>
        </header>
        <AgentTeamPage />
      </div>
    );
  }

  // ── Dashboard page ───────────────────────────────────────────────
  return (
    <div className="atc-page">
      {/* Dismissible error toast */}
      {error && error !== dismissedError && (
        <div
          style={{
            position: "relative",
            display: "flex",
            alignItems: "center",
            gap: "var(--sp-2)",
            padding: "var(--sp-1) var(--sp-4)",
            backgroundColor: "rgba(255,51,51,0.12)",
            borderLeft: "3px solid var(--color-critical)",
            fontSize: "var(--fs-body)",
            color: "var(--color-critical)",
            fontFamily: "var(--font-mono)",
            animation: "toast-slide-in 0.3s ease-out",
            flexShrink: 0,
            borderBottom: "1px solid rgba(255,51,51,0.15)",
          }}
        >
          <span style={{ flex: 1 }}>⚠ {error}</span>
          <button
            onClick={() => setDismissedError(error)}
            style={{
              background: "none",
              border: "none",
              color: "var(--color-critical)",
              cursor: "pointer",
              fontSize: "0.85rem",
              padding: "0 0.3rem",
              lineHeight: 1,
              fontFamily: "var(--font-mono)",
            }}
            aria-label="Dismiss error"
          >
            ×
          </button>
        </div>
      )}

      {/* Header bar */}
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "var(--sp-2) var(--sp-4)",
          backgroundColor: "var(--bg-mid)",
          borderBottom: "1px solid var(--border-mid)",
          flexShrink: 0,
          boxShadow: "0 2px 8px rgba(0, 0, 0, 0.2)",
          position: "relative",
          zIndex: 10,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
          <FaviconIcon />
          <h1 style={{ fontSize: "var(--fs-header)", fontWeight: 600, margin: 0, letterSpacing: "0.1em" }}>
            ATC GUARDIAN{" "}
            <span style={{ fontSize: "var(--fs-meta)", color: "var(--text-dim)", fontWeight: 400 }}>
              AI-assisted, human-decided
            </span>
          </h1>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-3)", fontSize: "var(--fs-body)", color: "var(--text-secondary)" }}>
          <span>{scenarioId} | T+{Math.round(elapsedSeconds)}s</span>
          <span style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}>
            {lastUpdated && (
              <span
                style={{
                  display: "inline-block",
                  width: "6px",
                  height: "6px",
                  borderRadius: "50%",
                  backgroundColor: "var(--color-nominal)",
                  animation: "pulse-live 2s ease-in-out infinite",
                }}
              />
            )}
            {lastUpdated
              ? `Update: ${new Date(lastUpdated).toLocaleTimeString()}`
              : "Awaiting data..."}
          </span>
          {/* Connection indicator */}
          <span style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "var(--fs-micro)" }}>
            <span
              style={{
                display: "inline-block",
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                backgroundColor: connStatus.color,
                animation: connStatus.animation,
              }}
            />
            <span style={{ color: connStatus.color, letterSpacing: "0.06em" }}>{connStatus.label}</span>
          </span>
          {/* Agent Team nav button */}
          <button
            onClick={() => setPage("agent-team")}
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
            }}
          >
            AGENT TEAM
            <span style={{ fontSize: "0.6rem", opacity: 0.6 }}>→</span>
          </button>
        </div>
      </header>

      {/* Main content: map + resizable side panel */}
      <div className="atc-main-layout" style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Radar map — takes remaining space */}
        <div className="atc-map-container" style={{ flex: 1, minWidth: 0 }}>
          <RadarView />
        </div>

        {/* Resize handle */}
        <div
          className="atc-resize-handle"
          onMouseDown={handleResizeStart}
          style={{
            width: "4px",
            cursor: "col-resize",
            backgroundColor: "var(--border-mid)",
            flexShrink: 0,
            transition: "background-color 0.2s",
          }}
          onMouseEnter={(e) => {
            (e.target as HTMLElement).style.backgroundColor = "var(--color-nominal)";
          }}
          onMouseLeave={(e) => {
            (e.target as HTMLElement).style.backgroundColor = "var(--border-mid)";
          }}
        />

        {/* Right side panel — 3-row left column + AGENT COMMS spanning right
         *
         *  ┌──────────────┬──────────────┐
         *  │  SCENARIO     │              │
         *  ├──────────────┤  AGENT COMMS  │
         *  │  SITUATION    │              │
         *  ├──────────────┤              │
         *  │  DECISIONS    │              │
         *  └──────────────┴──────────────┘
         */}
        <div
          className="atc-side-panel"
          style={{
            width: `${panelWidth}px`,
            minWidth: "480px",
            display: "grid",
            gridTemplateRows: "auto 1fr auto",
            gridTemplateColumns: "1fr 1fr",
            gap: "0px",
            borderLeft: "1px solid var(--border-mid)",
            backgroundColor: "var(--bg-mid)",
            overflow: "hidden",
            boxShadow: "-2px 0 16px rgba(0, 0, 0, 0.35)",
          }}
        >
          {/* ── Row 1, Col 1: Scenario controls ── */}
          <div style={{ overflow: "auto", borderRight: "1px solid var(--border-mid)", borderBottom: "1px solid var(--border-mid)" }}>
            <ScenarioControls />
          </div>

          {/* ── Row 1–3, Col 2: Agent comms (spans all 3 rows) ── */}
          <div style={{ overflow: "hidden", gridRow: "1 / 4", gridColumn: "2" }}>
            <AgentChatPanel />
          </div>

          {/* ── Row 2, Col 1: Situation ── */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              overflow: "auto",
              borderRight: "1px solid var(--border-mid)",
              borderBottom: "1px solid var(--border-mid)",
            }}
          >
            {/* Panel header */}
            <div className="atc-panel-header">
              <span className="atc-panel-title">SITUATION</span>
            </div>

            <div
              style={{
                padding: "var(--sp-2) var(--sp-3)",
                fontSize: "var(--fs-body)",
                color: "var(--text-secondary)",
              }}
            >
              {/* Stat chips */}
              <div style={{
                display: 'flex', gap: 'var(--sp-2)', marginBottom: 'var(--sp-3)', flexWrap: 'wrap'
              }}>
                <div style={{
                  padding: 'var(--sp-2) var(--sp-3)',
                  borderRadius: 'var(--radius-lg)',
                  border: '1px solid rgba(51, 255, 51, 0.25)',
                  backgroundColor: 'rgba(51, 255, 51, 0.06)',
                  fontSize: 'var(--fs-meta)',
                  color: 'var(--color-nominal)',
                  fontFamily: 'var(--font-mono)',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '0.15rem',
                  minWidth: '50px',
                  boxShadow: 'var(--shadow-sm)',
                  transition: 'border-color var(--transition-fast), box-shadow var(--transition-fast)',
                }}>
                  <span style={{ fontSize: 'var(--fs-micro)', opacity: 0.6, letterSpacing: '0.08em' }}>A/C</span>
                  <span style={{ fontWeight: 700, fontSize: 'var(--fs-body)' }}>{aircraft.length}</span>
                </div>
                <div style={{
                  padding: 'var(--sp-2) var(--sp-3)',
                  borderRadius: 'var(--radius-lg)',
                  border: conflicts.length > 0 ? '1px solid rgba(255, 170, 0, 0.4)' : '1px solid rgba(255, 170, 0, 0.2)',
                  backgroundColor: conflicts.length > 0 ? 'rgba(255,170,0,0.1)' : 'transparent',
                  fontSize: 'var(--fs-meta)',
                  color: 'var(--color-warning)',
                  fontFamily: 'var(--font-mono)',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '0.15rem',
                  minWidth: '50px',
                  boxShadow: conflicts.length > 0 ? '0 0 10px rgba(255, 170, 0, 0.15)' : 'var(--shadow-sm)',
                  transition: 'border-color var(--transition-fast), box-shadow var(--transition-fast), background-color var(--transition-fast)',
                }}>
                  <span style={{ fontSize: 'var(--fs-micro)', opacity: 0.6, letterSpacing: '0.08em' }}>CNFLT</span>
                  <span style={{ fontWeight: 700, fontSize: 'var(--fs-body)' }}>{conflicts.length}</span>
                </div>
                <div style={{
                  padding: 'var(--sp-2) var(--sp-3)',
                  borderRadius: 'var(--radius-lg)',
                  border: emergencies.length > 0 ? '1px solid rgba(255, 51, 51, 0.4)' : '1px solid rgba(255, 51, 51, 0.2)',
                  backgroundColor: emergencies.length > 0 ? 'rgba(255,51,51,0.12)' : 'transparent',
                  fontSize: 'var(--fs-meta)',
                  color: 'var(--color-critical)',
                  fontFamily: 'var(--font-mono)',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '0.15rem',
                  minWidth: '50px',
                  boxShadow: emergencies.length > 0 ? '0 0 10px rgba(255, 51, 51, 0.2)' : 'var(--shadow-sm)',
                  transition: 'border-color var(--transition-fast), box-shadow var(--transition-fast), background-color var(--transition-fast)',
                }}>
                  <span style={{ fontSize: 'var(--fs-micro)', opacity: 0.6, letterSpacing: '0.08em' }}>EMG</span>
                  <span style={{ fontWeight: 700, fontSize: 'var(--fs-body)' }}>{emergencies.length}</span>
                </div>
              </div>

              {emergencies.length > 0 && (
                <div style={{ marginBottom: "var(--sp-3)" }}>
                  <div style={{
                    color: "var(--color-critical)",
                    fontWeight: 700,
                    fontSize: "var(--fs-body)",
                    marginBottom: "var(--sp-2)",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.4rem",
                  }}>
                    <span style={{
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      width: "16px",
                      height: "16px",
                      borderRadius: "var(--radius-sm)",
                      backgroundColor: "rgba(255, 51, 51, 0.2)",
                      fontSize: "0.6rem",
                    }}>⚠</span>
                    EMERGENCIES ({emergencies.length})
                  </div>
                  {emergencies.map((e) => (
                    <div
                      key={e.emergency_id}
                      style={{
                        borderLeft: "3px solid var(--color-critical)",
                        backgroundColor: "rgba(255, 51, 51, 0.05)",
                        padding: "var(--sp-2) var(--sp-3)",
                        marginBottom: "var(--sp-2)",
                        fontSize: "var(--fs-meta)",
                        borderRadius: "0 var(--radius-lg) var(--radius-lg) 0",
                        boxShadow: "var(--shadow-sm)",
                        transition: "box-shadow var(--transition-fast)",
                      }}
                    >
                      <div style={{ fontWeight: 700, color: "var(--color-critical)", marginBottom: "2px" }}>
                        SQ{e.squawk_code} — {e.callsign}
                      </div>
                      <div style={{ color: "var(--text-secondary)" }}>
                        Phase: <span style={{ color: "var(--color-critical)", fontWeight: 600 }}>{e.phase.toUpperCase()}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {conflicts.length > 0 && (
                <div>
                  <div style={{
                    color: "var(--color-warning)",
                    fontWeight: 700,
                    fontSize: "var(--fs-body)",
                    marginBottom: "var(--sp-2)",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.4rem",
                  }}>
                    <span style={{
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      width: "16px",
                      height: "16px",
                      borderRadius: "var(--radius-sm)",
                      backgroundColor: "rgba(255, 170, 0, 0.15)",
                      fontSize: "0.6rem",
                    }}>◆</span>
                    CONFLICTS ({conflicts.length})
                  </div>
                  {conflicts.map((c) => {
                    const isCritical = c.cpa.min_distance_nm < 3;
                    const severityColor = isCritical ? "var(--color-critical)" : "var(--color-warning)";
                    const severityLabel = isCritical ? "CRITICAL" : "CAUTION";
                    return (
                      <div
                        key={c.advisory_id}
                        style={{
                          borderLeft: `3px solid ${isCritical ? 'var(--color-critical)' : 'var(--color-warning)'}`,
                          backgroundColor: isCritical ? "rgba(255, 51, 51, 0.05)" : "rgba(255, 170, 0, 0.04)",
                          padding: "var(--sp-2) var(--sp-3)",
                          marginBottom: "var(--sp-2)",
                          fontSize: "var(--fs-meta)",
                          borderRadius: "0 var(--radius-lg) var(--radius-lg) 0",
                          boxShadow: "var(--shadow-sm)",
                          transition: "box-shadow var(--transition-fast)",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)", marginBottom: "4px" }}>
                          <span style={{
                            fontSize: "var(--fs-micro)",
                            fontWeight: 700,
                            color: severityColor,
                            padding: "2px var(--sp-2)",
                            borderRadius: "var(--radius-sm)",
                            border: `1px solid ${isCritical ? 'var(--color-critical)' : 'var(--color-warning)'}`,
                            backgroundColor: isCritical ? 'rgba(255,51,51,0.15)' : 'rgba(255,170,0,0.12)',
                            letterSpacing: "0.05em",
                          }}>
                            {severityLabel}
                          </span>
                          <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>
                            {c.cpa.aircraft_a_callsign} {" \u21C4 "} {c.cpa.aircraft_b_callsign}
                          </span>
                        </div>
                        <div style={{ color: "var(--text-dim)", display: "flex", gap: "var(--sp-3)" }}>
                          <span>CPA: <span style={{ color: "var(--text-secondary)" }}>{c.cpa.min_distance_nm}nm</span></span>
                          <span>Time: <span style={{ color: "var(--text-secondary)" }}>{c.cpa.time_to_cpa_seconds}s</span></span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {emergencies.length === 0 && conflicts.length === 0 && (
                <div style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  padding: "var(--sp-4) var(--sp-2)",
                  textAlign: "center",
                  gap: "0.3rem",
                }}>
                  <div style={{ fontSize: "1.2rem", opacity: 0.4 }}>✓</div>
                  <div style={{ fontSize: "var(--fs-meta)", color: "var(--text-dim)" }}>
                    All clear — no active conflicts or emergencies
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* ── Row 3, Col 1: Controller decisions ── */}
          <div style={{ overflow: "auto", borderRight: "1px solid var(--border-mid)" }}>
            <DecisionPanel />
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
