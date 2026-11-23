"use client";
/**
 * Frontend (web) · Task 18 · ChecksList.tsx - the automatic checks (Task 17) as a list:
 *   ✓ green = pass, ⚠ amber = warning, ✕ red = fail (a failed check blocks approval, Task 19)
 */
import { CircleAlert, CircleCheck, CircleX } from "lucide-react";
import { usePrefs } from "@/components/PreferencesProvider";
import type { TextKey } from "@/lib/i18n";
import type { Check } from "@/lib/review";

const LOOK = {
  pass: { icon: <CircleCheck size={18} />, colour: "text-emerald-600" },
  warning: { icon: <CircleAlert size={18} />, colour: "text-amber-600" },
  fail: { icon: <CircleX size={18} />, colour: "text-red-600" },
};

export function ChecksList({ checks }: { checks: Check[] }) {
  const { t, lang } = usePrefs();
  return (
    <ul className="divide-y divide-line">
      {checks.map((check) => (
        <li key={check.code} className="flex items-start gap-3 py-3">
          <span className={`mt-0.5 shrink-0 ${LOOK[check.result].colour}`} aria-label={t(`check_${check.result}` as TextKey)}>
            {LOOK[check.result].icon}
          </span>
          <div>
            <p className="text-sm font-medium text-ink">{t(`check_name_${check.code}` as TextKey)}</p>
            <p className="text-sm text-ink-soft">{lang === "bn" ? check.message_bn : check.message}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}
