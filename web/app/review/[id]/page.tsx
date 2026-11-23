"use client";
/**
 * Frontend (web) · Task 18 · /review/[id] - the review screen (design doc 5.4).
 *
 * Opening the page CLAIMS the report for 15 minutes (only one verifier can hold it).
 * A timer shows how long the hold lasts; "Back to queue" lets it go.
 * If someone else holds it, the page is read-only and says who.
 *
 *  Left:  the exact place + the GD's police station on a map, the photos, the victim's story
 *  Right: the risk meter with reasons, the automatic checks, the GD, safe facts about the reporter
 *
 * Task 19: the decision bar (approve / ask for information / reject) and the report's history.
 * Data: GET /api/v1/review/{id}, POST /claim, POST /release (Task 18 backend).
 */
import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { ArrowLeft, CalendarClock, CircleCheck, IdCard, LoaderCircle, Lock, MapPin, MessageCircleReply, ShieldCheck, Timer, X } from "lucide-react";
import { createPortal } from "react-dom";
import { useAuth } from "@/components/AuthProvider";
import { usePrefs } from "@/components/PreferencesProvider";
import { AlertPreview, type AlertTexts } from "@/components/review/AlertPreview";
import { ChecksList } from "@/components/review/ChecksList";
import { OcrCompare } from "@/components/review/OcrCompare";
import { DecisionBar } from "@/components/review/DecisionBar";
import { Timeline } from "@/components/review/Timeline";
import { RiskMeter } from "@/components/review/RiskMeter";
import { api, ApiError } from "@/lib/api";
import { areaName } from "@/lib/areas";
import { dhakaTime, type ReportPhoto } from "@/lib/reports";
import type { ReviewDetail } from "@/lib/review";

const PlaceMap = dynamic(() => import("@/components/review/PlaceMap"), {
  ssr: false,
  loading: () => <div className="h-[300px] animate-pulse rounded-2xl bg-bg-soft" />,
});

// The page reads [id] from the address (useParams), so Next.js 16 wants it inside <Suspense>
export default function ReviewPage() {
  return (
    <Suspense fallback={<div className="grid h-[60vh] place-items-center"><LoaderCircle className="animate-spin text-ink-soft" /></div>}>
      <ReviewScreen />
    </Suspense>
  );
}

