"use client";
/**
 * Frontend (web) · Task 28 · /crime - crime statistics for everyone (FR-23, Design Revisions R6).
 *
 *  - choose: the period (1, 3, 6 or 12 months), a crime category (or all), Thanas / Wards,
 *    and "Per km²" (fair between big and small areas, the default) or "Total"
 *  - the danger map: every area coloured by its level (dark red = very high … grey = no data),
 *    with a legend that says the levels are RELATIVE (compared with other areas, not a safe limit)
 *  - the top 10 most dangerous areas, totals per category, and where the figures come from
 *
 * The figures are official monthly totals entered by admins (Task 27) - not SafeZone's own reports.
 * Data: GET /api/v1/public/crime/overview and /api/v1/areas/shapes.
 */
import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { BookOpen, Info, LoaderCircle } from "lucide-react";
import darkStreet from "@/public/images/crime-dark-street-walk.jpg";
import { DhakaMap } from "@/components/areas/DhakaMap";
import { TheftGallery } from "@/components/home/TheftGallery";
import { BarList } from "@/components/charts/BarList";
import { usePrefs } from "@/components/PreferencesProvider";
import { api } from "@/lib/api";
import { areaName, type Area, type AreaShapes } from "@/lib/areas";
import type { TextKey } from "@/lib/i18n";

type Level = "very_high" | "high" | "medium" | "low" | "no_data";
type Row = { code: string; name_en: string; name_bn: string; level: Level; score?: number; total?: number; rank?: number; top_category?: string; size_km2?: number };
type Overview = {
  months: number; level: "thana" | "ward"; mode: "per_km2" | "total";
  areas: Row[]; top10: Row[]; areas_with_data: number; sources: string[];
  by_category: { key: string; name_en: string; name_bn: string; count: number }[];
  categories: { key: string; name_en: string; name_bn: string; weight: number }[];
};

// Design doc 5.8: one colour per level (from dark red down to grey)
const LEVEL_COLOURS: Record<Level, string> = {
  very_high: "#991B1B", high: "#DC2626", medium: "#F97316", low: "#FACC15", no_data: "#D1D5DB",
};
const LEVEL_ORDER: Level[] = ["very_high", "high", "medium", "low", "no_data"];

