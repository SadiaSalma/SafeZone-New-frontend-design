"use client";
/**
 * Frontend (web) · Task 25 · /map - the public theft map (FR-21). No log-in needed.
 *
 *  - choose the period: last 7, 30 or 90 days
 *  - choose a theft type (or all), with how many of each
 *  - the map: one coloured dot per verified theft (moved 100-200 m for privacy),
 *    house burglaries only as a bubble per thana
 *  - the latest thefts as a list next to the map
 *
 * Data: GET /api/v1/public/incidents (Task 25 backend).
 */
import dynamic from "next/dynamic";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { BellRing, Clock, LoaderCircle, MapPin, ShieldCheck } from "lucide-react";
import flyover from "@/public/images/map-dhaka-flyover.jpg";
import { usePrefs } from "@/components/PreferencesProvider";
import { THEFT_ICONS } from "@/components/report/ReportSteps";
import { api } from "@/lib/api";
import { areaName } from "@/lib/areas";
import { THEFT_COLOURS, type Incidents } from "@/lib/public";
import { ago } from "@/lib/review";

const IncidentMap = dynamic(() => import("@/components/map/IncidentMap"), {
  ssr: false,
  loading: () => <div className="h-[560px] animate-pulse rounded-[1.5rem] bg-bg-soft" />,
});

const PERIODS = [7, 30, 90] as const;

export default function PublicMapPage() {
  const { t, lang } = usePrefs();
  const [days, setDays] = useState<(typeof PERIODS)[number]>(30);
  const [type, setType] = useState<string>("");
  const [all, setAll] = useState<Incidents | null>(null); // every type: for the counts on the chips
  const [shown, setShown] = useState<Incidents | null>(null);

  useEffect(() => {
    let current = true;
    api<Incidents>(`/public/incidents?days=${days}`).then((d) => current && setAll(d)).catch(() => {});
    return () => { current = false; };
  }, [days]);

  useEffect(() => {
    let current = true;
    api<Incidents>(`/public/incidents?days=${days}${type ? `&type=${type}` : ""}`).then((d) => current && setShown(d)).catch(() => {});
    return () => { current = false; };
  }, [days, type]);

  return (
    <>
      <section data-photo-hero className="relative -mt-16 h-[40svh] min-h-[320px] overflow-hidden bg-black">
        <Image src={flyover} alt="A flyover cutting through Dhaka's skyline with traffic below" fill preload placeholder="blur"
               sizes="100vw" className="drift object-cover object-[50%_60%]" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-black/30 to-bg" />
        <div className="rise relative mx-auto flex h-full max-w-6xl flex-col justify-end px-4 pb-12 text-white">
          <p className="mb-3 inline-flex w-fit items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-xs backdrop-blur-md">
            <ShieldCheck size={14} aria-hidden /> {t("map_badge")}
          </p>
          <h1 className="text-4xl font-semibold md:text-6xl">{t("map_title")}</h1>
          <p className="mt-2 max-w-2xl text-white/80">{t("map_sub")}</p>
        </div>
      </section>

      <section className="mx-auto -mt-6 max-w-6xl px-4">
        {/* Filters */}
        <div className="soft-shadow mb-4 flex flex-wrap items-center gap-3 rounded-[1.5rem] bg-surface p-3">
          <div className="inline-flex rounded-full bg-bg-soft p-1" role="tablist" aria-label={t("map_period")}>
            {PERIODS.map((d) => (
              <button key={d} role="tab" aria-selected={days === d} onClick={() => setDays(d)}
                      className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${days === d ? "bg-primary text-on-primary shadow" : "text-ink-soft hover:text-ink"}`}>
                {t("map_days").replace("{n}", String(d))}
              </button>
            ))}
          </div>
          <div className="no-scrollbar flex flex-1 gap-2 overflow-x-auto">
            <Chip on={type === ""} onClick={() => setType("")} colour="#334155" label={`${t("chip_all")} · ${all?.total ?? "…"}`} />
            {all?.by_type.map((x) => (
              <Chip key={x.code} on={type === x.code} onClick={() => setType(x.code)} colour={THEFT_COLOURS[x.code]}
                    label={`${lang === "bn" ? x.name_bn : x.name_en} · ${x.count}`} />
            ))}
          </div>
        </div>

        <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="soft-shadow rounded-[1.75rem] bg-surface p-3 md:p-4">
            <IncidentMap data={shown} />
            <p className="mt-3 flex items-start gap-2 text-xs text-ink-soft">
              <ShieldCheck size={14} className="mt-0.5 shrink-0" aria-hidden /> {t("map_privacy")}
            </p>
          </div>

          <aside className="soft-shadow rounded-[1.75rem] bg-surface p-5">
            <h2 className="mb-3 text-sm font-semibold tracking-wide text-ink-soft uppercase">{t("map_latest")}</h2>
            {!shown ? (
              <div className="grid h-32 place-items-center"><LoaderCircle className="animate-spin text-ink-soft" /></div>
            ) : shown.points.length === 0 && shown.area_counts.length === 0 ? (
              <p className="text-sm text-ink-soft">{t("map_none")}</p>
            ) : (
              <ul className="space-y-2">
                {shown.points.slice(0, 8).map((p) => (
                  <li key={p.id} className="flex items-center gap-3 rounded-2xl bg-bg-soft p-3">
                    <span className="grid size-9 shrink-0 place-items-center rounded-xl text-white [&_svg]:size-[18px]"
                          style={{ background: THEFT_COLOURS[p.theft_type] }}>{THEFT_ICONS[p.theft_type]}</span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-ink">{lang === "bn" ? p.theft_name_bn : p.theft_name_en}</p>
                      <p className="flex items-center gap-2 truncate text-xs text-ink-soft">
                        <span className="inline-flex items-center gap-0.5"><MapPin size={11} aria-hidden />{p.thana ? areaName(p.thana, lang) : "—"}</span>
                        <span className="inline-flex items-center gap-0.5"><Clock size={11} aria-hidden />{ago(p.occurred_hour, lang)}</span>
                      </p>
                    </div>
                  </li>
                ))}
                {shown.area_counts.map((b) => (
                  <li key={b.thana.code} className="flex items-center gap-3 rounded-2xl bg-amber-50 p-3 text-sm text-amber-950">
                    <span className="grid size-9 shrink-0 place-items-center rounded-full bg-amber-700 text-xs font-bold text-white">{b.count}</span>
                    {t("map_burglary_bubble").replace("{n}", String(b.count)).replace("{area}", areaName(b.thana, lang))}
                  </li>
                ))}
              </ul>
            )}
            <Link href="/areas" className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-full bg-primary px-4 py-2.5 text-sm font-semibold text-on-primary">
              <BellRing size={16} aria-hidden /> {t("map_follow")}
            </Link>
          </aside>
        </div>
      </section>
    </>
  );
}

function Chip({ on, onClick, colour, label }: { on: boolean; onClick: () => void; colour: string; label: string }) {
  return (
    <button onClick={onClick}
            className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs transition ${
              on ? "border-transparent bg-ink text-bg" : "border-line text-ink hover:border-ink-soft"}`}>
      <span className="size-2.5 rounded-full" style={{ background: colour }} aria-hidden /> {label}
    </button>
  );
}
