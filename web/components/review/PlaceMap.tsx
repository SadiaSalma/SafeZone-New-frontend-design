"use client";
/**
 * Frontend (web) · Task 18 · PlaceMap.tsx - the EXACT place of the theft (only staff and the victim
 * ever see this, R8) and the police station where the GD was filed, on one small map.
 * A dashed line joins them, so the verifier sees at a glance if they are far apart.
 *
 * Loaded with next/dynamic + { ssr: false } because Leaflet needs the browser.
 */
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { MapContainer, Marker, Polyline, TileLayer, Tooltip } from "react-leaflet";

const PIN = L.divIcon({ className: "", html: '<div class="sz-pin"><span></span></div>', iconSize: [36, 46], iconAnchor: [18, 44] });
const STATION = L.divIcon({
  className: "",
  html: '<div class="sz-station">P</div>',
  iconSize: [30, 30],
  iconAnchor: [15, 15],
});

type Props = { lat: number; lng: number; station?: { lat: number; lng: number; name: string } | null; height?: number };

export default function PlaceMap({ lat, lng, station, height = 300 }: Props) {
  const points: [number, number][] = station ? [[lat, lng], [station.lat, station.lng]] : [[lat, lng]];
  const bounds = L.latLngBounds(points).pad(0.4);
  return (
    <div className="isolate overflow-hidden rounded-2xl border border-line" style={{ height }}>
      <MapContainer bounds={station ? bounds : undefined} center={station ? undefined : [lat, lng]} zoom={station ? undefined : 16}
                    maxZoom={18} scrollWheelZoom={false} className="h-full w-full">
        <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" className="sz-tiles"
                   attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' />
        <Marker position={[lat, lng]} icon={PIN} />
        {station && (
          <>
            <Polyline positions={points} pathOptions={{ color: "#64748b", weight: 2, dashArray: "6 6" }} />
            <Marker position={[station.lat, station.lng]} icon={STATION}>
              <Tooltip direction="top" offset={[0, -14]}>{station.name}</Tooltip>
            </Marker>
          </>
        )}
      </MapContainer>
    </div>
  );
}
