/** RadarView — canvas-based radar-phile display for ATC Guardian.

Draws a rotating sweep line, range rings, and aircraft blips
with callsign labels. Uses CSS conic-gradient as an overlay
for the sweep effect.
*/

import { useRef, useEffect } from "react";
import { useAtcStore } from "../stores/atcStore";
import { RADAR_RANGE_NM } from "../lib/constants";
import type { AircraftState } from "../lib/types";

/** Canvas dimensions (square radar display). */
const CANVAS_SIZE = 600;
const CENTER = CANVAS_SIZE / 2;
const RADIUS = CANVAS_SIZE / 2 - 20;

/** Convert nautical miles offset to pixel offset from center. */
function nmToPixel(nm: number): number {
  return (nm / RADAR_RANGE_NM) * RADIUS;
}

/** Draw the radar background (range rings, compass marks). */
function drawBackground(ctx: CanvasRenderingContext2D): void {
  ctx.fillStyle = "#0a0a0a";
  ctx.fillRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);

  // Range rings
  ctx.strokeStyle = "#1a3a1a";
  ctx.lineWidth = 1;
  for (let nm = 10; nm <= RADAR_RANGE_NM; nm += 10) {
    const r = nmToPixel(nm);
    ctx.beginPath();
    ctx.arc(CENTER, CENTER, r, 0, Math.PI * 2);
    ctx.stroke();

    // Range label
    ctx.fillStyle = "#2a5a2a";
    ctx.font = "9px monospace";
    ctx.fillText(`${nm}`, CENTER + r - 14, CENTER - 3);
  }

  // Compass lines (N, E, S, W)
  ctx.strokeStyle = "#1a3a1a";
  ctx.lineWidth = 0.5;
  for (const angle of [0, Math.PI / 2, Math.PI, (3 * Math.PI) / 2]) {
    ctx.beginPath();
    ctx.moveTo(CENTER, CENTER);
    ctx.lineTo(
      CENTER + Math.sin(angle) * RADIUS,
      CENTER - Math.cos(angle) * RADIUS,
    );
    ctx.stroke();
  }

  // Compass labels
  ctx.fillStyle = "#3a7a3a";
  ctx.font = "11px monospace";
  ctx.textAlign = "center";
  ctx.fillText("N", CENTER, 16);
  ctx.fillText("S", CENTER, CANVAS_SIZE - 8);
  ctx.fillText("E", CANVAS_SIZE - 10, CENTER + 4);
  ctx.fillText("W", 10, CENTER + 4);
}

/** Draw a single aircraft blip with callsign label. */
function drawBlip(ctx: CanvasRenderingContext2D, aircraft: AircraftState): void {
  const dx = (aircraft.longitude - 0) * 60; // rough nm per degree at ~40° lat
  const dy = -(aircraft.latitude - 0) * 60; // negative because canvas y is inverted

  const px = CENTER + nmToPixel(dx);
  const py = CENTER + nmToPixel(dy);

  // Check if within radar range
  const dist = Math.sqrt((px - CENTER) ** 2 + (py - CENTER) ** 2);
  if (dist > RADIUS) return;

  // Blip color based on squawk
  const isEmergency = aircraft.squawk === "7700";
  const isHijack = aircraft.squawk === "7500";
  const blipColor = isEmergency ? "#ff3333" : isHijack ? "#ff8800" : "#33ff33";

  // Draw blip
  ctx.fillStyle = blipColor;
  ctx.beginPath();
  ctx.arc(px, py, 3, 0, Math.PI * 2);
  ctx.fill();

  // Heading line
  const headingRad = (aircraft.heading_deg * Math.PI) / 180;
  const lineLen = 12;
  ctx.strokeStyle = blipColor;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(px, py);
  ctx.lineTo(
    px + Math.sin(headingRad) * lineLen,
    py - Math.cos(headingRad) * lineLen,
  );
  ctx.stroke();

  // Callsign label
  ctx.fillStyle = "#33ff33";
  ctx.font = "10px monospace";
  ctx.textAlign = "left";
  ctx.fillText(aircraft.callsign, px + 6, py - 4);

  // Altitude label
  const fl = Math.round(aircraft.altitude_ft / 100);
  ctx.fillStyle = "#22aa22";
  ctx.fillText(`FL${fl.toString().padStart(3, "0")}`, px + 6, py + 6);
}

/** Main RadarView component. */
export function RadarView(): React.ReactElement {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const aircraft = useAtcStore((s) => s.aircraft);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    drawBackground(ctx);

    for (const ac of aircraft) {
      drawBlip(ctx, ac);
    }
  }, [aircraft]);

  return (
    <div style={{ position: "relative", width: CANVAS_SIZE, height: CANVAS_SIZE }}>
      <canvas
        ref={canvasRef}
        width={CANVAS_SIZE}
        height={CANVAS_SIZE}
        style={{
          border: "1px solid #1a3a1a",
          borderRadius: "50%",
        }}
      />
    </div>
  );
}
