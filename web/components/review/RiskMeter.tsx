"use client";
/**
 * Frontend (web) · Task 18 · RiskMeter.tsx - the risk score as a half-circle meter (0-100),
 * coloured green / amber / red, with the plain reasons underneath ("+20 The place is 3 km outside…").
 *
 * The score is ADVICE for the verifier (FR-13): it never approves or rejects anything by itself.
 */
import { useEffect, useState } from "react";
import { usePrefs } from "@/components/PreferencesProvider";
import type { TextKey } from "@/lib/i18n";
import { RISK_COLOURS, type Risk } from "@/lib/review";

export function RiskMeter({ risk }: { risk: Risk }) {
  const { t, lang } = usePrefs();
  const [shown, setShown] = useState(0); // the needle swings up to the score when the page opens
  useEffect(() => {
    const timer = setTimeout(() => setShown(risk.score), 150);
    return () => clearTimeout(timer);
  }, [risk.score]);

  const colour = RISK_COLOURS[risk.level].bar;
  const length = Math.PI * 80; // the length of the half-circle line (radius 80)

  return (
    <div>
      <div className="relative mx-auto w-56">
        <svg viewBox="0 0 200 115" className="w-full" role="img" aria-label={`${t("risk_score")} ${risk.score} / 100`}>
          <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke="var(--line)" strokeWidth="16" strokeLinecap="round" />
          <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke={colour} strokeWidth="16" strokeLinecap="round"
                strokeDasharray={length} strokeDashoffset={length * (1 - shown / 100)}
                style={{ transition: "stroke-dashoffset 1.1s cubic-bezier(.2,.8,.2,1)" }} />
        </svg>
        <div className="absolute inset-x-0 bottom-1 text-center">
          <p className="text-4xl font-semibold text-ink">{risk.score}</p>
          <p className={`mt-1 inline-flex rounded-full px-3 py-0.5 text-xs font-semibold ${RISK_COLOURS[risk.level].pill}`}>
            {t(`risk_${risk.level}` as TextKey)}
          </p>
        </div>
      </div>
      {risk.reasons && risk.reasons.length > 0 ? (
        <ul className="mt-4 space-y-2">
          {risk.reasons.map((r) => (
            <li key={r.code} className="flex items-start gap-3 text-sm">
              <span className="shrink-0 rounded-full bg-bg-soft px-2 py-0.5 text-xs font-semibold text-ink">+{r.points}</span>
              <span className="text-ink">{lang === "bn" ? r.text_bn : r.text}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 text-center text-sm text-ink-soft">{t("risk_no_reasons")}</p>
      )}
      <p className="mt-4 text-xs text-ink-soft">{t("risk_advice")}</p>
    </div>
  );
}
