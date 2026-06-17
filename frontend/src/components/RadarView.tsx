/** RadarView — Leaflet-based ATC radar display for ATC Guardian.

Displays aircraft as colored dot markers on a dark map with
heading lines, hover tooltips, conflict lines, range rings with
labels, emergency blinking, selected-aircraft highlighting, and
a rotating radar-sweep overlay. Uses CartoDB dark tiles for the
authentic ATC radar aesthetic.
*/

import { Fragment, useEffect, useMemo, useCallback, useRef } from "react";
import L from "leaflet";
import {
  MapContainer,
  TileLayer,
  Marker,
  Polyline,
  Polygon,
  Circle,
  Tooltip,
  useMap,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { useAtcStore } from "../stores/atcStore";
import type { AircraftState, ConflictAdvisory, WeatherAdvisory } from "../lib/types";
import {
  COLOR_NORMAL,
  COLOR_7700,
  COLOR_7500,
  COLOR_7600,
  COLOR_CONFLICT_CAUTION,
  COLOR_CONFLICT_CRITICAL,
  COLOR_RANGE_RING,
  COLOR_RANGE_RING_LABEL,
  COLOR_SELECTED_RING,
  BLINK_INTERVAL_7700_MS,
  BLINK_INTERVAL_7500_MS,
  BLINK_INTERVAL_7600_MS,
  HEADING_PROJECTION_NM,
  RADAR_SWEEP_DURATION_SECONDS,
  SWEEP_GRADIENT_OPACITY,
  SWEEP_GRADIENT_ANGLE_DEG,
} from "../lib/constants";

/** Meters per nautical mile. */
const METERS_PER_NM = 1852;

/** Earth radius in nautical miles. */
const EARTH_RADIUS_NM = 3440.065;

/** Range ring radii in nautical miles. */
const RANGE_RINGS_NM = [10, 20, 30, 40, 50, 60];

/** Map of squawk codes to their display colors. */
const SQUAWK_COLORS: Record<string, string> = {
  "7700": COLOR_7700,
  "7500": COLOR_7500,
  "7600": COLOR_7600,
};



// ─── Helpers ────────────────────────────────────────────────────────

/** Get blip color based on squawk code. */
function getBlipColor(aircraft: AircraftState): string {
  return SQUAWK_COLORS[aircraft.squawk] ?? COLOR_NORMAL;
}

/** Whether the squawk code is an emergency code. */
function isEmergency(squawk: string): boolean {
  return squawk in SQUAWK_COLORS;
}

/** Compute the endpoint of a heading line using great-circle math. */
function computeHeadingEndpoint(
  lat: number,
  lng: number,
  headingDeg: number,
  distanceNm: number,
): [number, number] {
  const d = distanceNm / EARTH_RADIUS_NM;
  const brng = (headingDeg * Math.PI) / 180;
  const lat1 = (lat * Math.PI) / 180;
  const lon1 = (lng * Math.PI) / 180;

  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(d) +
      Math.cos(lat1) * Math.sin(d) * Math.cos(brng),
  );
  const lon2 =
    lon1 +
    Math.atan2(
      Math.sin(brng) * Math.sin(d) * Math.cos(lat1),
      Math.cos(d) - Math.sin(lat1) * Math.sin(lat2),
    );

  return [(lat2 * 180) / Math.PI, (lon2 * 180) / Math.PI];
}

/** Format vertical speed with climb/descent indicator. */
function formatVerticalSpeed(fpm: number): string {
  if (fpm > 0) return `\u2191${fpm}`;
  if (fpm < 0) return `\u2193${Math.abs(fpm)}`;
  return "";
}

// ─── Icon Factories ─────────────────────────────────────────────────

