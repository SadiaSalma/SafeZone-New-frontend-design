"use client";
/**
 * Frontend (web) · Task 18 · /review - the verifier's queue.
 *
 *  - "Waiting for review": oldest first (FR-14), each card shows what, where, how long it has waited,
 *    the risk level, a red mark if a check FAILED, and who is reviewing it right now
 *  - "Waiting for the victim": reports where the verifier asked for more information (Task 19)
 *  - refreshes itself every 30 seconds
 *
 * Only verifiers and admins can open it (the backend checks too).
 * Data: GET /api/v1/review/queue (Task 18 backend).
 */
import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Camera, ChevronRight, CircleX, Clock, LoaderCircle, Lock, MapPin, RefreshCw } from "lucide-react";
import policeTraffic from "@/public/images/review-police-traffic.jpg";
import { useAuth } from "@/components/AuthProvider";
import { usePrefs } from "@/components/PreferencesProvider";
import { THEFT_ICONS } from "@/components/report/ReportSteps";
import { api, ApiError } from "@/lib/api";
import { areaName } from "@/lib/areas";
import { ago, RISK_COLOURS, type QueueCard } from "@/lib/review";
import type { TextKey } from "@/lib/i18n";

type Queue = { waiting: QueueCard[]; needs_info: QueueCard[] };

export default function ReviewQueuePage() {
  const { t } = usePrefs();
  const { user, loading } = useAuth();
  const [queue, setQueue] = useState<Queue | null>(null);
  const [tab, setTab] = useState<keyof Queue>("waiting");
  const [problem, setProblem] = useState("");
  const isStaff = user?.role === "verifier" || user?.role === "admin";

  const load = useCallback(() => {
    api<Queue>("/review/queue").then(setQueue).catch((e: ApiError) => setProblem(e.message));
  }, []);

  useEffect(() => {
    if (!isStaff) return;
    load();
    const timer = setInterval(load, 30000); // new reports appear without reloading
    return () => clearInterval(timer);
  }, [isStaff, load]);

  return (
    <>
      <section data-photo-hero className="relative -mt-16 h-[36svh] min-h-[290px] overflow-hidden bg-black">
        <Image src={policeTraffic} alt="A traffic policeman standing between buses on a busy Dhaka road" fill preload
               placeholder="blur" sizes="100vw" className="drift object-cover object-[50%_35%]" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-black/35 to-bg" />
        <div className="rise relative mx-auto flex h-full max-w-5xl flex-col justify-end px-4 pb-10 text-white">
          <p className="mb-2 inline-flex w-fit items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-xs backdrop-blur-md">
            <Lock size={13} aria-hidden /> {t("review_staff_only")}
          </p>
          <h1 className="text-4xl font-semibold md:text-5xl">{t("review_title")}</h1>
          <p className="mt-2 text-white/80">{t("review_sub")}</p>
        </div>
      </section>

      <section className="mx-auto -mt-4 max-w-5xl px-4">
        {loading ? (
          <Spinner />
        ) : !isStaff ? (
          <div className="soft-shadow rounded-[1.75rem] bg-surface p-8 text-center text-ink">{t("review_only_staff")}</div>
        ) : !queue ? (
          problem ? <p role="alert" className="rounded-2xl bg-red-50 p-4 text-sm text-red-800">{problem}</p> : <Spinner />
        ) : (
          <>
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <div className="inline-flex rounded-full bg-surface p-1 shadow-sm" role="tablist">
                {(["waiting", "needs_info"] as const).map((key) => (
                  <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}
                          className={`rounded-full px-5 py-2 text-sm font-medium transition ${
                            tab === key ? "bg-primary text-on-primary shadow" : "text-ink-soft hover:text-ink"}`}>
                    {t(key === "waiting" ? "review_tab_waiting" : "review_tab_needs_info")}
                    <span className={`ml-2 rounded-full px-2 py-0.5 text-xs ${tab === key ? "bg-white/25" : "bg-bg-soft"}`}>
                      {queue[key].length}
                    </span>
                  </button>
                ))}
              </div>
              <button onClick={load} className="inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm text-ink-soft hover:text-ink">
                <RefreshCw size={15} aria-hidden /> {t("refresh")}
              </button>
            </div>

            {queue[tab].length === 0 ? (
              <div className="soft-shadow rounded-[1.75rem] bg-surface p-10 text-center">
                <p className="text-lg font-medium text-ink">{t("review_empty")}</p>
                <p className="mt-1 text-sm text-ink-soft">{t("review_empty_sub")}</p>
              </div>
            ) : (
              <ol className="space-y-3">
                {queue[tab].map((card, i) => <Card key={card.id} card={card} position={i + 1} />)}
              </ol>
            )}
          </>
        )}
      </section>
    </>
  );
}

function Spinner() {
  return <div className="grid h-40 place-items-center"><LoaderCircle className="animate-spin text-ink-soft" /></div>;
}

function Card({ card, position }: { card: QueueCard; position: number }) {
  const { t, lang } = usePrefs();
  const held = card.claim && !card.claim.mine;
  return (
    <li className="rise">
      <Link href={`/review/${card.id}`}
            className={`soft-shadow group flex items-center gap-4 rounded-[1.5rem] bg-surface p-4 transition hover:-translate-y-0.5 md:p-5 ${
              held ? "opacity-70" : ""}`}>
        <span className="hidden w-6 text-center text-sm text-ink-soft sm:block">{position}</span>
        <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-bg-soft text-primary">{THEFT_ICONS[card.theft_type]}</span>
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 font-semibold text-ink">
            {lang === "bn" ? card.theft_name_bn : card.theft_name_en}
            {card.has_failed_check && (
              <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-[11px] font-semibold text-red-800">
                <CircleX size={12} aria-hidden /> {t("review_failed_check")}
              </span>
            )}
          </p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-soft">
            <span className="inline-flex items-center gap-1"><MapPin size={12} aria-hidden />
              {card.thana ? areaName(card.thana, lang) : "—"}{card.ward && ` · ${areaName(card.ward, lang)}`}</span>
            <span className="inline-flex items-center gap-1"><Clock size={12} aria-hidden /> {t("review_waiting")} {ago(card.submitted_at, lang)}</span>
            {card.photos > 0 && <span className="inline-flex items-center gap-1"><Camera size={12} aria-hidden /> {card.photos}</span>}
          </p>
          {card.claim && (
            <p className={`mt-1.5 inline-flex items-center gap-1 text-xs font-medium ${card.claim.mine ? "text-primary" : "text-amber-700"}`}>
              <Lock size={12} aria-hidden /> {card.claim.mine ? t("review_claimed_you") : `${card.claim.by_name} ${t("review_claimed_other")}`}
            </p>
          )}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className={`rounded-full px-3 py-1 text-xs font-semibold ${RISK_COLOURS[card.risk.level].pill}`}>
            {t(`risk_${card.risk.level}` as TextKey)} · {card.risk.score}
          </span>
        </div>
        <ChevronRight size={18} className="shrink-0 text-ink-soft transition group-hover:translate-x-0.5" aria-hidden />
      </Link>
    </li>
  );
}
