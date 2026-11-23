"use client";
/**
 * Frontend (web) · Task 13 · LocationPicker.tsx - "Where did it happen?"
 *
 * A real street map (Leaflet + OpenStreetMap's free map pictures, softened a little by CSS):
 *  - tap/click the map to drop the pin, or drag the pin to move it
 *  - "Use my location" puts the pin where the phone is
 *  - the dashed line is the edge of the area SafeZone covers (GET /areas/outline)
 *  - after every move we ask the backend which thana + ward it is (GET /areas/lookup)
 *    and show it on a little card; outside Dhaka the card turns into a warning
 *
 * Leaflet only works in the browser, so pages load this file with
 * next/dynamic and { ssr: false } (see app/report/page.tsx).
 */
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect, useMemo, useRef, useState } from "react";
import { GeoJSON, MapContainer, Marker, TileLayer, useMap, useMapEvents } from "react-leaflet";
import { AlertTriangle, LoaderCircle, LocateFixed, MapPin } from "lucide-react";
import { usePrefs } from "@/components/PreferencesProvider";
import { api } from "@/lib/api";
import { areaName, type Lookup } from "@/lib/areas";

export type Spot = { lat: number; lng: number };
type Outline = {
  outline: GeoJSON.Geometry;
  bounds: { south: number; west: number; north: number; east: number };
  center: Spot;
};
type Props = {
  value: Spot | null;
  onChange: (spot: Spot, place: Lookup | null) => void;
  height?: number;
};

// The pin: our own little HTML drawing (Leaflet's default pin images break in modern bundlers)
const PIN = L.divIcon({
  className: "",
  html: '<div class="sz-pin"><span></span></div>',
  iconSize: [36, 46],
  iconAnchor: [18, 44],
});

