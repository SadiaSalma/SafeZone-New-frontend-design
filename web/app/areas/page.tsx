"use client";
/**
 * Frontend (web) · Task 12 · /areas - "Know your area".
 *
 *  - a photo header with "Find my area" (uses the phone's location) and a search box
 *  - an interactive map of Dhaka: switch between the 41 thanas and the 92 wards
 *  - a side panel: the chosen area (size, its wards or thanas, its police stations)
 *    or "You are here" (your thana, ward and the nearest police stations)
 *  - every area as a chip below the map, filtered by the search box
 *
 * Data: GET /api/v1/areas/shapes, /api/v1/areas/{code}, /api/v1/areas/lookup (Task 12 backend).
 */
import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Building2, LoaderCircle, LocateFixed, MapPin, Phone, Search, ShieldCheck, X } from "lucide-react";
import uttaraSunset from "@/public/images/areas-uttara-aerial-sunset.jpg";
import { DhakaMap } from "@/components/areas/DhakaMap";
import { FollowArea } from "@/components/areas/FollowArea";
import { usePrefs } from "@/components/PreferencesProvider";
import { api, ApiError } from "@/lib/api";
import {
  areaName, distanceText,
  type Area, type AreaDetail, type AreaShapes, type AreaType, type Lookup, type PoliceStation,
} from "@/lib/areas";

const SAMPLE_SPOT = { lat: 23.7457, lng: 90.4047 }; // Ramna, for trying the page away from Dhaka

