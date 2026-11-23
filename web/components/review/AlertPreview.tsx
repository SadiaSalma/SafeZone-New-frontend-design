"use client";
/**
 * Frontend (web) · Task 20 · AlertPreview.tsx - what people nearby will receive, before approving.
 *
 *  - a phone-style message bubble in English and Bangla (switch with the two tabs)
 *  - "Edit text" opens both texts; every change is privacy-checked half a second later
 *    (phone numbers, emails, GD numbers, house numbers, the victim's name, blaming words)
 *  - problems are highlighted in the text and listed underneath; approval is blocked until fixed
 *
 * Data: GET /api/v1/review/{id}/alert-preview, POST /api/v1/review/{id}/alert-check (Task 20 backend).
 */
import { useEffect, useState } from "react";
import { BellRing, CircleCheck, Pencil, RotateCcw, ShieldAlert } from "lucide-react";
import { usePrefs } from "@/components/PreferencesProvider";
import { api } from "@/lib/api";

export type AlertTexts = { text_en: string; text_bn: string; edited: boolean; safe: boolean };
type Problem = { code: string; match: string; message: string };
type Problems = { en: Problem[]; bn: Problem[] };

export function AlertPreview({ reportId, value, onChange, canEdit }: {
  reportId: string; value: AlertTexts | null; onChange: (v: AlertTexts) => void; canEdit: boolean;
}) {
  const { t } = usePrefs();
  const [original, setOriginal] = useState<{ text_en: string; text_bn: string } | null>(null);
  const [radius, setRadius] = useState(1000);
  const [lang, setLang] = useState<"en" | "bn">("en");
  const [editing, setEditing] = useState(false);
  const [problems, setProblems] = useState<Problems>({ en: [], bn: [] });

  // The template text, once
  useEffect(() => {
    api<{ text_en: string; text_bn: string; radius_m: number }>(`/review/${reportId}/alert-preview`).then((p) => {
      setOriginal({ text_en: p.text_en, text_bn: p.text_bn });
      setRadius(p.radius_m);
      onChange({ text_en: p.text_en, text_bn: p.text_bn, edited: false, safe: true });
    }).catch(() => {});
  }, [reportId, onChange]);

  // Privacy-check edited texts half a second after typing stops
  const en = value?.text_en ?? "";
  const bn = value?.text_bn ?? "";
  useEffect(() => {
    if (!value?.edited) return;
    const timer = setTimeout(() => {
      api<{ ok: boolean; problems: Problems }>(`/review/${reportId}/alert-check`, { method: "POST", body: { text_en: en, text_bn: bn } })
        .then((answer) => {
          setProblems(answer.problems);
          onChange({ text_en: en, text_bn: bn, edited: true, safe: answer.ok });
        })
        .catch(() => {});
    }, 500);
    return () => clearTimeout(timer);
  }, [en, bn, value?.edited, reportId, onChange]);

  if (!value || !original) return <div className="h-40 animate-pulse rounded-2xl bg-bg-soft" />;
  const text = lang === "en" ? value.text_en : value.text_bn;
  const shown = value.edited ? problems : { en: [], bn: [] };
  const allProblems = [...shown.en, ...shown.bn];

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="inline-flex rounded-full bg-bg-soft p-1 text-xs">
          {(["en", "bn"] as const).map((l) => (
            <button key={l} onClick={() => setLang(l)}
                    className={`rounded-full px-3 py-1 ${lang === l ? "bg-surface font-semibold text-ink shadow" : "text-ink-soft"}`}>
              {l === "en" ? "English" : "বাংলা"}
            </button>
          ))}
        </div>
        <span className="text-xs text-ink-soft">{t("alert_radius").replace("{km}", (radius / 1000).toFixed(1))}</span>
      </div>

      {/* The phone-style message */}
      <div className="rounded-[1.75rem] bg-neutral-900 p-3 shadow-inner">
        <div className="rounded-2xl bg-neutral-800 p-3 text-white">
          <p className="mb-1.5 flex items-center gap-1.5 text-[11px] text-white/60">
            <BellRing size={12} aria-hidden /> SafeZone · {t("alert_now")}
          </p>
          <p className="text-sm leading-relaxed"><Highlighted text={text} problems={shown[lang]} /></p>
        </div>
      </div>

      {value.edited && (
        allProblems.length ? (
          <ul className="mt-3 space-y-1 rounded-2xl bg-red-50 p-3 text-xs text-red-900" role="alert">
            {allProblems.map((p, i) => (
              <li key={i} className="flex items-start gap-1.5"><ShieldAlert size={13} className="mt-0.5 shrink-0" aria-hidden />
                <span><strong>{p.match || "—"}</strong> · {p.message}</span></li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 inline-flex items-center gap-1.5 text-xs text-emerald-700"><CircleCheck size={14} aria-hidden /> {t("alert_safe")}</p>
        )
      )}

      {canEdit && (
        <div className="mt-3 flex flex-wrap gap-2">
          <button onClick={() => setEditing(!editing)}
                  className="inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 text-xs text-ink hover:border-primary">
            <Pencil size={13} aria-hidden /> {editing ? t("alert_done_editing") : t("alert_edit")}
          </button>
          {value.edited && (
            <button onClick={() => { onChange({ ...original, edited: false, safe: true }); setProblems({ en: [], bn: [] }); setEditing(false); }}
                    className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs text-ink-soft hover:text-ink">
              <RotateCcw size={13} aria-hidden /> {t("alert_reset")}
            </button>
          )}
        </div>
      )}
      {editing && (
        <div className="mt-3 grid gap-2">
          {(["text_en", "text_bn"] as const).map((key) => (
            <textarea key={key} rows={4} maxLength={600} value={value[key]} aria-label={key === "text_en" ? "English" : "বাংলা"}
                      onChange={(e) => onChange({ ...value, [key]: e.target.value, edited: true, safe: false })}
                      className="w-full rounded-2xl border border-line bg-bg px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none" />
          ))}
        </div>
      )}
    </div>
  );
}

/** The text with every problem part marked in red. */
function Highlighted({ text, problems }: { text: string; problems: Problem[] }) {
  const words = problems.map((p) => p.match).filter(Boolean);
  if (!words.length) return <>{text}</>;
  const pattern = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return (
    <>
      {text.split(pattern).map((part, i) =>
        words.some((w) => w.toLowerCase() === part.toLowerCase())
          ? <mark key={i} className="rounded bg-red-500/80 px-0.5 text-white">{part}</mark>
          : <span key={i}>{part}</span>)}
    </>
  );
}