export default function LocationPicker({ value, onChange, height = 420 }: Props) {
  const { t, lang } = usePrefs();
  const [outline, setOutline] = useState<Outline | null>(null);
  const [place, setPlace] = useState<Lookup | null>(null);
  const [checking, setChecking] = useState(false);
  const [locating, setLocating] = useState(false);
  const [problem, setProblem] = useState("");
  const [flyTarget, setFlyTarget] = useState<Spot | null>(null); // only "Use my location" moves the map
  const asked = useRef(0); // only the newest lookup may update the card

  useEffect(() => {
    api<Outline>("/areas/outline").then(setOutline).catch(() => setProblem(t("picker_no_areas")));
  }, [t]);

  async function move(spot: Spot) {
    setProblem("");
    setChecking(true);
    const ticket = ++asked.current;
    onChange(spot, null);
    try {
      const answer = await api<Lookup>(`/areas/lookup?lat=${spot.lat.toFixed(6)}&lng=${spot.lng.toFixed(6)}`);
      if (ticket !== asked.current) return;
      setPlace(answer);
      onChange(spot, answer);
    } catch {
      if (ticket === asked.current) { setPlace(null); setProblem(t("picker_outside_bd")); }
    } finally {
      if (ticket === asked.current) setChecking(false);
    }
  }

  function useMyLocation() {
    if (!navigator.geolocation) return setProblem(t("areas_no_location"));
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (p) => {
        const spot = { lat: p.coords.latitude, lng: p.coords.longitude };
        setLocating(false);
        setFlyTarget(spot);
        move(spot);
      },
      () => { setLocating(false); setProblem(t("areas_location_denied")); },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }

  const limits = useMemo(() => {
    if (!outline) return undefined;
    const pad = 0.08; // let people scroll a little past the edge (~8 km)
    const b = outline.bounds;
    return L.latLngBounds([b.south - pad, b.west - pad], [b.north + pad, b.east + pad]);
  }, [outline]);

  if (!outline) {
    return (
      <div className="grid place-items-center rounded-[1.5rem] bg-bg-soft text-ink-soft" style={{ height }}>
        {problem || <LoaderCircle className="animate-spin" aria-label={t("working")} />}
      </div>
    );
  }

  return (
    <div className="relative isolate overflow-hidden rounded-[1.5rem] border border-line" style={{ height }}>
      <MapContainer
        center={[value?.lat ?? outline.center.lat, value?.lng ?? outline.center.lng]}
        zoom={value ? 16 : 12}
        minZoom={11}
        maxBounds={limits}
        maxBoundsViscosity={0.8}
        scrollWheelZoom={false} // the mouse wheel scrolls the page; zoom with + / - or a double-click
        className="h-full w-full"
        attributionControl
      >
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          maxZoom={19}
          className="sz-tiles"
        />
        <GeoJSON data={outline.outline} interactive={false}
                 style={{ color: "var(--primary)", weight: 2.5, dashArray: "6 6", fillOpacity: 0.04 }} />
        <ClickToMove onPick={move} />
        <FlyTo spot={flyTarget} />
        {value && (
          <Marker position={[value.lat, value.lng]} icon={PIN} draggable
                  eventHandlers={{ dragend: (e) => { const p = (e.target as L.Marker).getLatLng(); move({ lat: p.lat, lng: p.lng }); } }} />
        )}
      </MapContainer>

      {/* Use my location (top right) */}
      <button type="button" onClick={useMyLocation} disabled={locating}
              className="absolute top-3 right-3 z-[500] inline-flex items-center gap-2 rounded-full bg-surface px-4 py-2 text-sm font-medium text-ink shadow-lg transition hover:scale-[1.03] disabled:opacity-70">
        {locating ? <LoaderCircle size={16} className="animate-spin" aria-hidden /> : <LocateFixed size={16} aria-hidden />}
        {t("picker_my_location")}
      </button>

      {/* What we know about the chosen spot (bottom) */}
      <div className="pointer-events-none absolute inset-x-3 bottom-3 z-[500] flex justify-center">
        <div role="status" aria-live="polite"
             className={`pointer-events-auto flex max-w-md items-center gap-3 rounded-2xl px-4 py-3 text-sm shadow-xl backdrop-blur-md ${
               problem || (place && !place.inside_dhaka) ? "bg-red-600/90 text-white" : "bg-surface/95 text-ink"}`}>
          {checking ? (
            <><LoaderCircle size={18} className="animate-spin" aria-hidden /> {t("picker_checking")}</>
          ) : problem ? (
            <><AlertTriangle size={18} aria-hidden /> {problem}</>
          ) : !value ? (
            <><MapPin size={18} className="text-primary" aria-hidden /> {t("picker_tap")}</>
          ) : place && !place.inside_dhaka ? (
            <><AlertTriangle size={18} aria-hidden /> {t("areas_outside")}</>
          ) : place ? (
            <>
              <MapPin size={18} className="shrink-0 text-primary" aria-hidden />
              <span>
                <strong>{place.thana ? areaName(place.thana, lang) : "—"}</strong>
                {place.thana && ` ${t("areas_thana")}`}
                {place.ward && ` · ${areaName(place.ward, lang)}`}
                <span className="block text-xs text-ink-soft">{t("picker_drag")}</span>
              </span>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/** Clicking anywhere on the map moves the pin there. */
function ClickToMove({ onPick }: { onPick: (spot: Spot) => void }) {
  useMapEvents({ click: (e) => onPick({ lat: e.latlng.lat, lng: e.latlng.lng }) });
  return null;
}

/** After "Use my location", glide the map to the new pin. */
function FlyTo({ spot }: { spot: Spot | null }) {
  const map = useMap();
  const last = useRef<string>("");
  useEffect(() => {
    if (!spot) return;
    const key = `${spot.lat.toFixed(5)},${spot.lng.toFixed(5)}`;
    if (key === last.current) return;
    last.current = key;
    map.flyTo([spot.lat, spot.lng], Math.max(map.getZoom(), 16), { duration: 0.8 });
  }, [map, spot]);
  return null;
}
