/** ATC Guardian — human-on-the-loop decision panel.

Polls pending controller decisions and renders APPROVE / REJECT / MODIFY
controls. Nothing an agent recommends is marked executed until the
controller acts here. This is the 'AI-assisted, human-decided' layer.
*/

import { useCallback, useEffect, useState } from "react";
import type { ControllerDecision, ResolveDecisionRequest } from "../lib/types";
import { SystemIcon } from "./AgentIcons";

/** HTTP base URL. In dev, Vite proxies to the backend. */
const HTTP_BASE_URL: string = import.meta.env.VITE_API_URL ?? "";

/** Poll interval for pending decisions (ms). */
const POLL_INTERVAL_MS = 3000;

/** Colour per advisory kind for the left accent. */
const KIND_COLORS: Record<string, string> = {
  conflict: "#ffaa00",
  weather: "#33ccff",
  emergency: "#ff3333",
  advisory: "#888888",
};

/** One-line label per advisory kind. */
const KIND_LABEL: Record<string, string> = {
  conflict: "CONFLICT",
  weather: "WEATHER",
  emergency: "EMERGENCY",
  advisory: "ADVISORY",
};

/** Format ISO timestamp to HH:MM:SS. */
function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  } catch {
    return "??:??:??";
  }
}

/** Convert a hex colour to rgba with alpha. */
function withAlpha(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** DecisionPanel — pending controller decisions with action controls. */
export function DecisionPanel(): React.ReactElement {
  const [pending, setPending] = useState<ControllerDecision[]>([]);
  const [recent, setRecent] = useState<{ id: string; action: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const fetchPending = useCallback(async (): Promise<void> => {
    try {
      const res = await fetch(`${HTTP_BASE_URL}/decisions/pending`);
      if (!res.ok) return;
      const data: ControllerDecision[] = await res.json();
      setPending(data);
    } catch {
      /* backend offline */
    }
  }, []);

  useEffect(() => {
    fetchPending();
    const timer = window.setInterval(fetchPending, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [fetchPending]);

  const resolve = useCallback(
    async (decisionId: string, body: ResolveDecisionRequest): Promise<void> => {
      setBusy(decisionId);
      try {
        const res = await fetch(
          `${HTTP_BASE_URL}/decisions/${decisionId}/resolve`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          },
        );
        if (res.ok) {
          setRecent({ id: decisionId, action: body.action });
          await fetchPending();
        }
      } catch {
        /* swallow — next poll will retry */
      } finally {
        setBusy(null);
      }
    },
    [fetchPending],
  );

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      height: "100%",
      backgroundColor: "var(--bg-deep)",
      fontFamily: "var(--font-mono)",
      overflow: "hidden",
    }}>
      <div className="atc-panel-header">
        <span className="atc-panel-title">CONTROLLER DECISIONS</span>
        <span style={{
          padding: '0.15rem 0.5rem',
          borderRadius: 'var(--radius-xl)',
          fontSize: 'var(--fs-micro)',
          fontWeight: 700,
          fontFamily: 'var(--font-mono)',
          backgroundColor: pending.length > 0 ? 'rgba(255, 170, 0, 0.15)' : 'rgba(51, 255, 51, 0.06)',
          color: pending.length > 0 ? '#ffaa00' : 'var(--color-nominal)',
          border: pending.length > 0 ? '1px solid rgba(255, 170, 0, 0.35)' : '1px solid rgba(51, 255, 51, 0.2)',
          letterSpacing: '0.04em',
          boxShadow: pending.length > 0 ? '0 0 8px rgba(255, 170, 0, 0.15)' : 'none',
          transition: 'all var(--transition-fast)',
        }}>
          {pending.length} PENDING
        </span>
      </div>
      <div style={{
        overflowY: "auto",
        padding: "var(--sp-2) var(--sp-3)",
      }}>
        {pending.length === 0 && (
          <div className="atc-empty-state">
            <div className="atc-empty-state-icon">
              <SystemIcon type="check" size={28} color="var(--accent-green)" />
            </div>
            <div className="atc-empty-state-title">
              {recent
                ? `Last action: ${recent.action} (${recent.id.slice(-6)})`
                : 'No pending decisions'}
            </div>
            <div className="atc-empty-state-desc">
              Agent proposals requiring controller authority will appear here for your review.
            </div>
          </div>
        )}
        {pending.map((d) => {
          const accent = KIND_COLORS[d.advisory_kind] ?? "#888";
          const isBusy = busy === d.decision_id;
          return (
            <div
              key={d.decision_id}
              style={{
                borderLeft: `3px solid ${accent}`,
                borderRadius: '0 var(--radius-lg) var(--radius-lg) 0',
                backgroundColor: withAlpha(accent, 0.04),
                padding: "0.55rem",
                marginBottom: "0.5rem",
                fontSize: "0.62rem",
                fontFamily: 'var(--font-mono)',
                boxShadow: 'var(--shadow-sm)',
                transition: 'box-shadow var(--transition-fast), background-color var(--transition-fast)',
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: 'center', marginBottom: "0.35rem" }}>
                <span style={{
                  padding: '0.1rem 0.45rem',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '0.5rem',
                  fontWeight: 700,
                  backgroundColor: withAlpha(accent, 0.15),
                  color: accent,
                  border: `1px solid ${withAlpha(accent, 0.35)}`,
                  letterSpacing: '0.04em',
                }}>
                  {KIND_LABEL[d.advisory_kind] ?? d.advisory_kind.toUpperCase()}
                </span>
                <span style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-micro)' }}>{formatTime(d.created_at)}</span>
              </div>
              <div style={{
                color: 'var(--text-primary)',
                marginBottom: "0.4rem",
                lineHeight: 1.55,
                fontWeight: 500,
              }}>{d.summary}</div>
              <div style={{
                color: 'var(--text-secondary)',
                marginBottom: "0.25rem",
                padding: "0.25rem 0.4rem",
                backgroundColor: "rgba(68, 136, 255, 0.06)",
                borderRadius: "var(--radius-md)",
                borderLeft: "2px solid var(--accent-blue)",
              }}>
                <span style={{ color: 'var(--accent-blue)', fontWeight: 600, fontSize: 'var(--fs-micro)' }}>AGENT:</span>{" "}
                {d.agent_recommendation}
              </div>
              <div style={{
                color: 'var(--text-secondary)',
                marginBottom: "0.4rem",
                padding: "0.25rem 0.4rem",
                backgroundColor: "rgba(51, 255, 51, 0.04)",
                borderRadius: "var(--radius-md)",
                borderLeft: "2px solid var(--color-nominal)",
              }}>
                <span style={{ color: 'var(--color-nominal)', fontWeight: 600, fontSize: 'var(--fs-micro)' }}>REVIEWER:</span>{" "}
                {d.reviewer_verdict}
              </div>
              <div style={{ display: "flex", gap: "0.3rem" }}>
                <button
                  type="button"
                  disabled={isBusy}
                  onClick={() => resolve(d.decision_id, { action: "APPROVED" })}
                  style={btnStyle("#0a1a0a", "#33ff33")}
                >
                  {isBusy ? "..." : "APPROVE"}
                </button>
                <button
                  type="button"
                  disabled={isBusy}
                  onClick={() => resolve(d.decision_id, { action: "MODIFIED" })}
                  style={btnStyle("#1a1a0a", "#ffaa00")}
                >
                  {isBusy ? "..." : "MODIFY"}
                </button>
                <button
                  type="button"
                  disabled={isBusy}
                  onClick={() => resolve(d.decision_id, { action: "REJECTED" })}
                  style={btnStyle("#1a0a0a", "#ff3333")}
                >
                  {isBusy ? "..." : "REJECT"}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Build a button style with the given bg/text colours. */
function btnStyle(bg: string, color: string): React.CSSProperties {
  return {
    flex: 1,
    backgroundColor: bg,
    color,
    border: `1px solid ${color}`,
    borderRadius: 'var(--radius-md)',
    padding: "0.3rem 0.4rem",
    fontSize: "0.58rem",
    fontFamily: "var(--font-mono)",
    fontWeight: 700,
    cursor: "pointer",
    letterSpacing: "0.06em",
    transition: 'all var(--transition-fast)',
    boxShadow: 'var(--shadow-sm)',
  };
}
