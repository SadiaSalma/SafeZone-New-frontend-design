"use client";
/**
 * Frontend (web) · Task 19 · Timeline.tsx - the history of one report, from the audit log:
 * "Report sent" -> "Opened by a verifier" -> "More information asked" -> "Victim answered" -> ...
 * Only roles are shown (victim, verifier), never names.
 */
import { usePrefs } from "@/components/PreferencesProvider";
import type { TextKey } from "@/lib/i18n";
import { dhakaTime } from "@/lib/reports";
import type { ReviewDetail } from "@/lib/review";

const DOT: Record<string, string> = {
  "report.approve": "bg-emerald-500", "report.reject": "bg-red-500", "report.ask_info": "bg-sky-500",
  "report.answer": "bg-violet-500", "report.withdraw": "bg-neutral-400",
};

export function Timeline({ steps }: { steps: ReviewDetail["timeline"] }) {
  const { t, lang } = usePrefs();
  return (
    <ol className="relative space-y-4 border-l-2 border-line pl-5">
      {steps.map((step, i) => (
        <li key={i} className="relative">
          <span className={`absolute top-1 -left-[27px] size-3 rounded-full ring-4 ring-surface ${DOT[step.action] ?? "bg-primary"}`} />
          <p className="text-sm font-medium text-ink">{t(`tl_${step.action.replace("report.", "")}` as TextKey) || step.text}</p>
          <p className="text-xs text-ink-soft">
            {dhakaTime(step.created_at, lang)} · {t(`role_${step.role}` as TextKey) || step.role}
          </p>
        </li>
      ))}
    </ol>
  );
}
