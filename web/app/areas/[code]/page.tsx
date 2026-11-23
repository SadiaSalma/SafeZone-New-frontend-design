"use client";
/**
 * Frontend (web) · Task 26 · /areas/[code] - one area's safety dashboard (FR-22). No log-in needed.
 *
 *  - figure tiles: thefts, thefts per km², how that compares with the whole city, what is stolen most
 *  - busiest hours (24 columns, the peak highlighted) and busiest days
 *  - what is stolen most (bars) and the weekly trend
 *  - a hotspot map: the area outline and red circles where several thefts happened close together
 *  - "Get alerts for this area" (Task 23)
 *
 * Data: GET /api/v1/public/areas/{code}/dashboard?days=30|90 (Task 26 backend).
 */
import dynamic from "next/dynamic";
import Image from "next/image";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ArrowLeft, LoaderCircle, MapPin } from "lucide-react";
import streetTower from "@/public/images/area-dashboard-street-tower.jpg";
import { FollowArea } from "@/components/areas/FollowArea";
import type { Hotspot } from "@/components/areas/HotspotMap";
import { BarList } from "@/components/charts/BarList";
import { ColumnChart } from "@/components/charts/ColumnChart";
import { usePrefs } from "@/components/PreferencesProvider";
import { api, ApiError } from "@/lib/api";
import { areaName, type Area } from "@/lib/areas";
import type { TextKey } from "@/lib/i18n";

const HotspotMap = dynamic(() => import("@/components/areas/HotspotMap"), {
  ssr: false,
  loading: () => <div className="h-[360px] animate-pulse rounded-[1.5rem] bg-bg-soft" />,
});

type Dashboard = {
  area: Area & { geom: GeoJSON.Geometry };
  days: number;
  total: number;
  per_km2: number;
  city_per_km2: number;
  vs_city: number | null;
  by_type: { code: string; name_en: string; name_bn: string; count: number }[];
  by_hour: number[];
  busiest_hour: number | null;
  by_weekday: { day: string; count: number }[];
  weekly: number[];
  hotspots: Hotspot[];
};

const BN_DIGITS = "০১২৩৪৫৬৭৮৯";
const hourLabel = (h: number, lang: "en" | "bn") => {
  const twelve = h % 12 || 12;
  return lang === "bn" ? String(twelve).replace(/\d/g, (d) => BN_DIGITS[+d]) + (h < 12 ? " am" : " pm") : `${twelve} ${h < 12 ? "am" : "pm"}`;
};

// The page reads [code] from the address (useParams), so Next.js 16 wants it inside <Suspense>
export default function AreaDashboardPage() {
  return (
    <Suspense fallback={<div className="grid h-[60vh] place-items-center"><LoaderCircle className="animate-spin text-ink-soft" /></div>}>
      <AreaDashboard />
    </Suspense>
  );
}

