"use client";
/**
 * Frontend (web) · Task 25 · IncidentMap.tsx - the public theft map (FR-21).
 *
 *  - every verified theft is a coloured dot (one colour per theft type), at its PUBLIC point:
 *    moved 100-200 m from the real place, so nobody can find a victim's spot
 *  - house burglaries are never dots: each thana gets one brown bubble with the number
 *  - hover/tap a dot: what, where (thana · ward) and roughly when
 *  - optional `circle`: the alert page draws the alert's radius around its point
 *
 * Loaded with next/dynamic + { ssr: false } because Leaflet needs the browser.
 */
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect } from "react";
import { Circle, CircleMarker, MapContainer, Marker, TileLayer, Tooltip, useMap } from "react-leaflet";
import { usePrefs } from "@/components/PreferencesProvider";
import { areaName } from "@/lib/areas";
import { THEFT_COLOURS, type Incidents } from "@/lib/public";
import { dhakaTime } from "@/lib/reports";

type Props = {
  data: Incidents | null;
  circle?: { lat: number; lng: number; radius_m: number; colour: string } | null;
  height?: number | string;
  zoom?: number;
};

// One canvas for all dots (made once); a tap within 6 px of a dot still counts
const CANVAS = L.canvas({ tolerance: 6 });

function bubble(count: number) {
  const size = 26 + Math.min(count, 20) * 2;
  return L.divIcon({
    className: "",
    html: `<div class="sz-bubble" style="width:${size}px;height:${size}px">${count}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

export default function IncidentMap({ data, circle, height = 560, zoom = 12 }: Props) {
  const { t, lang } = usePrefs();
  const center: [number, number] = circle ? [circle.lat, circle.lng] : [23.785, 90.405];
  return (
    <div className="isolate overflow-hidden rounded-[1.5rem] border border-line" style={{ height }}>
      <MapContainer center={center} zoom={circle ? 15 : zoom} minZoom={11} maxZoom={18} preferCanvas
                    renderer={CANVAS} scrollWheelZoom={false} className="h-full w-full">
        <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" className="sz-tiles"
                   attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' />
        {circle && (
          <Circle center={[circle.lat, circle.lng]} radius={circle.radius_m} interactive={false}
                  pathOptions={{ color: circle.colour, weight: 2.5, dashArray: "8 6", fillColor: circle.colour, fillOpacity: 0.12 }} />
        )}
        {data?.points.map((p) => (
          <CircleMarker key={p.id} center={[p.lat, p.lng]} radius={circle ? 9 : 7}
                        pathOptions={{ color: "#fff", weight: 2, fillColor: THEFT_COLOURS[p.theft_type] ?? "#64748b", fillOpacity: 0.95 }}>
            <Tooltip>
              <strong>{lang === "bn" ? p.theft_name_bn : p.theft_name_en}</strong>{p.is_demo && ` · ${t("demo_label")}`}<br />
              {p.thana ? areaName(p.thana, lang) : ""}{p.ward ? ` · ${areaName(p.ward, lang)}` : ""}<br />
              {dhakaTime(p.occurred_hour, lang)}
            </Tooltip>
          </CircleMarker>
        ))}
        {data?.area_counts.map((b) => (
          <Marker key={b.thana.code} position={[b.lat, b.lng]} icon={bubble(b.count)}>
            <Tooltip>{t("map_burglary_bubble").replace("{n}", String(b.count)).replace("{area}", areaName(b.thana, lang))}</Tooltip>
          </Marker>
        ))}
        <Recenter circle={circle} />
      </MapContainer>
    </div>
  );
}

function Recenter({ circle }: { circle?: Props["circle"] }) {
  const map = useMap();
  useEffect(() => {
    if (circle) map.setView([circle.lat, circle.lng], 15);
  }, [map, circle]);
  return null;
}