export default function AreasPage() {
  const { t, lang } = usePrefs();
  const [layer, setLayer] = useState<AreaType>("thana");
  const [shapes, setShapes] = useState<Partial<Record<AreaType, AreaShapes>>>({});
  const [selected, setSelected] = useState<AreaDetail | null>(null);
  const [here, setHere] = useState<Lookup | null>(null);
  const [search, setSearch] = useState("");
  const [locating, setLocating] = useState(false);
  const [problem, setProblem] = useState("");

  // Load the shapes of the visible layer once
  useEffect(() => {
    if (shapes[layer]) return;
    api<AreaShapes>(`/areas/shapes?type=${layer}`)
      .then((data) => setShapes((old) => ({ ...old, [layer]: data })))
      .catch((e: ApiError) => setProblem(e.message));
  }, [layer, shapes]);

  const features = useMemo(() => shapes[layer]?.features ?? [], [shapes, layer]);
  const chips = useMemo(() => {
    const words = search.trim().toLowerCase();
    const all = features.map((f) => f.properties);
    const sorted = layer === "ward" ? all.sort((a, b) => Number(a.code.slice(5)) - Number(b.code.slice(5)))
                                     : all.sort((a, b) => a.name_en.localeCompare(b.name_en));
    return words ? sorted.filter((a) => a.name_en.toLowerCase().includes(words) || a.name_bn.includes(search.trim())) : sorted;
  }, [features, layer, search]);

  async function choose(area: Area) {
    setProblem("");
    if (area.type !== layer) setLayer(area.type);
    try {
      setSelected(await api<AreaDetail>(`/areas/${area.code}`));
      document.getElementById("area-panel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (e) {
      setProblem((e as ApiError).message);
    }
  }

  async function lookUp(spot: { lat: number; lng: number }) {
    const answer = await api<Lookup>(`/areas/lookup?lat=${spot.lat}&lng=${spot.lng}`);
    setHere(answer);
    if (answer.inside_dhaka) {
      const mine = layer === "thana" ? answer.thana : answer.ward;
      if (mine) await choose(mine);
    } else {
      setProblem(t("areas_outside"));
    }
  }

  function findMe() {
    setProblem("");
    if (!navigator.geolocation) return setProblem(t("areas_no_location"));
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => lookUp({ lat: position.coords.latitude, lng: position.coords.longitude })
        .catch((e: ApiError) => setProblem(e.message))
        .finally(() => setLocating(false)),
      () => { setProblem(t("areas_location_denied")); setLocating(false); },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }

  function trySample() {
    setProblem("");
    setLocating(true);
    lookUp(SAMPLE_SPOT).catch((e: ApiError) => setProblem(e.message)).finally(() => setLocating(false));
  }

  return (
    <>
      {/* ---------- Photo header ---------- */}
      <section data-photo-hero className="relative -mt-16 h-[52svh] min-h-[420px] overflow-hidden bg-black">
        <Image src={uttaraSunset} alt="Uttara, Dhaka, from the air at sunset" fill preload placeholder="blur"
               sizes="100vw" className="drift object-cover" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/55 via-black/30 to-bg" />
        <div className="rise relative mx-auto flex h-full max-w-6xl flex-col justify-end px-4 pb-14 text-white">
          <p className="mb-3 inline-flex w-fit items-center gap-2 rounded-full bg-white/15 px-3 py-1 text-xs backdrop-blur-md">
            <MapPin size={14} aria-hidden /> {t("areas_badge")}
          </p>
          <h1 className="max-w-2xl text-4xl leading-tight font-semibold md:text-6xl">{t("areas_title")}</h1>
          <p className="mt-3 max-w-xl text-white/80">{t("areas_sub")}</p>

          <div className="mt-7 flex flex-col gap-3 sm:flex-row sm:items-center">
            <button onClick={findMe} disabled={locating}
                    className="inline-flex items-center justify-center gap-2 rounded-full bg-white px-6 py-3 text-sm font-semibold text-neutral-900 shadow-lg transition hover:scale-[1.02] disabled:opacity-70">
              {locating ? <LoaderCircle size={18} className="animate-spin" aria-hidden /> : <LocateFixed size={18} aria-hidden />}
              {t("areas_find_me")}
            </button>
            <label className="flex flex-1 items-center gap-2 rounded-full border border-white/30 bg-white/10 px-5 py-3 backdrop-blur-md sm:max-w-sm">
              <Search size={18} className="text-white/70" aria-hidden />
              <span className="sr-only">{t("areas_search")}</span>
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("areas_search")}
                     className="w-full bg-transparent text-sm text-white placeholder:text-white/60 focus:outline-none" />
              {search && (
                <button onClick={() => setSearch("")} aria-label={t("areas_clear")} className="text-white/70 hover:text-white">
                  <X size={16} />
                </button>
              )}
            </label>
          </div>
          <button onClick={trySample} className="mt-3 w-fit text-xs text-white/70 underline underline-offset-4 hover:text-white">
            {t("areas_try_sample")}
          </button>
        </div>
      </section>

      {/* ---------- Map + side panel ---------- */}
      <section className="mx-auto -mt-6 grid max-w-6xl grid-cols-[minmax(0,1fr)] gap-6 px-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="soft-shadow rounded-[1.75rem] bg-surface p-4 md:p-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="inline-flex rounded-full bg-bg-soft p-1" role="tablist" aria-label={t("areas_layer")}>
              {(["thana", "ward"] as const).map((type) => (
                <button key={type} role="tab" aria-selected={layer === type} onClick={() => setLayer(type)}
                        className={`rounded-full px-5 py-2 text-sm font-medium transition ${
                          layer === type ? "bg-primary text-on-primary shadow" : "text-ink-soft hover:text-ink"}`}>
                  {type === "thana" ? t("areas_thanas") : t("areas_wards")}
                </button>
              ))}
            </div>
            <p className="text-xs text-ink-soft">{t("areas_hint")}</p>
          </div>

          {problem && (
            <p role="alert" className="mb-4 rounded-2xl bg-accent/15 px-4 py-3 text-sm text-ink">{problem}</p>
          )}

          {features.length ? (
            <DhakaMap features={features} selected={selected?.type === layer ? selected.code : null}
                      onSelect={choose} pin={here?.inside_dhaka ? here : null} />
          ) : (
            <div className="grid aspect-[3/4] place-items-center text-ink-soft">
              <LoaderCircle className="animate-spin" aria-label={t("working")} />
            </div>
          )}
          <p className="mt-3 text-[11px] text-ink-soft">{t("areas_source")}</p>
        </div>

        <aside id="area-panel" className="flex flex-col gap-4 lg:sticky lg:top-20 lg:self-start">
          {here?.inside_dhaka && <YouAreHere here={here} onChoose={choose} />}
          {selected ? <AreaPanel area={selected} onChoose={choose} /> : !here && (
            <div className="soft-shadow rounded-[1.75rem] bg-surface p-6 text-sm text-ink-soft">
              <Building2 className="mb-3 text-primary" aria-hidden />
              {t("areas_pick")}
            </div>
          )}
        </aside>
      </section>

      {/* ---------- All areas as chips ---------- */}
      <section className="mx-auto mt-10 max-w-6xl px-4">
        <h2 className="mb-4 text-xl font-semibold text-ink">
          {layer === "thana" ? t("areas_all_thanas") : t("areas_all_wards")}{" "}
          <span className="text-sm font-normal text-ink-soft">({chips.length})</span>
        </h2>
        <div className="flex flex-wrap gap-2">
          {chips.map((area) => (
            <button key={area.code} onClick={() => choose(area)}
                    className={`rounded-full border px-4 py-2 text-sm transition ${
                      selected?.code === area.code ? "border-primary bg-primary text-on-primary"
                                                   : "border-line bg-surface text-ink hover:border-primary"}`}>
              {areaName(area, lang)}
            </button>
          ))}
          {!chips.length && features.length > 0 && <p className="text-sm text-ink-soft">{t("areas_none")}</p>}
        </div>
      </section>
    </>
  );
}

