/** RadarView — Leaflet-based ATC radar display for ATC Guardian.

Displays aircraft as colored dot markers on a dark map with
heading lines, callsign labels, and range rings. Uses CartoDB
dark tiles for the ATC radar aesthetic.
*/

import { useEffect } from "react";
import L from "leaflet";
import {
  MapContainer,
  TileLayer,
  Marker,
  Polyline,
  Circle,
  Tooltip,
  useMap,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { useAtcStore } from "../stores/atcStore";
import type { AircraftState } from "../lib/types";

/** Meters per nautical mile. */
const METERS_PER_NM = 1852;

/** Earth radius in nautical miles. */
const EARTH_RADIUS_NM = 3440.065;

/** Range ring radii in nautical miles. */
const RANGE_RINGS_NM = [10, 20, 30, 40, 50, 60];

/** Heading projection distance in nautical miles. */
const HEADING_PROJECTION_NM = 3;

/** Create a small colored circle marker using L.divIcon. */
function createAircraftIcon(color: string, size: number = 10): L.DivIcon {
  return L.divIcon({
    className: "",
    html: `<div style="
      width:${size}px;
      height:${size}px;
      background:${color};
      border:1.5px solid #ffffff;
      border-radius:50%;
      box-shadow:0 0 6px ${color}80;
    "></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
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

/** Get blip color based on squawk code. */
function getBlipColor(aircraft: AircraftState): string {
  if (aircraft.squawk === "7700") return "#ff3333";
  if (aircraft.squawk === "7500") return "#ff8800";
  if (aircraft.squawk === "7600") return "#ffaa00";
  return "#33ff33";
}

/** Component that updates the map center when scenario data changes. */
function MapCenterUpdater({
  center,
  zoom,
}: {
  center: [number, number];
  zoom: number;
}): null {
  const map = useMap();

  useEffect(() => {
    map.setView(center, zoom, { animate: true, duration: 1.0 });
  }, [map, center, zoom]);

  return null;
}

/** Single aircraft marker with heading line and tooltip. */
function AircraftMarker({
  aircraft,
}: {
  aircraft: AircraftState;
}): React.ReactElement {
  const color = getBlipColor(aircraft);
  const position: [number, number] = [aircraft.latitude, aircraft.longitude];
  const headingEnd = computeHeadingEndpoint(
    aircraft.latitude,
    aircraft.longitude,
    aircraft.heading_deg,
    HEADING_PROJECTION_NM,
  );
  const fl = Math.round(aircraft.altitude_ft / 100)
    .toString()
    .padStart(3, "0");
  const vsIndicator =
    aircraft.vertical_speed_fpm > 0
      ? ` ↑${aircraft.vertical_speed_fpm}`
      : aircraft.vertical_speed_fpm < 0
        ? ` ↓${Math.abs(aircraft.vertical_speed_fpm)}`
        : "";

  return (
    <>
      <Marker position={position} icon={createAircraftIcon(color, 10)}>
        <Tooltip direction="right" offset={[8, 0]} permanent>
          <div
            style={{
              fontFamily: "monospace",
              fontSize: "11px",
              color,
              background: "transparent",
              border: "none",
            }}
          >
            <div style={{ fontWeight: "bold" }}>{aircraft.callsign}</div>
            <div style={{ color: "#aaa", fontSize: "10px" }}>
              FL{fl} {Math.round(aircraft.heading_deg).toString().padStart(3, "0")}°{" "}
              {Math.round(aircraft.speed_kts)}kt{vsIndicator}
            </div>
          </div>
        </Tooltip>
      </Marker>
      <Polyline
        positions={[position, headingEnd]}
        pathOptions={{ color, weight: 1.5, opacity: 0.7, dashArray: "4, 4" }}
      />
      {aircraft.squawk === "7700" && (
        <Circle
          center={position}
          radius={5 * METERS_PER_NM}
          pathOptions={{
            color: "#ff3333",
            weight: 1.5,
            fill: false,
            dashArray: "3, 6",
          }}
        />
      )}
    </>
  );
}

/** Main RadarView component — Leaflet map with ATC display. */
export function RadarView(): React.ReactElement {
  const aircraft = useAtcStore((s) => s.aircraft);
  const centerLat = useAtcStore((s) => s.centerLatitude);
  const centerLng = useAtcStore((s) => s.centerLongitude);

  const center: [number, number] = [centerLat, centerLng];

  return (
    <div style={{ height: "calc(100vh - 60px)", width: "100%" }}>
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

        <MapCenterUpdater center={center} zoom={9} />

        {/* Range rings around center */}
        {RANGE_RINGS_NM.map((nm) => (
          <Circle
            key={`ring-${nm}`}
            center={center}
            radius={nm * METERS_PER_NM}
            pathOptions={{
              color: "#1a4a1a",
              weight: 0.8,
              fill: false,
              dashArray: "3, 8",
            }}
          />
        ))}

        {/* Aircraft markers */}
        {aircraft.map((ac) => (
          <AircraftMarker key={ac.callsign} aircraft={ac} />
        ))}
      </MapContainer>
    </div>
  );
}