function ReviewScreen() {
  const { t, lang } = usePrefs();
  const { user, loading } = useAuth();
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [report, setReport] = useState<ReviewDetail | null>(null);
  const [claimProblem, setClaimProblem] = useState("");
  const [problem, setProblem] = useState("");
  const [big, setBig] = useState<ReportPhoto | null>(null);
  const [decided, setDecided] = useState(""); // Task 19: the new status after a decision
  const [alertTexts, setAlertTexts] = useState<AlertTexts | null>(null); // Task 20: what people nearby will get
  const isStaff = user?.role === "verifier" || user?.role === "admin";

  // Show what fetchReview found (called when the answer arrives, never directly in the effect)
  const show = useCallback((found: Found) => {
    setReport(found.report);
    setClaimProblem(found.claimProblem);
    setProblem(found.problem);
  }, []);

  useEffect(() => {
    if (!isStaff) return;
    let current = true;
    fetchReview(id).then((found) => current && show(found));
    return () => { current = false; };
  }, [isStaff, id, show]);

  const renew = () => fetchReview(id).then(show);

  async function backToQueue() {
    if (report?.claim?.mine) await api(`/review/${id}/release`, { method: "POST" }).catch(() => {});
    router.push("/review");
  }

  if (loading || (isStaff && !report && !problem)) {
    return <div className="grid h-[60vh] place-items-center"><LoaderCircle className="animate-spin text-ink-soft" /></div>;
  }
  if (!isStaff) return <p className="mx-auto mt-10 max-w-md text-center text-ink">{t("review_only_staff")}</p>;
  if (!report) return <p role="alert" className="mx-auto mt-10 max-w-md rounded-2xl bg-red-50 p-4 text-center text-red-800">{problem}</p>;
  if (decided) return <Decided status={decided} />;

  const station = report.gd.police_station;
  return (
    <div className="mx-auto max-w-6xl px-4 pt-6">
      {/* Top bar: back + claim status */}
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <button onClick={backToQueue} className="inline-flex items-center gap-1.5 rounded-full px-3 py-2 text-sm text-ink-soft hover:text-ink">
          <ArrowLeft size={16} aria-hidden /> {t("review_back")}
        </button>
        {report.claim?.mine ? (
          <ClaimTimer until={report.claim.until} onRenew={renew} />
        ) : (
          <p className="inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-4 py-2 text-sm text-amber-900">
            <Lock size={15} aria-hidden /> {claimProblem || t("review_read_only")}
          </p>
        )}
      </div>

      <header className="rise mb-6">
        <p className="text-xs tracking-wide text-ink-soft uppercase">{t(report.status === "PENDING_REVIEW" ? "status_pending" : "status_needs_info")}</p>
        <h1 className="mt-1 text-3xl font-semibold text-ink md:text-4xl">{lang === "bn" ? report.theft_name_bn : report.theft_name_en}</h1>
        <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-soft">
          <span className="inline-flex items-center gap-1"><MapPin size={14} aria-hidden />
            {report.thana ? areaName(report.thana, lang) : "—"}{report.ward && ` · ${areaName(report.ward, lang)}`}
            {report.landmark && ` · ${report.landmark}`}</span>
          <span className="inline-flex items-center gap-1"><CalendarClock size={14} aria-hidden /> {dhakaTime(report.occurred_at, lang)}</span>
        </p>
      </header>

      {report.info_answer && (
        <p className="rise mb-6 flex items-start gap-3 rounded-[1.5rem] bg-violet-50 p-4 text-sm text-violet-950">
          <MessageCircleReply size={18} className="mt-0.5 shrink-0" aria-hidden />
          <span><strong>{t("review_victim_answered")}</strong> {report.info_answer}
            {report.info_request && <span className="mt-1 block text-xs text-violet-800">{t("review_you_asked")} {report.info_request}</span>}</span>
        </p>
      )}

      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        {/* ---------- left ---------- */}
        <div className="space-y-6">
          <Panel title={t("review_place")}>
            <PlaceMap lat={report.lat} lng={report.lng}
                      station={station ? { lat: station.lat, lng: station.lng, name: areaName(station, lang) } : null} />
            <p className="mt-2 text-xs text-ink-soft">{t("review_place_note")}</p>
          </Panel>

          <Panel title={`${t("photos_title")} (${report.photos.length})`}>
            {report.photos.length ? (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {report.photos.map((p) => (
                  <button key={p.id} onClick={() => setBig(p)} className="relative aspect-square overflow-hidden rounded-2xl bg-bg-soft">
                    {/* eslint-disable-next-line @next/next/no-img-element -- private photo served by our backend */}
                    <img src={p.url} alt="" className="size-full object-cover transition hover:scale-105" />
                    {p.kind === "gd_copy" && <span className="absolute inset-x-0 bottom-0 bg-black/60 py-1 text-center text-xs text-white">{t("photo_gd_short")}</span>}
                  </button>
                ))}
              </div>
            ) : <p className="text-sm text-ink-soft">{t("review_no_photos")}</p>}
          </Panel>

          {report.ocr && <Panel title={t("ocr_title")}><OcrCompare ocr={report.ocr} /></Panel>}

          <Panel title={t("review_story")}>
            <dl className="grid gap-4 text-sm sm:grid-cols-2">
              <Fact label={t("my_reports_items")} value={report.stolen_items || "—"} />
              <Fact label={t("my_reports_sent")} value={dhakaTime(report.submitted_at, lang)} />
            </dl>
            <p className="mt-4 rounded-2xl bg-bg-soft p-4 text-sm whitespace-pre-line text-ink">{report.description || t("review_no_story")}</p>
          </Panel>
        </div>

        {/* ---------- right ---------- */}
        <aside className="space-y-6">
          <Panel title={t("risk_score")}><RiskMeter risk={report.risk} /></Panel>
          <Panel title={t("review_checks")}><ChecksList checks={report.checks} /></Panel>
          <Panel title={report.gd.type}>
            <dl className="grid grid-cols-2 gap-4 text-sm">
              <Fact label={t("report_gd_number")} value={`#${report.gd.number}`} />
              <Fact label={t("report_gd_date")} value={dhakaTime(report.gd.date, lang, false)} />
              <div className="col-span-2"><Fact label={t("my_reports_station")} value={station ? areaName(station, lang) : "—"} /></div>
            </dl>
          </Panel>
          {report.reporter && (
            <Panel title={t("review_reporter")}>
              <ul className="space-y-2 text-sm text-ink">
                <li className="flex items-center gap-2"><ShieldCheck size={16} className="text-primary" aria-hidden />
                  {t("review_account_age").replace("{n}", String(report.reporter.account_days))}</li>
                <li className="flex items-center gap-2"><IdCard size={16} className="text-primary" aria-hidden />
                  {report.reporter.nid_added ? `${t("nid_done")} · ••••${report.reporter.nid_last4}` : t("review_no_nid")}</li>
                <li className="text-ink-soft">
                  {t("review_history").replace("{all}", String(report.reporter.other_reports))
                    .replace("{ok}", String(report.reporter.verified_reports)).replace("{bad}", String(report.reporter.rejected_reports))}
                </li>
              </ul>
              <p className="mt-3 text-xs text-ink-soft">{t("review_privacy")}</p>
            </Panel>
          )}
          {report.status === "PENDING_REVIEW" && (
            <Panel title={t("alert_title")}>
              <AlertPreview reportId={report.id} value={alertTexts} onChange={setAlertTexts} canEdit={!!report.claim?.mine} />
            </Panel>
          )}
          <DecisionBar report={report} onDecided={setDecided} alertTexts={alertTexts} />
          <Panel title={t("review_timeline")}><Timeline steps={report.timeline} /></Panel>
        </aside>
      </div>

      {big && createPortal(
        <div role="dialog" aria-modal="true" onClick={() => setBig(null)}
             className="fixed inset-0 z-50 grid place-items-center bg-black/85 p-4 backdrop-blur-sm">
          {/* eslint-disable-next-line @next/next/no-img-element -- private photo served by our backend */}
          <img src={big.url} alt="" className="max-h-[88vh] max-w-full rounded-2xl shadow-2xl" />
          <button onClick={() => setBig(null)} aria-label={t("close")}
                  className="absolute top-5 right-5 grid size-10 place-items-center rounded-full bg-white text-neutral-900"><X size={18} /></button>
        </div>,
        document.body,
      )}
      <p className="mt-8 text-center text-xs text-ink-soft"><Link href="/review" className="hover:underline">{t("review_title")}</Link></p>
    </div>
  );
}

