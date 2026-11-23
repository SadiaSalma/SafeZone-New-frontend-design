"use client";
/**
 * Frontend (web) · Task 14 · /me/reports - "My reports".
 *
 * Shows every report the logged-in person sent, newest first, with:
 *  - a coloured status pill and a small progress line (Sent -> Reviewed -> Alert sent)
 *  - what, when, where (thana · ward) and the GD details
 *  - "Withdraw" for reports nobody has decided on yet (asks "Are you sure?" first)
 *
 * Data: GET /api/v1/me/reports, POST /api/v1/me/reports/{id}/withdraw (Task 14 backend).
 */
import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { CalendarClock, FileText, IdCard, LoaderCircle, MapPin, Plus, Trash2, Undo2 } from "lucide-react";
import rainRickshaw from "@/public/images/myreports-rain-rickshaw.jpg";
import { useAuth } from "@/components/AuthProvider";
import { AnswerForm } from "@/components/report/AnswerForm";
import { ReportPhotos } from "@/components/report/ReportPhotos";
import { usePrefs } from "@/components/PreferencesProvider";
import { api, ApiError } from "@/lib/api";
import { areaName } from "@/lib/areas";
import { dhakaTime, STATUS_LOOK, type Report } from "@/lib/reports";

export default function MyReportsPage() {
  const { t } = usePrefs();
  const { user, loading } = useAuth();
  const [reports, setReports] = useState<Report[] | null>(null);
  const [problem, setProblem] = useState("");

  const load = useCallback(() => {
    api<{ reports: Report[] }>("/me/reports")
      .then((answer) => setReports(answer.reports))
      .catch((e: ApiError) => setProblem(e.message));
  }, []);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  return (
    <>
      <section data-photo-hero className="relative -mt-16 h-[34svh] min-h-[280px] overflow-hidden bg-black">
        <Image src={rainRickshaw} alt="A rickshaw rider pedalling through heavy rain on a Dhaka street" fill preload
               placeholder="blur" sizes="100vw" className="drift object-cover" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/55 via-black/30 to-bg" />
        <div className="rise relative mx-auto flex h-full max-w-3xl items-end justify-between gap-4 px-4 pb-10 text-white">
          <div>
            <h1 className="text-4xl font-semibold md:text-5xl">{t("my_reports")}</h1>
            <p className="mt-2 text-white/80">{t("my_reports_sub")}</p>
          </div>
          {user && (
            <Link href="/report/new"
                  className="hidden shrink-0 items-center gap-2 rounded-full bg-white px-5 py-2.5 text-sm font-semibold text-neutral-900 shadow-lg transition hover:scale-[1.03] sm:inline-flex">
              <Plus size={18} aria-hidden /> {t("new_report")}
            </Link>
          )}
        </div>
      </section>

      <section className="mx-auto -mt-4 max-w-3xl space-y-4 px-4">
        {loading || (user && reports === null && !problem) ? (
          <div className="grid h-40 place-items-center"><LoaderCircle className="animate-spin text-ink-soft" /></div>
        ) : !user ? (
          <Card>
            <p className="text-ink">{t("my_reports_login")}</p>
            <Link href="/login" className="mt-4 inline-flex rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-on-primary">
              {t("login")}
            </Link>
          </Card>
        ) : (
          <>
            {!user.nid_added && (
              <Card className="flex items-center gap-4 border border-amber-300/60 bg-amber-50">
                <IdCard className="shrink-0 text-amber-700" aria-hidden />
                <p className="flex-1 text-sm text-amber-900">{t("my_reports_nid")}</p>
                <Link href="/me/nid" className="shrink-0 rounded-full bg-amber-600 px-4 py-2 text-sm font-semibold text-white">
                  {t("nid_add_link")}
                </Link>
              </Card>
            )}
            {problem && <p role="alert" className="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-800">{problem}</p>}
            {reports?.length === 0 && (
              <Card className="text-center">
                <FileText size={40} className="mx-auto text-primary" aria-hidden />
                <p className="mt-3 font-medium text-ink">{t("my_reports_empty")}</p>
                <p className="mt-1 text-sm text-ink-soft">{t("my_reports_empty_sub")}</p>
                <Link href="/report/new" className="mt-5 inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-on-primary">
                  <Plus size={18} aria-hidden /> {t("new_report")}
                </Link>
              </Card>
            )}
            {reports?.map((report) => (
              <ReportCard key={report.id} report={report}
                          onChanged={(updated) => setReports((all) => all!.map((r) => (r.id === updated.id ? updated : r)))} />
            ))}
            {/* Task 31: a quiet link at the bottom - deleting is possible, but never one tap away */}
            {user.role === "victim" && (
              <p className="pt-4 text-center">
                <Link href="/me/delete" className="inline-flex items-center gap-1.5 text-sm text-ink-soft hover:text-red-700">
                  <Trash2 size={14} aria-hidden /> {t("del_link")}
                </Link>
              </p>
            )}
          </>
        )}
      </section>
    </>
  );
}

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`soft-shadow rounded-[1.75rem] bg-surface p-6 ${className}`}>{children}</div>;
}

