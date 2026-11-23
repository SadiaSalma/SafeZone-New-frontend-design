"use client";
/**
 * Frontend (web) · Tasks 21 + 24 · NetworkMap.tsx - the simulated phone network on a map.
 *
 *  - towers: small white dots (Task 24: the towers that broadcast the chosen alert turn red-ringed)
 *  - phones: tiny dots - grey normally, RED if they received the chosen alert (FR-19), violet = a test phone
 *  - the chosen alert: a red circle around the place (its radius)
 *  - only the phones inside the current view are loaded, again after every pan or zoom
 *  - click a phone -> onPhoneClick (the page shows its messages); click the map -> onMapClick (test mode)
 *
 * Thousands of dots would be slow as normal HTML markers, so everything is drawn on ONE canvas
 * (Leaflet's preferCanvas) - Design Revisions R10: "simulator map rendering".
 * Loaded with next/dynamic + { ssr: false } because Leaflet needs the browser.
 */
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect, useState } from "react";
import { Circle, CircleMarker, MapContainer, TileLayer, Tooltip, useMap, useMapEvents } from "react-leaflet";
import { api } from "@/lib/api";

export type Tower = { id: string; code: string; lat: number; lng: number; range_m: number; phones: number };
export type Phone = { id: string; lat: number; lng: number; tower_id: string; is_test: boolean; received?: boolean };
export type AlertView = { id: string; center: { lat: number; lng: number }; radius_m: number; tower_ids: string[]; phones: number };

type Props = {
  towers: Tower[];
  showRanges: boolean;
  alert?: AlertView | null; // Task 24
  onPhoneClick?: (phone: Phone) => void;
  onMapClick?: (lat: number, lng: number) => void;
  onPhonesLoaded?: (count: number, received: number) => void;
  refreshKey?: number; // change it to reload the phones (e.g. after placing a test phone)
  height?: number;
};

// One canvas for all dots; a click within 8 px of a tiny phone dot still counts as a click on it
const CANVAS = L.canvas({ tolerance: 8 });

export default function NetworkMap({ towers, showRanges, alert, onPhoneClick, onMapClick, onPhonesLoaded, refreshKey = 0, height = 560 }: Props) {
  const used = new Set(alert?.tower_ids ?? []);
  return (
    <div className="isolate overflow-hidden rounded-[1.5rem] border border-line" style={{ height }}>
      <MapContainer center={[23.785, 90.41]} zoom={12} minZoom={11} maxZoom={17} preferCanvas renderer={CANVAS} scrollWheelZoom={false}
                    className={`h-full w-full ${onMapClick ? "cursor-crosshair" : ""}`}>
        <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" className="sz-tiles"
                   attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' />
        {showRanges && towers.map((t) => (
          <Circle key={`r-${t.id}`} center={[t.lat, t.lng]} radius={t.range_m} interactive={false}
                  pathOptions={{ color: used.has(t.id) ? "#dc2626" : "#1e3a8a", weight: used.has(t.id) ? 1 : 0.6,
                                 opacity: used.has(t.id) ? 0.6 : 0.35, fillOpacity: 0.025 }} />
        ))}
        {alert && (
          <Circle center={[alert.center.lat, alert.center.lng]} radius={alert.radius_m} interactive={false}
                  pathOptions={{ color: "#dc2626", weight: 2.5, dashArray: "8 6", fillColor: "#ef4444", fillOpacity: 0.12 }} />
        )}
        <Phones alertId={alert?.id} onClick={onPhoneClick} onLoaded={onPhonesLoaded} refreshKey={refreshKey} />
        {towers.map((t) => (
          <CircleMarker key={t.id} center={[t.lat, t.lng]} radius={used.has(t.id) ? 4.5 : 3.5}
                        pathOptions={{ color: used.has(t.id) ? "#dc2626" : "#0f172a", weight: used.has(t.id) ? 2.5 : 1.5,
                                       fillColor: "#ffffff", fillOpacity: 1 }}>
            <Tooltip>{t.code} · {t.phones} phones</Tooltip>
          </CircleMarker>
        ))}
        <FlyToAlert alert={alert} />
        {onMapClick && <MapClicks onClick={onMapClick} />}
      </MapContainer>
    </div>
  );
}

/** Loads the phones inside the view (again after every move) and draws them as dots. */
function Phones({ alertId, onClick, onLoaded, refreshKey }: {
  alertId?: string; onClick?: (p: Phone) => void; onLoaded?: (count: number, received: number) => void; refreshKey: number;
}) {
  const map = useMap();
  const [phones, setPhones] = useState<Phone[]>([]);
  const [view, setView] = useState(() => map.getBounds().toBBoxString());

  useMapEvents({ moveend: () => setView(map.getBounds().toBBoxString()) });

  useEffect(() => {
    const [west, south, east, north] = view.split(",").map(Number);
    let current = true;
    const timer = setTimeout(() => {
      const forAlert = alertId ? `&alert_id=${alertId}` : "";
      api<{ phones: Phone[] }>(`/admin/simulator/phones?south=${south}&west=${west}&north=${north}&east=${east}${forAlert}`)
        .then((answer) => {
          if (!current) return;
          setPhones(answer.phones);
          onLoaded?.(answer.phones.length, answer.phones.filter((p) => p.received).length);
        }).catch(() => {});
    }, 250);
    return () => { current = false; clearTimeout(timer); };
  }, [view, alertId, onLoaded, refreshKey]);

  // Received phones are drawn last, so the red dots sit on top
  const ordered = [...phones].sort((a, b) => Number(!!a.received) - Number(!!b.received) || Number(a.is_test) - Number(b.is_test));
  return (
    <>
      {ordered.map((p) => {
        const fill = p.is_test ? "#7c3aed" : p.received ? "#dc2626" : "#64748b";
        return (
          <CircleMarker key={`${p.id}-${p.received ? 1 : 0}`} center={[p.lat, p.lng]} radius={p.is_test ? 7 : p.received ? 3.2 : 2.2}
                        eventHandlers={onClick ? { click: () => onClick(p) } : undefined}
                        pathOptions={{ stroke: p.is_test, color: p.received ? "#dc2626" : "#fff", weight: 3, fillColor: fill,
                                       fillOpacity: p.received || p.is_test ? 0.95 : 0.75 }} />
        );
      })}
    </>
  );
}

/** When an alert is chosen, glide the map to it. */
function FlyToAlert({ alert }: { alert?: AlertView | null }) {
  const map = useMap();
  useEffect(() => {
    if (alert) map.flyTo([alert.center.lat, alert.center.lng], 14, { duration: 0.8 });
  }, [map, alert]);
  return null;
}

function MapClicks({ onClick }: { onClick: (lat: number, lng: number) => void }) {
  useMapEvents({ click: (e) => onClick(e.latlng.lat, e.latlng.lng) });
  return null;
}