/** Create a heading-rotated aircraft silhouette marker using L.divIcon. */
function createAircraftIcon(color: string, headingDeg: number, size: number = 14): L.DivIcon {
  return L.divIcon({
    className: "",
    html: `<div style="
      width:${size}px;
      height:${size}px;
      display:flex;
      align-items:center;
      justify-content:center;
      filter: drop-shadow(0 0 4px ${color}88) drop-shadow(0 0 8px ${color}44);
    "><svg width="${size}" height="${size}" viewBox="0 0 24 24" style="
      transform:rotate(${headingDeg}deg);
    "><path d="M12 2 L14 8 L20 10 L14 12 L14 18 L17 20 L17 21 L12 19 L7 21 L7 20 L10 18 L10 12 L4 10 L10 8 Z" fill="${color}" opacity="0.95" stroke="${color}" stroke-width="0.3"/></svg></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

/** Create a selected-aircraft icon with a heading-rotated plane and selection ring. */
function createSelectedIcon(color: string, headingDeg: number, size: number = 18): L.DivIcon {
  const ringSize = size + 10;
  return L.divIcon({
    className: "",
    html: `<div style="
      width:${ringSize}px;
      height:${ringSize}px;
      display:flex;
      align-items:center;
      justify-content:center;
      position:relative;
    "><div style="
      width:${ringSize}px;
      height:${ringSize}px;
      border:2px solid ${COLOR_SELECTED_RING};
      border-radius:50%;
      position:absolute;
      top:0;left:0;
      box-shadow:0 0 10px ${COLOR_SELECTED_RING}66;
    "></div><svg width="${size}" height="${size}" viewBox="0 0 24 24" style="
      transform:rotate(${headingDeg}deg);
      position:relative;
      z-index:1;
      filter: drop-shadow(0 0 6px ${color}aa) drop-shadow(0 0 10px ${color}66);
    "><path d="M12 2 L14 8 L20 10 L14 12 L14 18 L17 20 L17 21 L12 19 L7 21 L7 20 L10 18 L10 12 L4 10 L10 8 Z" fill="${color}" opacity="0.95" stroke="${color}" stroke-width="0.3"/></svg></div>`,
    iconSize: [ringSize, ringSize],
    iconAnchor: [ringSize / 2, ringSize / 2],
  });
}

/** Compute arrowhead polygon points for a heading line tip.
 *  Returns 3 [lat,lng] coordinates forming a triangle with the tip at
 *  the heading line endpoint, pointing in the heading direction. */
function computeArrowheadPoints(
  tipLat: number,
  tipLng: number,
  headingDeg: number,
  lengthNm: number = 0.5,
  halfWidthNm: number = 0.25,
): [number, number][] {
  const brng = headingDeg * Math.PI / 180;
  const cosLat = Math.cos(tipLat * Math.PI / 180);

  // Base center: 'lengthNm' behind the tip along the heading
  const backLat = tipLat - (lengthNm / EARTH_RADIUS_NM) * Math.cos(brng) * (180 / Math.PI);
  const backLng = tipLng - (lengthNm / EARTH_RADIUS_NM) * Math.sin(brng) / cosLat * (180 / Math.PI);

  // Perpendicular direction for the base wings
  const perp = brng + Math.PI / 2;
  const dLat = (halfWidthNm / EARTH_RADIUS_NM) * Math.cos(perp) * (180 / Math.PI);
  const dLng = (halfWidthNm / EARTH_RADIUS_NM) * Math.sin(perp) / cosLat * (180 / Math.PI);

  return [
    [tipLat, tipLng],
    [backLat + dLat, backLng + dLng],
    [backLat - dLat, backLng - dLng],
  ];
}

/** Create a range-ring distance label at the 12-o'clock position. */
function createRangeRingLabel(nm: number): L.DivIcon {
  return L.divIcon({
    className: "",
    html: `<div style="
      font-family:var(--font-mono);
      font-size:10px;
      color:${COLOR_RANGE_RING_LABEL};
      white-space:nowrap;
      text-shadow:0 0 4px #000;
      pointer-events:none;
    ">${nm}nm</div>`,
    iconSize: [40, 14],
    iconAnchor: [20, 7],
  });
}

// ─── CSS Keyframes Injection ────────────────────────────────────────

/** Inject CSS keyframe animations for emergency blinking on mount. */
function useEmergencyBlinkStyles(): void {
  useEffect(() => {
    const styleId = "atc-guardian-emergency-blink";
    // Avoid duplicate injection
    if (document.getElementById(styleId)) return;

    const style = document.createElement("style");
    style.id = styleId;
    style.textContent = `
      @keyframes blink-7700 {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.15; }
      }
      @keyframes blink-7500 {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.2; }
      }
      @keyframes blink-7600 {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.25; }
      }
      @keyframes pulse-hazard {
        0%, 100% { opacity: 0.35; }
        50% { opacity: 0.12; }
      }
      .atc-blink-7700 {
        animation: blink-7700 ${BLINK_INTERVAL_7700_MS}ms ease-in-out infinite;
      }
      .atc-blink-7500 {
        animation: blink-7500 ${BLINK_INTERVAL_7500_MS}ms ease-in-out infinite;
      }
      .atc-blink-7600 {
        animation: blink-7600 ${BLINK_INTERVAL_7600_MS}ms ease-in-out infinite;
      }
      .atc-weather-pulse {
        animation: pulse-hazard 3s ease-in-out infinite;
      }
    `;
    document.head.appendChild(style);

    return () => {
      document.getElementById(styleId)?.remove();
    };
  }, []);
}