function ReportCard({ report, onChanged }: { report: Report; onChanged: (r: Report) => void }) {
  const { t, lang } = usePrefs();
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const look = STATUS_LOOK[report.status];

  async function withdraw() {
    setBusy(true);
    setProblem("");
    try {
      onChanged(await api<Report>(`/me/reports/${report.id}/withdraw`, { method: "POST" }));
      setAsking(false);
    } catch (e) {
      setProblem((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="rise soft-shadow rounded-[1.75rem] bg-surface p-5 md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-ink">{lang === "bn" ? report.theft_name_bn : report.theft_name_en}</h2>
          <p className="mt-1 flex items-center gap-1.5 text-sm text-ink-soft">
            <MapPin size={14} aria-hidden />
            {report.thana ? areaName(report.thana, lang) : "—"}
            {report.ward && ` · ${areaName(report.ward, lang)}`}
            {report.landmark && ` · ${report.landmark}`}
          </p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${look.pill}`}>{t(look.label)}</span>
      </div>

      {/* Progress: Sent -> Reviewed -> Alert sent (closed reports show no progress) */}
      {look.step > 0 && (
        <ol className="mt-5 grid grid-cols-3 gap-2" aria-label={t("my_reports_progress")}>
          {(["progress_sent", "progress_reviewed", "progress_alerted"] as const).map((key, i) => (
            <li key={key} className="flex flex-col gap-1.5">
              <span className={`h-1.5 rounded-full ${i < look.step ? "bg-primary" : "bg-line"}`} />
              <span className={`text-[11px] ${i < look.step ? "text-ink" : "text-ink-soft"}`}>{t(key)}</span>
            </li>
          ))}
        </ol>
      )}

      {report.status === "NEEDS_INFO" && report.info_request && (
        <>
          <p className="mt-4 rounded-2xl bg-sky-50 px-4 py-3 text-sm text-sky-900">
            <strong>{t("my_reports_question")}</strong> {report.info_request}
          </p>
          <AnswerForm report={report} onChanged={onChanged} />
        </>
      )}
      {report.alert?.status === "sent" && (
        <p className="mt-4 rounded-2xl bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          {t("my_reports_alerted").replace("{n}", report.alert.phones.toLocaleString())}
        </p>
      )}
      {report.status === "REJECTED" && report.reject_reason && (
        <p className="mt-4 rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-900">
          <strong>{t("my_reports_reason")}</strong> {report.reject_reason}
        </p>
      )}

      <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="flex items-center gap-1 text-xs text-ink-soft"><CalendarClock size={13} aria-hidden /> {t("my_reports_when")}</dt>
          <dd className="text-ink">{dhakaTime(report.occurred_at, lang)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-soft">{report.gd.type}</dt>
          <dd className="text-ink">#{report.gd.number} · {dhakaTime(report.gd.date, lang, false)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-soft">{t("my_reports_station")}</dt>
          <dd className="text-ink">{report.gd.police_station ? areaName(report.gd.police_station, lang) : "—"}</dd>
        </div>
      </dl>
      {report.stolen_items && <p className="mt-3 text-sm text-ink-soft">{t("my_reports_items")}: {report.stolen_items}</p>}
      <ReportPhotos report={report} onChanged={onChanged} />

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
        <p className="text-xs text-ink-soft">{t("my_reports_sent")} {dhakaTime(report.submitted_at, lang)}</p>
        {report.can_withdraw && !asking && (
          <button onClick={() => setAsking(true)}
                  className="inline-flex items-center gap-1.5 rounded-full border border-line px-4 py-2 text-sm text-ink hover:border-red-400 hover:text-red-700">
            <Undo2 size={15} aria-hidden /> {t("withdraw")}
          </button>
        )}
        {asking && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-ink">{t("withdraw_sure")}</span>
            <button onClick={withdraw} disabled={busy}
                    className="inline-flex items-center gap-1.5 rounded-full bg-red-600 px-4 py-2 font-semibold text-white disabled:opacity-70">
              {busy && <LoaderCircle size={15} className="animate-spin" aria-hidden />} {t("withdraw_yes")}
            </button>
            <button onClick={() => setAsking(false)} className="rounded-full px-3 py-2 text-ink-soft hover:text-ink">{t("keep")}</button>
          </div>
        )}
      </div>
      {problem && <p role="alert" className="mt-3 text-sm text-red-700">{problem}</p>}
    </article>
  );
}
