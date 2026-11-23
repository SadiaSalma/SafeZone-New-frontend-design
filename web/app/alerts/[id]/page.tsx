"use client";
/**
 * Frontend (web) · Task 25 · /alerts/[id] - one alert. This is the page a push notification opens.
 *
 *  - the alert text in your language, what kind of theft, the area and when
 *  - a map with the alert area (the circle is drawn around the PUBLIC point, moved 100-200 m;
 *    a house burglary has no point at all - only the area name)
 *  - "Get alerts for this area" (Task 23)
 *
 * Data: GET /api/v1/public/alerts/{id} (Task 25 backend).
 */
import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ArrowLeft, BellRing, Clock, LoaderCircle, MapPin, Smartphone } from "lucide-react";
import { FollowArea } from "@/components/areas/FollowArea";
import { usePrefs } from "@/components/PreferencesProvider";
import { THEFT_ICONS } from "@/components/report/ReportSteps";
import { api, ApiError } from "@/lib/api";
import { areaName } from "@/lib/areas";
import { THEFT_COLOURS, type PublicAlert } from "@/lib/public";
import { dhakaTime } from "@/lib/reports";

const IncidentMap = dynamic(() => import("@/components/map/IncidentMap"), {
  ssr: false,
  loading: () => <div className="h-[360px] animate-pulse rounded-[1.5rem] bg-bg-soft" />,
});

// The page reads [id] from the address (useParams), so Next.js 16 wants it inside <Suspense>
export default function AlertPage() {
  return (
    <Suspense fallback={<div className="grid h-[60vh] place-items-center"><LoaderCircle className="animate-spin text-ink-soft" /></div>}>
      <OneAlert />
    </Suspense>
  );
}

function OneAlert() {
  const { t, lang } = usePrefs();
  const { id } = useParams<{ id: string }>();
  const [alert, setAlert] = useState<PublicAlert | null>(null);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    let current = true;
    api<PublicAlert>(`/public/alerts/${id}`).then((a) => current && setAlert(a)).catch((e: ApiError) => current && setProblem(e.message));
    return () => { current = false; };
  }, [id]);

  if (problem) return <p role="alert" className="mx-auto mt-16 max-w-md rounded-2xl bg-red-50 p-4 text-center text-red-800">{problem}</p>;
  if (!alert) return <div className="grid h-[60vh] place-items-center"><LoaderCircle className="animate-spin text-ink-soft" /></div>;

  const colour = THEFT_COLOURS[alert.theft_type] ?? "#64748b";
  return (
    <div className="mx-auto max-w-3xl px-4 pt-6">
      <Link href="/alerts" className="inline-flex items-center gap-1.5 rounded-full px-2 py-2 text-sm text-ink-soft hover:text-ink">
        <ArrowLeft size={16} aria-hidden /> {t("alerts_back")}
      </Link>

      <article className="rise soft-shadow mt-3 overflow-hidden rounded-[1.75rem] bg-surface">
        <div className="p-6" style={{ background: `linear-gradient(135deg, ${colour}22, transparent 60%)` }}>
          <p className="inline-flex items-center gap-1.5 rounded-full bg-red-600 px-3 py-1 text-xs font-semibold text-white">
            <BellRing size={13} aria-hidden /> {t("alerts_badge_one")}
          </p>
          <div className="mt-4 flex items-center gap-4">
            <span className="grid size-14 shrink-0 place-items-center rounded-2xl text-white" style={{ background: colour }}>
              {THEFT_ICONS[alert.theft_type]}
            </span>
            <div>
              <h1 className="text-2xl font-semibold text-ink md:text-3xl">{lang === "bn" ? alert.theft_name_bn : alert.theft_name_en}{alert.is_demo && <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 align-middle text-[10px] font-semibold tracking-wide text-amber-900 uppercase">{t("demo_label")}</span>}</h1>
              <p className="mt-1 flex flex-wrap gap-x-4 text-sm text-ink-soft">
                <span className="inline-flex items-center gap-1"><MapPin size={14} aria-hidden />
                  {alert.thana ? areaName(alert.thana, lang) : "—"}{alert.ward && ` · ${areaName(alert.ward, lang)}`}</span>
                <span className="inline-flex items-center gap-1"><Clock size={14} aria-hidden />{dhakaTime(alert.sent_at, lang)}</span>
              </p>
            </div>
          </div>
          <p className="mt-5 text-lg leading-relaxed text-ink">{lang === "bn" ? alert.text_bn : alert.text_en}</p>
          <p className="mt-3 inline-flex items-center gap-1.5 text-xs text-ink-soft">
            <Smartphone size={13} aria-hidden /> {t("alerts_reached").replace("{n}", alert.phones.toLocaleString())}
          </p>
        </div>

        <div className="border-t border-line p-4">
          {alert.point ? (
            <IncidentMap data={null} height={360} circle={{ ...alert.point, radius_m: alert.radius_m, colour }} />
          ) : (
            <p className="rounded-2xl bg-bg-soft p-4 text-sm text-ink-soft">{t("alerts_area_only")}</p>
          )}
          <p className="mt-3 text-xs text-ink-soft">{t("alerts_map_note")}</p>
          {alert.thana && <FollowArea area={alert.thana} />}
        </div>
      </article>
    </div>
  );
}
