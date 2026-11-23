"use client";
/**
 * Frontend (web) · Task 26 · HotspotMap.tsx - one area on a map, with its theft hotspots.
 *
 *  - the area's outline (thana or ward) in the theme colour
 *  - each hotspot = a red circle; the more thefts, the stronger the red (one hue, light -> dark)
 *  - hover a hotspot: how many thefts happened there
 * Hotspots come from the moved public points, so they never show anyone's exact spot.
 * Loaded with next/dynamic + { ssr: false } because Leaflet needs the browser.
 */
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect } from "react";
import { Circle, GeoJSON, MapContainer, TileLayer, Tooltip, useMap } from "react-leaflet";
import { usePrefs } from "@/components/PreferencesProvider";

export type Hotspot = { lat: number; lng: number; count: number; radius_m: number };

type Props = { outline: GeoJSON.Geometry; hotspots: Hotspot[]; height?: number };

export default function HotspotMap({ outline, hotspots, height = 360 }: Props) {
  const { t } = usePrefs();
  const most = Math.max(...hotspots.map((h) => h.count), 1);
  return (
    <div className="isolate overflow-hidden rounded-[1.5rem] border border-line" style={{ height }}>
      <MapContainer center={[23.78, 90.4]} zoom={13} scrollWheelZoom={false} className="h-full w-full">
        <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" className="sz-tiles"
                   attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' />
        <GeoJSON key={JSON.stringify(outline).slice(0, 80)} data={outline} interactive={false}
                 style={{ color: "var(--primary)", weight: 3, fillColor: "var(--primary)", fillOpacity: 0.08 }} />
        {hotspots.map((h) => (
          <Circle key={`${h.lat},${h.lng}`} center={[h.lat, h.lng]} radius={h.radius_m}
                  pathOptions={{ color: "#b91c1c", weight: 2, fillColor: "#dc2626", fillOpacity: 0.2 + 0.45 * (h.count / most) }}>
            <Tooltip>{t("dash_hotspot_tip").replace("{n}", String(h.count))}</Tooltip>
          </Circle>
        ))}
        <FitArea outline={outline} />
      </MapContainer>
    </div>
  );
}

function FitArea({ outline }: { outline: GeoJSON.Geometry }) {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(L.geoJSON(outline).getBounds(), { padding: [20, 20] });
  }, [map, outline]);
  return null;
}
