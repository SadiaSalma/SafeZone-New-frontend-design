"use client";
/**
 * Frontend (web) · Task 19 · DecisionBar.tsx - the verifier's three decisions (FR-15):
 *
 *   Approve       - asks "are you sure?" and explains what happens (public pin moved 100-200 m,
 *                   people nearby get the alert). Disabled while a check has FAILED.
 *   Ask for info  - a question for the victim (quick ready-made questions to pick from)
 *   Reject        - a reason is required (ready-made reasons + your own words)
 *
 * Only usable while YOU hold the report (the claim from Task 18).
 * Task 20: approving sends the alert text from AlertPreview (the template, or the edited text if it is safe).
 * Data: POST /api/v1/review/{id}/approve | /ask-info | /reject (Task 19 backend).
 */
import { useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { CircleCheck, CircleX, LoaderCircle, MessageCircleQuestion, X } from "lucide-react";
import { usePrefs } from "@/components/PreferencesProvider";
import { api, ApiError } from "@/lib/api";
import type { TextKey } from "@/lib/i18n";
import type { ReviewDetail } from "@/lib/review";
import type { AlertTexts } from "@/components/review/AlertPreview";

type Kind = "approve" | "ask" | "reject";
const QUESTIONS: TextKey[] = ["ask_q_gd_copy", "ask_q_gd_number", "ask_q_place", "ask_q_items"];

export function DecisionBar({ report, onDecided, alertTexts }: {
  report: ReviewDetail; onDecided: (status: string) => void; alertTexts?: AlertTexts | null;
}) {
  const { t } = usePrefs();
  const [open, setOpen] = useState<Kind | null>(null);
  const canDecide = !!report.claim?.mine && report.status === "PENDING_REVIEW";
  const failed = report.checks.some((c) => c.result === "fail");
  const unsafeText = !!alertTexts?.edited && !alertTexts.safe; // Task 20: fix the alert text first

  return (
    <section className="soft-shadow rounded-[1.5rem] bg-surface p-5">
      <h2 className="mb-3 text-sm font-semibold tracking-wide text-ink-soft uppercase">{t("decide_title")}</h2>
      {!canDecide && <p className="mb-3 text-sm text-ink-soft">{t("decide_need_claim")}</p>}
      <div className="grid gap-2">
        <button disabled={!canDecide || failed || unsafeText} onClick={() => setOpen("approve")}
                className="inline-flex items-center justify-center gap-2 rounded-full bg-emerald-600 px-5 py-3 text-sm font-semibold text-white shadow transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-40">
          <CircleCheck size={18} aria-hidden /> {t("decide_approve")}
        </button>
        {failed && <p className="text-xs text-red-700">{t("decide_failed_blocks")}</p>}
        {unsafeText && <p className="text-xs text-red-700">{t("alert_fix_first")}</p>}
        <button disabled={!canDecide} onClick={() => setOpen("ask")}
                className="inline-flex items-center justify-center gap-2 rounded-full border border-sky-300 bg-sky-50 px-5 py-3 text-sm font-semibold text-sky-900 transition hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-40">
          <MessageCircleQuestion size={18} aria-hidden /> {t("decide_ask")}
        </button>
        <button disabled={!canDecide} onClick={() => setOpen("reject")}
                className="inline-flex items-center justify-center gap-2 rounded-full border border-red-300 bg-red-50 px-5 py-3 text-sm font-semibold text-red-800 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-40">
          <CircleX size={18} aria-hidden /> {t("decide_reject")}
        </button>
      </div>
      {open && <Dialog kind={open} report={report} alertTexts={alertTexts} onClose={() => setOpen(null)} onDecided={onDecided} />}
    </section>
  );
}

function Dialog({ kind, report, alertTexts, onClose, onDecided }: {
  kind: Kind; report: ReviewDetail; alertTexts?: AlertTexts | null; onClose: () => void; onDecided: (s: string) => void;
}) {
  const { t, lang } = usePrefs();
  const [note, setNote] = useState("");
  const [question, setQuestion] = useState("");
  const [reasonCode, setReasonCode] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");

  async function send() {
    setBusy(true);
    setProblem("");
    try {
      const path = kind === "approve" ? "approve" : kind === "ask" ? "ask-info" : "reject";
      const edited = alertTexts?.edited ? { text_en: alertTexts.text_en, text_bn: alertTexts.text_bn } : {};
      const body = kind === "approve" ? { note, ...edited } : kind === "ask" ? { question } : { reason_code: reasonCode, reason };
      const answer = await api<{ status: string }>(`/review/${report.id}/${path}`, { method: "POST", body });
      onDecided(answer.status);
    } catch (e) {
      const error = e as ApiError;
      setProblem(Object.values(error.fields ?? {})[0] ?? error.message);
    } finally {
      setBusy(false);
    }
  }

  const ready = kind === "approve" || (kind === "ask" ? question.trim().length >= 10 : !!reasonCode && (reasonCode !== "other" || reason.trim().length >= 5));
  const look: Record<Kind, { title: TextKey; button: TextKey; colour: string }> = {
    approve: { title: "decide_approve_title", button: "decide_approve", colour: "bg-emerald-600 hover:bg-emerald-700" },
    ask: { title: "decide_ask_title", button: "decide_ask_send", colour: "bg-sky-600 hover:bg-sky-700" },
    reject: { title: "decide_reject_title", button: "decide_reject", colour: "bg-red-600 hover:bg-red-700" },
  };

  let body: ReactNode;
  if (kind === "approve") {
    body = (
      <>
        <ul className="list-disc space-y-1.5 pl-5 text-sm text-ink">
          <li>{t("decide_approve_1")}</li>
          <li>{t("decide_approve_2")}</li>
          <li>{t("decide_approve_3")}</li>
        </ul>
        <label className="mt-4 block text-sm font-medium text-ink" htmlFor="note">{t("decide_note")}</label>
        <textarea id="note" rows={2} maxLength={300} value={note} onChange={(e) => setNote(e.target.value)}
                  placeholder={t("decide_note_hint")}
                  className="mt-1 w-full rounded-2xl border border-line bg-bg px-4 py-3 text-sm text-ink focus:border-primary focus:outline-none" />
      </>
    );
  } else if (kind === "ask") {
    body = (
      <>
        <div className="mb-3 flex flex-wrap gap-2">
          {QUESTIONS.map((q) => (
            <button key={q} type="button" onClick={() => setQuestion(t(q))}
                    className="rounded-full border border-line px-3 py-1.5 text-xs text-ink hover:border-primary">{t(q)}</button>
          ))}
        </div>
        <textarea rows={4} maxLength={500} value={question} onChange={(e) => setQuestion(e.target.value)} autoFocus
                  placeholder={t("decide_ask_hint")} aria-label={t("decide_ask_title")}
                  className="w-full rounded-2xl border border-line bg-bg px-4 py-3 text-sm text-ink focus:border-primary focus:outline-none" />
        <p className="mt-1 text-xs text-ink-soft">{t("decide_ask_note")}</p>
      </>
    );
  } else {
    body = (
      <>
        <div className="grid gap-2">
          {report.reject_reasons.map((r) => (
            <label key={r.code} className={`flex cursor-pointer items-center gap-3 rounded-2xl border px-4 py-2.5 text-sm ${
              reasonCode === r.code ? "border-red-400 bg-red-50 text-red-900" : "border-line text-ink"}`}>
              <input type="radio" name="reason" value={r.code} checked={reasonCode === r.code} onChange={() => setReasonCode(r.code)}
                     className="accent-red-600" />
              {lang === "bn" ? t(`reject_${r.code}` as TextKey) : r.text}
            </label>
          ))}
        </div>
        <textarea rows={3} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)}
                  placeholder={t("decide_reject_hint")} aria-label={t("decide_reject_hint")}
                  className="mt-3 w-full rounded-2xl border border-line bg-bg px-4 py-3 text-sm text-ink focus:border-primary focus:outline-none" />
        <p className="mt-1 text-xs text-ink-soft">{t("decide_reject_note")}</p>
      </>
    );
  }

  return createPortal(
    <div role="dialog" aria-modal="true" aria-labelledby="decision-title"
         className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="rise w-full max-w-lg rounded-[1.75rem] bg-surface p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 id="decision-title" className="text-xl font-semibold text-ink">{t(look[kind].title)}</h2>
          <button onClick={onClose} aria-label={t("close")} className="text-ink-soft hover:text-ink"><X size={20} /></button>
        </div>
        {body}
        {problem && <p role="alert" className="mt-3 rounded-2xl bg-red-50 px-4 py-2.5 text-sm text-red-800">{problem}</p>}
        <div className="mt-6 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-full px-5 py-2.5 text-sm text-ink-soft hover:text-ink">{t("cancel")}</button>
          <button onClick={send} disabled={!ready || busy}
                  className={`inline-flex items-center gap-2 rounded-full px-6 py-2.5 text-sm font-semibold text-white disabled:opacity-40 ${look[kind].colour}`}>
            {busy && <LoaderCircle size={16} className="animate-spin" aria-hidden />} {t(look[kind].button)}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
