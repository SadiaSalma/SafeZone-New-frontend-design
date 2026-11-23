"use client";
/**
 * Frontend (web) · Task 17 · SendTips.tsx - "Before you send" tips on the last step of the report form.
 *
 * It asks the backend to run the SAFE automatic checks on the form (nothing is saved):
 *   - does the GD number look right?
 *   - was the GD filed soon after the theft?
 *   - is the place inside the GD police station's thana?
 *   - is there a photo of the GD copy?
 * and shows what could slow down the review, so the victim can fix it first.
 * (The risk score itself is only for verifiers and is never shown here.)
 *
 * Data: POST /api/v1/reports/precheck (Task 17 backend).
 */
import { useEffect, useState } from "react";
import { CircleCheck, Lightbulb, LoaderCircle } from "lucide-react";
import { usePrefs } from "@/components/PreferencesProvider";
import { api } from "@/lib/api";

type Tip = { code: string; message: string; message_bn: string };

export function SendTips({ body, hasGdCopy }: { body: object; hasGdCopy: boolean }) {
  const { t, lang } = usePrefs();
  const [tips, setTips] = useState<Tip[] | null>(null);
  const [failed, setFailed] = useState(false);
  // The form as text: the effect below runs again only when this text changes
  const payload = JSON.stringify({ ...body, has_gd_copy: hasGdCopy });

  useEffect(() => {
    let current = true; // ignore an old answer if the form changed meanwhile
    api<{ tips: Tip[] }>("/reports/precheck", { method: "POST", body: JSON.parse(payload) })
      .then((answer) => current && setTips(answer.tips))
      .catch(() => current && setFailed(true));
    return () => { current = false; };
  }, [payload]);

  if (failed) return null; // tips are a help, not a must: if they fail, the form still works
  if (tips === null) {
    return (
      <p className="flex items-center gap-2 rounded-2xl bg-bg-soft px-4 py-3 text-sm text-ink-soft">
        <LoaderCircle size={16} className="animate-spin" aria-hidden /> {t("tips_checking")}
      </p>
    );
  }
  if (tips.length === 0) {
    return (
      <p className="rise flex items-center gap-2 rounded-2xl bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
        <CircleCheck size={18} aria-hidden /> {t("tips_all_good")}
      </p>
    );
  }
  return (
    <div className="rise rounded-2xl border border-amber-300/70 bg-amber-50 p-4">
      <p className="flex items-center gap-2 text-sm font-semibold text-amber-900">
        <Lightbulb size={18} aria-hidden /> {t("tips_title")}
      </p>
      <ul className="mt-2 space-y-1.5 pl-7 text-sm text-amber-900">
        {tips.map((tip) => (
          <li key={tip.code} className="list-disc">{lang === "bn" ? tip.message_bn : tip.message}</li>
        ))}
      </ul>
      <p className="mt-3 pl-7 text-xs text-amber-800">{t("tips_note")}</p>
    </div>
  );
}