type Found = { report: ReviewDetail | null; claimProblem: string; problem: string };

/** After a decision: a short "done" card, then back to the queue. */
function Decided({ status }: { status: string }) {
  const { t } = usePrefs();
  const router = useRouter();
  useEffect(() => {
    const timer = setTimeout(() => router.push("/review"), 2200);
    return () => clearTimeout(timer);
  }, [router]);
  const word = status === "VERIFIED" ? t("decided_approved") : status === "REJECTED" ? t("decided_rejected") : t("decided_asked");
  return (
    <div className="mx-auto mt-16 max-w-md px-4 text-center">
      <span className="rise mx-auto grid size-20 place-items-center rounded-full bg-primary/15 text-primary"><CircleCheck size={44} aria-hidden /></span>
      <h1 className="mt-5 text-2xl font-semibold text-ink">{word}</h1>
      <p className="mt-2 text-sm text-ink-soft">{t("decided_back")}</p>
    </div>
  );
}

/** Claim the report (FR-14), then load it. If someone else holds it, we still load it, read-only. */
async function fetchReview(id: string): Promise<Found> {
  let claimProblem = "";
  try {
    await api(`/review/${id}/claim`, { method: "POST" });
  } catch (e) {
    const error = e as ApiError;
    if (error.code !== "claimed_by_other" && error.code !== "not_reviewable") {
      return { report: null, claimProblem: "", problem: error.message };
    }
    claimProblem = error.message;
  }
  try {
    return { report: await api<ReviewDetail>(`/review/${id}`), claimProblem, problem: "" };
  } catch (e) {
    return { report: null, claimProblem, problem: (e as ApiError).message };
  }
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rise soft-shadow rounded-[1.5rem] bg-surface p-5">
      <h2 className="mb-3 text-sm font-semibold tracking-wide text-ink-soft uppercase">{title}</h2>
      {children}
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-soft">{label}</dt>
      <dd className="text-ink">{value}</dd>
    </div>
  );
}

/** "Yours for 14:32" counting down; at 2 minutes left it offers "Keep it". */
function ClaimTimer({ until, onRenew }: { until: string; onRenew: () => void }) {
  const { t } = usePrefs();
  const [left, setLeft] = useState(() => new Date(until).getTime() - Date.now());
  useEffect(() => {
    const timer = setInterval(() => setLeft(new Date(until).getTime() - Date.now()), 1000);
    return () => clearInterval(timer);
  }, [until]);
  const seconds = Math.max(0, Math.round(left / 1000));
  const text = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  return (
    <p className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm ${seconds < 120 ? "bg-amber-100 text-amber-900" : "bg-primary/15 text-ink"}`}>
      <Timer size={15} aria-hidden /> {t("review_yours_for")} {text}
      {seconds < 120 && <button onClick={onRenew} className="font-semibold underline">{t("review_keep")}</button>}
    </p>
  );
}