function AreaDashboard() {
  const { t, lang } = usePrefs();
  const { code } = useParams<{ code: string }>();
  const [days, setDays] = useState<30 | 90>(90);
  const [data, setData] = useState<Dashboard | null>(null);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    let current = true;
    api<Dashboard>(`/public/areas/${code}/dashboard?days=${days}`)
      .then((d) => current && setData(d))
      .catch((e: ApiError) => current && setProblem(e.message));
    return () => { current = false; };
  }, [code, days]);

  if (problem) return <p role="alert" className="mx-auto mt-16 max-w-md rounded-2xl bg-red-50 p-4 text-center text-red-800">{problem}</p>;

  const top = data?.by_type[0];
  const comparison = data?.vs_city == null || data.total === 0 ? "—" : `${data.vs_city}×`;

  return (
    <>
      <section data-photo-hero className="relative -mt-16 h-[40svh] min-h-[320px] overflow-hidden bg-black">
        <Image src={streetTower} alt="A tall building above a busy Dhaka street with trees" fill preload placeholder="blur"
               sizes="100vw" className="drift object-cover object-[50%_30%]" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-black/30 to-bg" />
        <div className="rise relative mx-auto flex h-full max-w-6xl flex-col justify-end px-4 pb-12 text-white">
          <Link href="/areas" className="mb-3 inline-flex w-fit items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-xs backdrop-blur-md hover:bg-white/25">
            <ArrowLeft size={13} aria-hidden /> {t("dash_all_areas")}
          </Link>
          <h1 className="text-4xl font-semibold md:text-6xl">{data ? areaName(data.area, lang) : "…"}</h1>
          <p className="mt-2 flex items-center gap-1.5 text-white/80">
            <MapPin size={15} aria-hidden /> {data ? `${data.area.type === "thana" ? t("areas_thana") : t("areas_ward")} · ${data.area.size_km2} km²` : ""}
          </p>
        </div>
      </section>

      <section className="mx-auto -mt-6 max-w-6xl px-4">
        <div className="soft-shadow mb-4 flex flex-wrap items-center justify-between gap-3 rounded-[1.5rem] bg-surface p-3">
          <p className="pl-2 text-sm text-ink-soft">{t("dash_sub")}</p>
          <div className="inline-flex rounded-full bg-bg-soft p-1" role="tablist" aria-label={t("map_period")}>
            {([30, 90] as const).map((d) => (
              <button key={d} role="tab" aria-selected={days === d} onClick={() => setDays(d)}
                      className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${days === d ? "bg-primary text-on-primary shadow" : "text-ink-soft hover:text-ink"}`}>
                {t("map_days").replace("{n}", String(d))}
              </button>
            ))}
          </div>
        </div>

        {!data ? (
          <div className="grid h-60 place-items-center"><LoaderCircle className="animate-spin text-ink-soft" /></div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Tile label={t("dash_thefts")} value={String(data.total)} />
              <Tile label={t("dash_per_km2")} value={data.per_km2.toFixed(2)} />
              <Tile label={t("dash_vs_city")} value={comparison} note={data.total ? t("dash_vs_city_note") : undefined} />
              <Tile label={t("dash_top")} value={top ? (lang === "bn" ? top.name_bn : top.name_en) : "—"} small />
            </div>

            {data.total === 0 ? (
              <div className="soft-shadow mt-4 rounded-[1.75rem] bg-surface p-10 text-center">
                <p className="text-lg font-medium text-ink">{t("dash_none")}</p>
                <p className="mt-1 text-sm text-ink-soft">{t("dash_none_sub")}</p>
              </div>
            ) : (
              <div className="mt-4 grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-2">
                <Panel title={t("dash_hours")}
                       sub={data.busiest_hour !== null ? t("dash_hours_peak").replace("{h}", hourLabel(data.busiest_hour, lang)) : undefined}>
                  <ColumnChart values={data.by_hour} labels={data.by_hour.map((_, h) => hourLabel(h, lang))} highlight={data.busiest_hour}
                               labelEvery={3} unit={t("dash_unit")} title={t("dash_hours")} />
                </Panel>
                <Panel title={t("dash_what")}>
                  <BarList unit={t("dash_unit")} rows={data.by_type.map((x) => ({ label: lang === "bn" ? x.name_bn : x.name_en, value: x.count }))} />
                </Panel>
                <Panel title={t("dash_days")}>
                  <ColumnChart values={data.by_weekday.map((d) => d.count)} labels={data.by_weekday.map((d) => t(`day_${d.day}` as TextKey))}
                               highlight={data.by_weekday.reduce((best, d, i, all) => (d.count > all[best].count ? i : best), 0)}
                               unit={t("dash_unit")} title={t("dash_days")} height={170} />
                </Panel>
                <Panel title={t("dash_weekly")}>
                  <ColumnChart values={data.weekly} labels={data.weekly.map((_, i) => i === data.weekly.length - 1 ? t("dash_this_week") : `-${data.weekly.length - 1 - i}`)}
                               highlight={data.weekly.length - 1} labelEvery={data.weekly.length > 6 ? 2 : 1}
                               unit={t("dash_unit")} title={t("dash_weekly")} height={170} />
                </Panel>
              </div>
            )}

            <div className="mt-4 grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
              <Panel title={t("dash_hotspots")} sub={data.hotspots.length ? t("dash_hotspots_sub") : t("dash_no_hotspots")}>
                <HotspotMap outline={data.area.geom} hotspots={data.hotspots} />
              </Panel>
              <Panel title={t("dash_stay_safe")}>
                <p className="text-sm text-ink-soft">{t("dash_stay_safe_sub")}</p>
                <FollowArea area={data.area} />
                <Link href="/map" className="mt-4 block text-center text-sm text-primary hover:underline">{t("dash_see_map")}</Link>
              </Panel>
            </div>
          </>
        )}
      </section>
    </>
  );
}

function Tile({ label, value, note, small }: { label: string; value: string; note?: string; small?: boolean }) {
  return (
    <div className="rise soft-shadow rounded-[1.5rem] bg-surface p-5">
      <p className="text-xs text-ink-soft">{label}</p>
      <p className={`mt-1 font-semibold text-ink ${small ? "text-lg leading-tight" : "text-3xl"}`}>{value}</p>
      {note && <p className="mt-1 text-[11px] text-ink-soft">{note}</p>}
    </div>
  );
}

function Panel({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <section className="rise soft-shadow rounded-[1.75rem] bg-surface p-5">
      <h2 className="text-sm font-semibold tracking-wide text-ink-soft uppercase">{title}</h2>
      {sub && <p className="mt-0.5 text-xs text-ink-soft">{sub}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}
