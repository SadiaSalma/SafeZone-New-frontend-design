"use client";
/**
 * Frontend (web) · Task 19 · AnswerForm.tsx - "The verifier asks: …" -> the victim answers.
 *
 * Shown on "My reports" for a report with "More information needed". The victim writes an answer
 * and, if the question was about the GD, can correct the GD number / date / police station.
 * Sending it puts the report back in the review queue (Design Revisions R7).
 *
 * Data: PUT /api/v1/me/reports/{id} (Task 19 backend); police stations from /reports/options.
 */
import { useState } from "react";
import { LoaderCircle, Send } from "lucide-react";
import { usePrefs } from "@/components/PreferencesProvider";
import { api, ApiError } from "@/lib/api";
import { areaName } from "@/lib/areas";
import type { Report, ReportOptions } from "@/lib/reports";

const INPUT = "w-full rounded-2xl border border-line bg-bg px-4 py-2.5 text-sm text-ink focus:border-primary focus:outline-none";

export function AnswerForm({ report, onChanged }: { report: Report; onChanged: (r: Report) => void }) {
  const { t, lang } = usePrefs();
  const [answer, setAnswer] = useState("");
  const [fixGd, setFixGd] = useState(false);
  const [gd, setGd] = useState({ number: report.gd.number, date: report.gd.date, police_station: report.gd.police_station?.code ?? "" });
  const [stations, setStations] = useState<ReportOptions["police_stations"]>([]);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");

  function openGd() {
    setFixGd(!fixGd);
    if (!stations.length) api<ReportOptions>("/reports/options").then((o) => setStations(o.police_stations)).catch(() => {});
  }

  async function send() {
    setBusy(true);
    setProblem("");
    try {
      const body = { answer, ...(fixGd ? { gd: { type: report.gd.type, ...gd } } : {}) };
      onChanged(await api<Report>(`/me/reports/${report.id}`, { method: "PUT", body }));
    } catch (e) {
      const error = e as ApiError;
      setProblem(Object.values(error.fields ?? {})[0] ?? error.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-4 rounded-2xl border border-sky-200 bg-sky-50/60 p-4">
      <label htmlFor={`answer-${report.id}`} className="text-sm font-semibold text-sky-900">{t("answer_title")}</label>
      <textarea id={`answer-${report.id}`} rows={3} maxLength={1000} value={answer} onChange={(e) => setAnswer(e.target.value)}
                placeholder={t("answer_hint")} className={`${INPUT} mt-2`} />
      <button type="button" onClick={openGd} className="mt-2 text-xs font-medium text-sky-900 underline underline-offset-2">
        {fixGd ? t("answer_keep_gd") : t("answer_fix_gd")}
      </button>
      {fixGd && (
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <input aria-label={t("report_gd_number")} className={INPUT} value={gd.number} maxLength={30}
                 onChange={(e) => setGd({ ...gd, number: e.target.value })} />
          <input aria-label={t("report_gd_date")} type="date" className={INPUT} value={gd.date}
                 onChange={(e) => setGd({ ...gd, date: e.target.value })} />
          <select aria-label={t("my_reports_station")} className={INPUT} value={gd.police_station}
                  onChange={(e) => setGd({ ...gd, police_station: e.target.value })}>
            {stations.length === 0 && report.gd.police_station && (
              <option value={report.gd.police_station.code}>{areaName(report.gd.police_station, lang)}</option>
            )}
            {stations.map((s) => <option key={s.code} value={s.code}>{areaName(s, lang)}</option>)}
          </select>
        </div>
      )}
      {problem && <p role="alert" className="mt-2 text-xs text-red-700">{problem}</p>}
      <div className="mt-3 flex justify-end">
        <button onClick={send} disabled={busy || answer.trim().length < 3}
                className="inline-flex items-center gap-2 rounded-full bg-sky-700 px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-40">
          {busy ? <LoaderCircle size={16} className="animate-spin" aria-hidden /> : <Send size={15} aria-hidden />} {t("answer_send")}
        </button>
      </div>
    </div>
  );
}
