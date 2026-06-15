/** ATC Guardian — human-on-the-loop decision panel.

Polls pending controller decisions and renders APPROVE / REJECT / MODIFY
controls. Nothing an agent recommends is marked executed until the
controller acts here. This is the 'AI-assisted, human-decided' layer.
*/

import { useCallback, useEffect, useState } from "react";
import type { ControllerDecision, ResolveDecisionRequest } from "../lib/types";

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

  const panelStyle: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    maxHeight: "38%",
    backgroundColor: "#0a0a0a",
    overflow: "hidden",
    borderBottom: "1px solid #1a3a1a",
  };

  const headerStyle: React.CSSProperties = {
    fontSize: "0.7rem",
    color: "#33ff33",
    padding: "0.3rem 0.5rem",
    borderBottom: "1px solid #1a3a1a",
    flexShrink: 0,
    letterSpacing: "0.05em",
    display: "flex",
    justifyContent: "space-between",
  };

  const listStyle: React.CSSProperties = {
    overflowY: "auto",
    padding: "0.25rem 0.5rem",
  };

  return (
    <div style={panelStyle}>
      <div style={headerStyle}>
        <span>CONTROLLER DECISIONS</span>
        <span style={{ color: pending.length > 0 ? "#ffaa00" : "#555" }}>
          {pending.length} PENDING
        </span>
      </div>
      <div style={listStyle}>
        {pending.length === 0 && (
          <div style={{ fontSize: "0.6rem", color: "#555", padding: "0.3rem" }}>
            {recent
              ? `Last: ${recent.action} (${recent.id.slice(-6)})`
              : "No pending decisions. Agents will surface proposals here."}
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
                backgroundColor: "#111",
                padding: "0.3rem",
                marginBottom: "0.25rem",
                fontSize: "0.62rem",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: accent, fontWeight: "bold" }}>
                  {KIND_LABEL[d.advisory_kind] ?? d.advisory_kind.toUpperCase()}
                </span>
                <span style={{ color: "#555" }}>{formatTime(d.created_at)}</span>
              </div>
              <div style={{ color: "#ccc", margin: "0.15rem 0" }}>{d.summary}</div>
              <div style={{ color: "#888", marginBottom: "0.1rem" }}>
                <span style={{ color: "#4488ff" }}>Agent:</span>{" "}
                {d.agent_recommendation}
              </div>
              <div style={{ color: "#888", marginBottom: "0.2rem" }}>
                <span style={{ color: "#33ff33" }}>Reviewer:</span>{" "}
                {d.reviewer_verdict}
              </div>
              <div style={{ display: "flex", gap: "0.25rem" }}>
                <button
                  type="button"
                  disabled={isBusy}
                  onClick={() => resolve(d.decision_id, { action: "APPROVED" })}
                  style={btnStyle("#1a3a1a", "#33ff33")}
                >
                  APPROVE
                </button>
                <button
                  type="button"
                  disabled={isBusy}
                  onClick={() => resolve(d.decision_id, { action: "MODIFIED" })}
                  style={btnStyle("#3a3a1a", "#ffaa00")}
                >
                  MODIFY
                </button>
                <button
                  type="button"
                  disabled={isBusy}
                  onClick={() => resolve(d.decision_id, { action: "REJECTED" })}
                  style={btnStyle("#3a1a1a", "#ff3333")}
                >
                  REJECT
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
    padding: "0.2rem",
    fontSize: "0.6rem",
    fontFamily: "monospace",
    cursor: "pointer",
    letterSpacing: "0.05em",
  };
}