function YouAreHere({ here, onChoose }: { here: Lookup; onChoose: (a: Area) => void }) {
  const { t, lang } = usePrefs();
  return (
    <div className="rise rounded-[1.75rem] bg-primary-strong p-6 text-white shadow-lg">
      <p className="flex items-center gap-2 text-xs tracking-wide text-white/70 uppercase">
        <LocateFixed size={14} aria-hidden /> {t("areas_you_are_in")}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {here.thana && (
          <button onClick={() => onChoose(here.thana!)} className="rounded-full bg-white px-4 py-1.5 text-sm font-semibold text-neutral-900">
            {areaName(here.thana, lang)} · {t("areas_thana")}
          </button>
        )}
        {here.ward && (
          <button onClick={() => onChoose(here.ward!)} className="rounded-full border border-white/40 px-4 py-1.5 text-sm">
            {areaName(here.ward, lang)}
          </button>
        )}
      </div>
      <p className="mt-5 mb-2 text-xs tracking-wide text-white/70 uppercase">{t("areas_nearest_police")}</p>
      <ul className="space-y-2">
        {here.nearest_police_stations.map((s) => <StationRow key={s.code} station={s} dark />)}
      </ul>
    </div>
  );
}

function AreaPanel({ area, onChoose }: { area: AreaDetail; onChoose: (a: Area) => void }) {
  const { t, lang } = usePrefs();
  const related = area.type === "thana" ? area.wards : area.thanas;
  return (
    <div key={area.code} className="rise soft-shadow rounded-[1.75rem] bg-surface p-6">
      <p className="text-xs tracking-wide text-ink-soft uppercase">
        {area.type === "thana" ? t("areas_thana") : t("areas_ward")}
      </p>
      <h2 className="mt-1 text-3xl font-semibold text-ink">{areaName(area, lang)}</h2>
      <p className="text-sm text-ink-soft">{lang === "bn" ? area.name_en : area.name_bn}</p>

      <dl className="mt-5 grid grid-cols-2 gap-3">
        <div className="rounded-2xl bg-bg-soft p-3">
          <dt className="text-xs text-ink-soft">{t("areas_size")}</dt>
          <dd className="text-lg font-semibold text-ink">{area.size_km2} km²</dd>
        </div>
        <div className="rounded-2xl bg-bg-soft p-3">
          <dt className="text-xs text-ink-soft">{area.type === "thana" ? t("areas_wards") : t("areas_thanas")}</dt>
          <dd className="text-lg font-semibold text-ink">{related?.length ?? 0}</dd>
        </div>
      </dl>

      {!!related?.length && (
        <>
          <p className="mt-5 mb-2 text-xs tracking-wide text-ink-soft uppercase">
            {area.type === "thana" ? t("areas_wards_here") : t("areas_thanas_here")}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {related.map((r) => (
              <button key={r.code} onClick={() => onChoose(r)}
                      className="rounded-full bg-bg-soft px-3 py-1 text-xs text-ink hover:bg-primary hover:text-on-primary">
                {areaName(r, lang)}
              </button>
            ))}
          </div>
        </>
      )}

      {!!area.police_stations?.length && (
        <>
          <p className="mt-5 mb-2 text-xs tracking-wide text-ink-soft uppercase">{t("areas_police_here")}</p>
          <ul className="space-y-2">
            {area.police_stations.map((s) => <StationRow key={s.code} station={s} />)}
          </ul>
        </>
      )}

      {/* Task 26: the area's safety dashboard */}
      <Link href={`/areas/${area.code}`}
            className="mt-5 flex items-center justify-between rounded-2xl bg-bg-soft px-4 py-3 text-sm font-medium text-ink hover:bg-line">
        {t("dash_open")} <span aria-hidden>→</span>
      </Link>

      {/* Task 23: get a notification when there is an alert here */}
      <FollowArea area={area} />
    </div>
  );
}

function StationRow({ station, dark }: { station: PoliceStation; dark?: boolean }) {
  const { lang } = usePrefs();
  return (
    <li className={`flex items-center gap-3 rounded-2xl p-3 ${dark ? "bg-white/10" : "bg-bg-soft"}`}>
      <ShieldCheck size={18} className={dark ? "text-white/80" : "text-primary"} aria-hidden />
      <div className="min-w-0 flex-1">
        <p className={`truncate text-sm font-medium ${dark ? "text-white" : "text-ink"}`}>{areaName(station, lang)}</p>
        {station.distance_m !== undefined && (
          <p className={`text-xs ${dark ? "text-white/65" : "text-ink-soft"}`}>{distanceText(station.distance_m)}</p>
        )}
      </div>
      {station.phone && (
        <a href={`tel:${station.phone}`} aria-label={`Call ${station.name_en}`}
           className={`grid size-9 place-items-center rounded-full ${dark ? "bg-white text-neutral-900" : "bg-primary text-on-primary"}`}>
          <Phone size={15} />
        </a>
      )}
    </li>
  );
}
