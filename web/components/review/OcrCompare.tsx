"use client";
/**
 * Frontend (web) · Task 29 · OcrCompare.tsx - on the verifier's screen: what OCR read from the GD photo,
 * next to what the victim typed (design doc 5.4: "GD photo next to OCR fields and form").
 *
 * Only fields OCR actually filled are shown (Design Revisions R10). A row that differs is marked,
 * so the verifier looks at the GD photo for that field. The theft type is shown for information only.
 */
import { CircleCheck, CircleAlert, ScanText } from "lucide-react";
import { usePrefs } from "@/components/PreferencesProvider";
import type { TextKey } from "@/lib/i18n";
import type { ReviewDetail } from "@/lib/review";

const LABEL: Record<string, TextKey> = {
  gd_type: "scan_f_gd_type", gd_number: "scan_f_gd_number", gd_date: "scan_f_gd_date",
  police_station: "scan_f_police_station", theft_type: "scan_f_theft_type",
};

type Row = NonNullable<ReviewDetail["ocr"]>["compare"][number];

/** A value as people read it: names instead of codes, dates as "18 Nov 2026" (or in Bangla). */
function readable(row: Row, side: "ocr_text" | "form_text", lang: "en" | "bn"): string {
  const value = row[side]?.[lang] ?? row[side]?.en ?? (side === "ocr_text" ? row.ocr : row.form); // older answers had codes only
  if (!value) return "—";
  if (row.field === "gd_date") {
    return new Intl.DateTimeFormat(lang === "bn" ? "bn-BD" : "en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })
      .format(new Date(`${value}T00:00:00Z`));
  }
  return value;
}

export function OcrCompare({ ocr }: { ocr: NonNullable<ReviewDetail["ocr"]> }) {
  const { t, lang } = usePrefs();
  if (ocr.status === "deleted") return <p className="text-sm text-ink-soft">{t("ocr_deleted")}</p>;
  if (ocr.status !== "done" || !ocr.compare.length) return <p className="text-sm text-ink-soft">{t("ocr_nothing")}</p>;
  return (
    <div>
      <p className="mb-3 flex items-center gap-1.5 text-xs text-ink-soft">
        <ScanText size={14} aria-hidden /> {t("ocr_how").replace("{s}", String(ocr.seconds))}
      </p>
      <table className="w-full text-sm">
        <thead><tr className="text-left text-xs text-ink-soft">
          <th className="pb-2 font-normal" />
          <th className="pb-2 font-normal">{t("ocr_photo")}</th>
          <th className="pb-2 font-normal">{t("ocr_form")}</th>
        </tr></thead>
        <tbody>
          {ocr.compare.map((row) => (
            <tr key={row.field} className={`border-t border-line ${row.same ? "" : "bg-amber-50"}`}>
              <td className="py-2 pr-2 text-ink-soft">{t(LABEL[row.field])}</td>
              <td className="py-2 pr-2 font-medium text-ink">
                {readable(row, "ocr_text", lang)} <span className="text-xs font-normal text-ink-soft">{Math.round(row.confidence)}%</span>
              </td>
              <td className="py-2 text-ink">
                <span className="inline-flex items-center gap-1">
                  {row.same
                    ? <CircleCheck size={14} className="text-emerald-600" aria-label={t("ocr_same")} />
                    : <CircleAlert size={14} className="text-amber-600" aria-label={t("ocr_differs")} />}
                  {readable(row, "form_text", lang)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
