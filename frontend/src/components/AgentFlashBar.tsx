/** ATC Guardian — agent flash indicator bar.
 *
 * Renders 6 small pill chips in the header — one per agent — that flash
 * brightly when that agent sends a new message, then decay over 2 seconds.
 * Clicking a chip filters Agent Comms to that agent AND navigates to
 * the agent detail page (via onNavigate callback).
 *
 * Intensity decay uses requestAnimationFrame for smooth 60fps animation.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useAtcStore } from "../stores/atcStore";
import { AgentIcon, AGENT_HANDLES, AGENT_COLORS } from "./AgentIcons";

interface AgentFlashBarProps {
  /** Called when user clicks a flash chip (navigates to detail page). */
  onNavigate?: () => void;
}

/** Per-agent flash intensity (0–1). Decays from 1→0 over 2 seconds. */
function useFlashIntensities(): Record<string, number> {
  const lastReplyAgent = useAtcStore((s) => s.lastReplyAgent);
  const lastReplyTick = useAtcStore((s) => s.lastReplyTick);
  const intensities = useRef<Record<string, number>>({});
  const [renderTick, setRenderTick] = useState(0);

  // When a new reply arrives, set that agent's intensity to 1
  useEffect(() => {
    if (lastReplyAgent) {
      intensities.current[lastReplyAgent] = 1;
    }
  }, [lastReplyAgent, lastReplyTick]);

  // rAF loop: decay all intensities towards 0 over 2 seconds
  useEffect(() => {
    let rafId: number;
    let lastTime = performance.now();

    const tick = (now: number) => {
      const dt = (now - lastTime) / 1000;
      lastTime = now;
      let dirty = false;

      for (const handle of Object.keys(intensities.current)) {
        const v = intensities.current[handle];
        if (v > 0) {
          intensities.current[handle] = Math.max(0, v - dt * 0.5); // 0.5 = 1/2s rate → 2s full decay
          dirty = true;
        }
      }

      if (dirty) {
        setRenderTick((t) => t + 1);
      }

      rafId = requestAnimationFrame(tick);
    };

    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, []);

  // Build snapshot for render
  const snap: Record<string, number> = {};
  for (const h of AGENT_HANDLES) {
    snap[h] = intensities.current[h] ?? 0;
  }
  return snap;
}

export function AgentFlashBar({ onNavigate }: AgentFlashBarProps): React.ReactElement {
  const intensities = useFlashIntensities();
  const chatFilterAgent = useAtcStore((s) => s.chatFilterAgent);
  const setChatFilterAgent = useAtcStore((s) => s.setChatFilterAgent);
  const setSelectedAgentHandle = useAtcStore((s) => s.setSelectedAgentHandle);

  const handleClick = useCallback(
    (handle: string) => {
      // Toggle: clicking same agent clears filter, otherwise set it
      setChatFilterAgent(chatFilterAgent === handle ? null : handle);
      setSelectedAgentHandle(handle);
      onNavigate?.();
    },
    [chatFilterAgent, setChatFilterAgent, setSelectedAgentHandle, onNavigate],
  );

  return (
    <div className="agent-flash-bar">
      {AGENT_HANDLES.map((handle) => {
        const intensity = intensities[handle] ?? 0;
        const color = AGENT_COLORS[handle];
        const isFiltered = chatFilterAgent === handle;

        return (
          <button
            key={handle}
            className={`agent-flash-chip${isFiltered ? " agent-flash-chip--active" : ""}`}
            onClick={() => handleClick(handle)}
            style={{
              borderColor: isFiltered
                ? color
                : intensity > 0.1
                  ? color
                  : undefined,
              boxShadow: intensity > 0.1
                ? `0 0 ${Math.round(intensity * 12)}px ${color.replace("#", "rgba(").replace(/([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})/i, (_, r, g, b) => `${parseInt(r, 16)},${parseInt(g, 16)},${parseInt(b, 16)},${intensity * 0.5})`)}`
                : undefined,
            }}
          >
            <AgentIcon handle={handle} size={10} color={intensity > 0.1 ? color : "#888"} />
            <span style={{ color: intensity > 0.3 ? color : "var(--text-muted)", fontWeight: intensity > 0.3 ? 600 : 400 }}>
              {handle.split("-").map((w) => w[0]).join("").toUpperCase().slice(0, 3)}
            </span>
          </button>
        );
      })}
    </div>
  );
}