// ─── Leaflet Map Sub-Components ─────────────────────────────────────

/** Component that updates the map center only on scenario change.

User pan/zoom is preserved between ticks — the map is only reset
when the active scenario ID changes (e.g. the user picks a new
scenario from the dropdown). Routine snapshot updates that carry
the same center coordinates must NOT call setView, otherwise the
user's manual zoom/pan would be overwritten every 4 s.
*/
function MapCenterUpdater({
  center,
  zoom,
  scenarioId,
  prevScenarioIdRef,
}: {
  center: [number, number];
  zoom: number;
  scenarioId: string;
  prevScenarioIdRef: React.MutableRefObject<string>;
}): null {
  const map = useMap();

  useEffect(() => {
    if (prevScenarioIdRef.current !== scenarioId) {
      prevScenarioIdRef.current = scenarioId;
      map.setView(center, zoom, { animate: true, duration: 1.0 });
    }
  }, [map, center, zoom, scenarioId, prevScenarioIdRef]);

  return null;
}

/** Range ring labels positioned at the 12-o'clock position of each ring. */
function RangeRingLabels({
  center,
}: {
  center: [number, number];
}): React.ReactElement {
  return (
    <>
      {RANGE_RINGS_NM.map((nm) => {
        // Position at 12 o'clock (north) on the ring
        const latOffset = nm / EARTH_RADIUS_NM;
        const labelLat = center[0] + (latOffset * 180) / Math.PI;
        return (
          <Marker
            key={`ring-label-${nm}`}
            position={[labelLat, center[1]]}
            icon={createRangeRingLabel(nm)}
            interactive={false}
          />
        );
      })}
    </>
  );
}

/** Conflict lines drawn between pairs of conflicting aircraft. */
function ConflictLines({
  conflicts,
  aircraftMap,
}: {
  conflicts: ConflictAdvisory[];
  aircraftMap: Map<string, AircraftState>;
}): React.ReactElement | null {
  if (conflicts.length === 0) return null;

  return (
    <>
      {conflicts.map((conflict) => {
        const acA = aircraftMap.get(conflict.cpa.aircraft_a_callsign);
        const acB = aircraftMap.get(conflict.cpa.aircraft_b_callsign);
        if (!acA || !acB) return null;

        const isCritical = conflict.severity === "critical";
        const color = isCritical
          ? COLOR_CONFLICT_CRITICAL
          : COLOR_CONFLICT_CAUTION;
        const weight = isCritical ? 2.5 : 1.5;

        // Predicted CPA zone — a marker at the midpoint showing where the
        // closest approach is forecast, radius scaled by the CPA distance.
        const midLat = (acA.latitude + acB.latitude) / 2;
        const midLon = (acA.longitude + acB.longitude) / 2;
        const cpaRadiusM = Math.max(conflict.cpa.min_distance_nm, 1) * 1852;

        return (
          <Fragment key={conflict.advisory_id}>
            <Polyline
              positions={[
                [acA.latitude, acA.longitude],
                [acB.latitude, acB.longitude],
              ]}
              pathOptions={{
                color,
                weight,
                opacity: 0.8,
                dashArray: "6, 4",
              }}
            />
            <Circle
              center={[midLat, midLon]}
              radius={cpaRadiusM}
              pathOptions={{
                color,
                weight: 1,
                opacity: 0.5,
                fillOpacity: 0.12,
                dashArray: "3, 6",
              }}
            >
              <Tooltip sticky>
                CPA {conflict.cpa.min_distance_nm} nm in{" "}
                {Math.round(conflict.cpa.time_to_cpa_seconds)}s ({conflict.severity})
              </Tooltip>
            </Circle>
          </Fragment>
        );
      })}
    </>
  );
}

// ─── Individual Aircraft Marker ─────────────────────────────────────