export default function CrimePage() {
  const { t, lang } = usePrefs();
  const [months, setMonths] = useState(3);
  const [category, setCategory] = useState("");
  const [level, setLevel] = useState<"thana" | "ward">("thana");
  const [mode, setMode] = useState<"per_km2" | "total">("per_km2");
  const [data, setData] = useState<Overview | null>(null);
  const [shapes, setShapes] = useState<Partial<Record<"thana" | "ward", AreaShapes>>>({});
  const [chosen, setChosen] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    api<Overview>(`/public/crime/overview?months=${months}&level=${level}&mode=${mode}${category ? `&category=${category}` : ""}`)
      .then((d) => current && setData(d)).catch(() => {});
    return () => { current = false; };
  }, [months, category, level, mode]);

  useEffect(() => {
    if (shapes[level]) return;
    api<AreaShapes>(`/areas/shapes?type=${level}`).then((s) => setShapes((old) => ({ ...old, [level]: s }))).catch(() => {});
  }, [level, shapes]);

  const byCode = useMemo(() => new Map((data?.areas ?? []).map((a) => [a.code, a])), [data]);
  const fillFor = useCallback((area: Area) => LEVEL_COLOURS[byCode.get(area.code)?.level ?? "no_data"], [byCode]);
  const chosenRow = chosen ? byCode.get(chosen) : null;
  const catName = (key?: string) => {
    const c = data?.categories.find((x) => x.key === key);
    return c ? (lang === "bn" ? c.name_bn || c.name_en : c.name_en) : "—";
  };
  const unit = mode === "per_km2" ? t("crime_score_unit") : t("crime_total_unit");

  return (
    <>
      <section data-photo-hero className="relative -mt-16 h-[40svh] min-h-[320px] overflow-hidden bg-black">
        <Image src={darkStreet} alt="A person walking down a dark Dhaka street at night" fill preload placeholder="blur"
               sizes="100vw" className="drift object-cover object-[50%_45%]" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-black/30 to-bg" />
        <div className="rise relative mx-auto flex h-full max-w-6xl flex-col justify-end px-4 pb-12 text-white">
          <h1 className="text-4xl font-semibold md:text-6xl">{t("crime_title")}</h1>
          <p className="mt-2 max-w-2xl text-white/80">{t("crime_sub")}</p>
        </div>
      </section>

      <section className="mx-auto -mt-6 max-w-6xl px-4">
        {/* Filters */}
        <div className="soft-shadow mb-4 flex flex-wrap items-center gap-3 rounded-[1.5rem] bg-surface p-3">
          <Segmented value={String(months)} onChange={(v) => setMonths(Number(v))}
                     options={[1, 3, 6, 12].map((m) => ({ value: String(m), label: t("crime_months").replace("{n}", String(m)) }))} />
          <Segmented value={level} onChange={(v) => { setLevel(v as "thana" | "ward"); setChosen(null); }}
                     options={[{ value: "thana", label: t("areas_thanas") }, { value: "ward", label: t("areas_wards") }]} />
          <Segmented value={mode} onChange={(v) => setMode(v as "per_km2" | "total")}
                     options={[{ value: "per_km2", label: t("crime_per_km2") }, { value: "total", label: t("crime_total") }]} />
          <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label={t("crime_category")}
                  className="rounded-full border border-line bg-bg px-4 py-2 text-sm text-ink">
            <option value="">{t("crime_all_categories")}</option>
            {data?.categories.map((c) => <option key={c.key} value={c.key}>{lang === "bn" ? c.name_bn || c.name_en : c.name_en}</option>)}
          </select>
        </div>

        {!data ? <div className="grid h-60 place-items-center"><LoaderCircle className="animate-spin text-ink-soft" /></div> : (
          <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
            {/* The danger map */}
            <div className="soft-shadow rounded-[1.75rem] bg-surface p-4 md:p-6">
              <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-ink">
                {LEVEL_ORDER.map((l) => (
                  <span key={l} className="inline-flex items-center gap-1.5">
                    <span className="size-3 rounded-sm" style={{ background: LEVEL_COLOURS[l] }} aria-hidden /> {t(`level_${l}` as TextKey)}
                  </span>
                ))}
              </div>
              {shapes[level] ? (
                <DhakaMap features={shapes[level]!.features} selected={chosen} onSelect={(a) => setChosen(a.code)} fillFor={fillFor} />
              ) : <div className="grid aspect-[3/4] place-items-center"><LoaderCircle className="animate-spin text-ink-soft" /></div>}
              <p className="mt-3 flex items-start gap-2 text-xs text-ink-soft"><Info size={14} className="mt-0.5 shrink-0" aria-hidden /> {t("crime_relative")}</p>
            </div>

            <aside className="flex flex-col gap-4">
              {chosenRow && (
                <div className="rise rounded-[1.75rem] bg-primary-strong p-5 text-white shadow-lg">
                  <p className="text-xs text-white/70 uppercase">{level === "thana" ? t("areas_thana") : t("areas_ward")}</p>
                  <p className="text-2xl font-semibold">{areaName(chosenRow, lang)}</p>
                  <p className="mt-2 inline-flex items-center gap-2 rounded-full bg-white/15 px-3 py-1 text-sm">
                    <span className="size-2.5 rounded-full" style={{ background: LEVEL_COLOURS[chosenRow.level] }} aria-hidden />
                    {t(`level_${chosenRow.level}` as TextKey)}{chosenRow.rank && ` · #${chosenRow.rank}`}
                  </p>
                  {chosenRow.score !== undefined && (
                    <p className="mt-3 text-sm text-white/85">{chosenRow.score} {unit} · {t("crime_mostly")} {catName(chosenRow.top_category)}</p>
                  )}
                  <Link href={`/areas/${chosenRow.code}`} className="mt-4 inline-block text-sm font-semibold underline underline-offset-4">{t("dash_open")}</Link>
                </div>
              )}

              <div className="soft-shadow rounded-[1.75rem] bg-surface p-5">
                <h2 className="mb-3 text-sm font-semibold tracking-wide text-ink-soft uppercase">{t("crime_top10")}</h2>
                {data.top10.length === 0 ? <p className="text-sm text-ink-soft">{t("crime_no_data")}</p> : (
                  <table className="w-full text-sm">
                    <thead><tr className="text-left text-xs text-ink-soft">
                      <th className="pb-2 font-normal">#</th><th className="pb-2 font-normal">{level === "thana" ? t("areas_thana") : t("areas_ward")}</th>
                      <th className="pb-2 text-right font-normal">{unit}</th>
                    </tr></thead>
                    <tbody>
                      {data.top10.map((row) => (
                        <tr key={row.code} onClick={() => setChosen(row.code)} className="cursor-pointer border-t border-line hover:bg-bg-soft">
                          <td className="py-2 pr-2 text-ink-soft">{row.rank}</td>
                          <td className="py-2">
                            <span className="flex items-center gap-2 text-ink">
                              <span className="size-2.5 shrink-0 rounded-full" style={{ background: LEVEL_COLOURS[row.level] }} aria-hidden />
                              {areaName(row, lang)}
                            </span>
                            <span className="ml-[18px] text-xs text-ink-soft">{t(`level_${row.level}` as TextKey)} · {catName(row.top_category)}</span>
                          </td>
                          <td className="py-2 text-right font-medium text-ink">{row.score}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              <div className="soft-shadow rounded-[1.75rem] bg-surface p-5">
                <h2 className="mb-3 text-sm font-semibold tracking-wide text-ink-soft uppercase">{t("crime_by_category")}</h2>
                {data.by_category.length ? (
                  <BarList unit={t("crime_total_unit")} rows={data.by_category.map((c) => ({ label: lang === "bn" ? c.name_bn || c.name_en : c.name_en, value: c.count }))} />
                ) : <p className="text-sm text-ink-soft">{t("crime_no_data")}</p>}
              </div>

              <div className="rounded-[1.5rem] bg-bg-soft p-4 text-xs text-ink-soft">
                <p className="mb-1 flex items-center gap-1.5 font-semibold text-ink"><BookOpen size={14} aria-hidden /> {t("crime_sources")}</p>
                {data.sources.length ? data.sources.map((s) => <p key={s}>{s}</p>) : <p>—</p>}
                <p className="mt-2">{t("crime_formula")}</p>
              </div>
            </aside>
          </div>
        )}
      </section>

      <TheftGallery only={["night_mugging", "machete_gang", "bike_snatching", "gunpoint"]}
                    title="tg_crime_title" sub="tg_crime_sub" className="mx-auto mt-14 max-w-6xl px-4" />
    </>
  );
}

function Segmented({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  return (
    <div className="inline-flex rounded-full bg-bg-soft p-1">
      {options.map((o) => (
        <button key={o.value} onClick={() => onChange(o.value)} aria-pressed={value === o.value}
                className={`rounded-full px-3.5 py-1.5 text-sm transition ${value === o.value ? "bg-primary font-medium text-on-primary shadow" : "text-ink-soft hover:text-ink"}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}