/** Single aircraft marker with heading line, arrowhead, and tooltips. */
function AircraftMarker({
  aircraft,
  isSelected,
  onSelect,
}: {
  aircraft: AircraftState;
  isSelected: boolean;
  onSelect: (callsign: string) => void;
}): React.ReactElement {
  const color = getBlipColor(aircraft);
  const position: [number, number] = [aircraft.latitude, aircraft.longitude];
  const headingEnd = computeHeadingEndpoint(
    aircraft.latitude,
    aircraft.longitude,
    aircraft.heading_deg,
    HEADING_PROJECTION_NM,
  );
  const emergency = isEmergency(aircraft.squawk);
  const blinkClass = emergency
    ? `atc-blink-${aircraft.squawk}`
    : "";

  const fl = Math.round(aircraft.altitude_ft / 100)
    .toString()
    .padStart(3, "0");
  const hdg = Math.round(aircraft.heading_deg)
    .toString()
    .padStart(3, "0");
  const gs = Math.round(aircraft.speed_kts);
  const vs = formatVerticalSpeed(aircraft.vertical_speed_fpm);
  const isNonStandardSquawk = !["1200", "2000", "0000"].includes(
    aircraft.squawk,
  );

  const icon = isSelected
    ? createSelectedIcon(color, aircraft.heading_deg, 18)
    : createAircraftIcon(color, aircraft.heading_deg, 14);

  const handleClick = useCallback(() => {
    onSelect(aircraft.callsign);
  }, [aircraft.callsign, onSelect]);

  return (
    <>
      {/* Aircraft dot marker */}
      <Marker
        position={position}
        icon={icon}
        eventHandlers={{ click: handleClick }}
      >
        {/* Emergency aircraft: always show callsign label */}
        {emergency && (
          <Tooltip
            direction="right"
            offset={[12, 0]}
            permanent
            className={blinkClass}
          >
            <div
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "11px",
                color,
                background: "rgba(0,0,0,0.75)",
                border: `1px solid ${color}44`,
                borderRadius: "2px",
                padding: "2px 5px",
                whiteSpace: "nowrap",
              }}
            >
              {aircraft.callsign}
            </div>
          </Tooltip>
        )}

        {/* Hover tooltip (all aircraft) */}
        <Tooltip direction="right" offset={[12, 0]} className={blinkClass}>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "11px",
              background: "rgba(0,0,0,0.85)",
              border: `1px solid ${color}55`,
              borderRadius: "3px",
              padding: "6px 8px",
              color: "#ccc",
              lineHeight: "1.5",
              whiteSpace: "nowrap",
            }}
          >
            {/* Callsign */}
            <div
              style={{
                fontWeight: "bold",
                color,
                fontSize: "12px",
                marginBottom: "2px",
              }}
            >
              {aircraft.callsign}
            </div>
            {/* Flight level */}
            <div>
              FL{fl}
              <span style={{ marginLeft: 8, color: "#999" }}>
                {hdg}&deg;
              </span>
              <span style={{ marginLeft: 8, color: "#999" }}>
                {gs} kt
              </span>
            </div>
            {/* Vertical speed */}
            {vs && (
              <div style={{ color: aircraft.vertical_speed_fpm > 0 ? "#66cc66" : "#cc6666" }}>
                VS {vs} fpm
              </div>
            )}
            {/* Squawk */}
            <div>
              <span
                style={{
                  color: isNonStandardSquawk ? "#ffcc00" : "#888",
                  background: isNonStandardSquawk
                    ? "rgba(255,204,0,0.12)"
                    : "transparent",
                  padding: "0 3px",
                  borderRadius: "2px",
                }}
              >
                SQ {aircraft.squawk}
              </span>
            </div>
            {/* Category */}
            <div style={{ color: "#666", fontSize: "10px" }}>
              Cat {aircraft.category}
            </div>
          </div>
        </Tooltip>
      </Marker>

      {/* Heading projection line */}
      <Polyline
        positions={[position, headingEnd]}
        pathOptions={{
          color,
          weight: 1.5,
          opacity: 0.7,
          dashArray: "4, 4",
          className: blinkClass,
        }}
      />

      {/* Arrowhead at heading line tip — Polygon for precise alignment */}
      <Polygon
        positions={computeArrowheadPoints(headingEnd[0], headingEnd[1], aircraft.heading_deg)}
        pathOptions={{
          color: "transparent",
          fillColor: color,
          fillOpacity: 0.8,
          weight: 0,
          interactive: false,
          className: blinkClass,
        }}
      />

      {/* 7700 danger circle */}
      {aircraft.squawk === "7700" && (
        <Circle
          center={position}
          radius={5 * METERS_PER_NM}
          pathOptions={{
            color: COLOR_7700,
            weight: 1.5,
            fill: false,
            dashArray: "3, 6",
          }}
        />
      )}
    </>
  );
}

// ─── Radar Sweep Overlay ────────────────────────────────────────────

/** Absolutely-positioned rotating radar sweep overlay. */
function RadarSweepOverlay(_props: {
  center: [number, number];
}): React.ReactElement | null {
  const map = useMap();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const animFrameRef = useRef<number | null>(null);

  useEffect(() => {
    const mapContainer = map.getContainer();

    // Create the overlay div
    const overlay = document.createElement("div");
    overlay.style.cssText = `
      position: absolute;
      top: 0; left: 0; right: 0; bottom: 0;
      pointer-events: none;
      z-index: 450;
      overflow: hidden;
    `;

    // Inner rotating element
    const sweep = document.createElement("div");
    sweep.style.cssText = `
      position: absolute;
      width: 200%;
      height: 200%;
      top: -50%;
      left: -50%;
      background: conic-gradient(
        from 0deg,
        rgba(51, 255, 51, ${SWEEP_GRADIENT_OPACITY}),
        transparent ${SWEEP_GRADIENT_ANGLE_DEG}deg,
        transparent 360deg
      );
      animation: atc-sweep-rotate ${RADAR_SWEEP_DURATION_SECONDS}s linear infinite;
      pointer-events: none;
    `;

    // Inject the rotation keyframe if not already present
    const sweepStyleId = "atc-sweep-rotate-style";
    if (!document.getElementById(sweepStyleId)) {
      const style = document.createElement("style");
      style.id = sweepStyleId;
      style.textContent = `
        @keyframes atc-sweep-rotate {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `;
      document.head.appendChild(style);
    }

    overlay.appendChild(sweep);
    mapContainer.appendChild(overlay);
    containerRef.current = overlay;

    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      overlay.remove();
    };
  }, [map]);

  return null;
}

// ─── Weather Hazard Overlay ─────────────────────────────────────────

/** Render pulsing weather hazard circles around affected aircraft. */
function WeatherHazardOverlay({
  weatherAdvisories,
  aircraftMap,
}: {
  weatherAdvisories: WeatherAdvisory[];
  aircraftMap: Map<string, AircraftState>;
}): React.ReactElement | null {
  if (weatherAdvisories.length === 0) return null;

  return (
    <>
      {weatherAdvisories.map((advisory) => {
        // Find the first affected aircraft that exists in the map
        const affectedAc = advisory.affected_callsigns
          .map((cs) => aircraftMap.get(cs))
          .find((ac): ac is AircraftState => ac !== undefined);
        if (!affectedAc) return null;

        const hazardColor = advisory.severity === "critical" ? "#ff3333" : "#ffaa00";

        return (
          <Circle
            key={advisory.advisory_id}
            center={[affectedAc.latitude, affectedAc.longitude]}
            radius={8 * METERS_PER_NM}
            pathOptions={{
              color: hazardColor,
              weight: 1.5,
              opacity: 0.7,
              fillColor: hazardColor,
              fillOpacity: 0.08,
              dashArray: "8, 4",
              className: "atc-weather-pulse",
            }}
          >
            <Tooltip sticky>
              <div style={{
                fontFamily: "var(--font-mono)",
                fontSize: "11px",
                color: hazardColor,
              }}>
                ⚠ Weather Hazard ({advisory.severity})
                <br />
                <span style={{ color: "#aaa" }}>
                  Affected: {advisory.affected_callsigns.join(", ")}
                </span>
              </div>
            </Tooltip>
          </Circle>
        );
      })}
    </>
  );
}

// ─── Main RadarView Component ───────────────────────────────────────

/** Main RadarView component — Leaflet map with ATC display. */
export function RadarView(): React.ReactElement {
  const aircraft = useAtcStore((s) => s.aircraft);
  const conflicts = useAtcStore((s) => s.conflicts);
  const weatherAdvisories = useAtcStore((s) => s.weatherAdvisories);
  const centerLat = useAtcStore((s) => s.centerLatitude);
  const centerLng = useAtcStore((s) => s.centerLongitude);
  const selectedCallsign = useAtcStore((s) => s.selectedCallsign);
  const selectAircraft = useAtcStore((s) => s.selectAircraft);
  const scenarioId = useAtcStore((s) => s.activeScenarioId);

  // Inject emergency blink CSS keyframes
  useEmergencyBlinkStyles();

  // Track previous scenario ID so we only reset the map view on change.
  const prevScenarioRef = useRef(scenarioId);

  const center: [number, number] = [centerLat, centerLng];

  // Build a quick-lookup map for conflict line endpoints
  const aircraftMap = useMemo(() => {
    const map = new Map<string, AircraftState>();
    for (const ac of aircraft) {
      map.set(ac.callsign, ac);
    }
    return map;
  }, [aircraft]);

  const handleSelectAircraft = useCallback(
    (callsign: string) => {
      selectAircraft(callsign);
    },
    [selectAircraft],
  );

  return (
    <div style={{ height: "100%", width: "100%", position: "relative" }}>
      <MapContainer
        center={center}
        zoom={9}
        scrollWheelZoom={true}
        style={{ height: "100%", width: "100%", backgroundColor: "#0a0a0a" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          maxZoom={19}
        />

        <MapCenterUpdater center={center} zoom={9} scenarioId={scenarioId} prevScenarioIdRef={prevScenarioRef} />

        {/* Range rings around center */}
        {RANGE_RINGS_NM.map((nm) => (
          <Circle
            key={`ring-${nm}`}
            center={center}
            radius={nm * METERS_PER_NM}
            pathOptions={{
              color: COLOR_RANGE_RING,
              weight: 0.8,
              fill: false,
              dashArray: "3, 8",
            }}
          />
        ))}

        {/* Range ring distance labels */}
        <RangeRingLabels center={center} />

        {/* Conflict lines between conflicting aircraft */}
        <ConflictLines conflicts={conflicts} aircraftMap={aircraftMap} />

        {/* Aircraft markers */}
        {aircraft.map((ac) => (
          <AircraftMarker
            key={ac.callsign}
            aircraft={ac}
            isSelected={selectedCallsign === ac.callsign}
            onSelect={handleSelectAircraft}
          />
        ))}

        {/* Weather hazard overlay */}
        <WeatherHazardOverlay weatherAdvisories={weatherAdvisories} aircraftMap={aircraftMap} />

        {/* Radar sweep overlay */}
        <RadarSweepOverlay center={center} />
      </MapContainer>

      {/* Map Legend */}
      <div style={{
        position: 'absolute',
        bottom: '2rem',
        left: '0.75rem',
        zIndex: 1000,
        backgroundColor: 'rgba(5, 8, 5, 0.85)',
        border: '1px solid #1a2e1a',
        borderRadius: '4px',
        padding: '0.5rem 0.6rem',
        fontFamily: 'var(--font-mono)',
        fontSize: '0.55rem',
        color: '#88aa88',
        display: 'flex',
        flexDirection: 'column' as const,
        gap: '0.3rem',
        backdropFilter: 'blur(4px)',
      }}>
        <div style={{ fontWeight: 600, color: '#33ff33', fontSize: '0.6rem', marginBottom: '0.15rem' }}>LEGEND</div>
        {/* Aircraft */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
          <svg width="12" height="12" viewBox="0 0 24 24"><path d="M12 2 L14 8 L20 10 L14 12 L14 18 L17 20 L17 21 L12 19 L7 21 L7 20 L10 18 L10 12 L4 10 L10 8 Z" fill="#33ff33" opacity="0.9"/></svg>
          <span>Aircraft</span>
        </div>
        {/* Conflict */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
          <svg width="12" height="6" viewBox="0 0 12 6"><line x1="0" y1="3" x2="12" y2="3" stroke="#ffaa00" strokeWidth="1.5" strokeDasharray="3,2" /></svg>
          <span style={{ color: '#ffaa00' }}>Conflict</span>
        </div>
        {/* Weather Hazard */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
          <svg width="12" height="12" viewBox="0 0 12 12"><circle cx="6" cy="6" r="4.5" fill="none" stroke="#ff3333" strokeWidth="1" strokeDasharray="2,1.5" opacity="0.8" /></svg>
          <span style={{ color: '#ff3333' }}>Weather Hazard</span>
        </div>
        {/* Radar Coverage */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
          <svg width="12" height="12" viewBox="0 0 12 12"><circle cx="6" cy="6" r="4.5" fill="none" stroke="#1a3a1a" strokeWidth="0.8" strokeDasharray="1.5,3" /></svg>
          <span>Radar Coverage</span>
        </div>
      </div>
    </div>
  );
}
