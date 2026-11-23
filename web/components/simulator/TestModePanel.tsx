"use client";
/**
 * Frontend (web) · Task 24 · TestModePanel.tsx - test mode for admins (FR-20).
 *
 * "Place my test phone" -> tap anywhere on the map in Dhaka. The test phone joins its nearest
 * tower, like a real phone. Then for each alert you see:
 *   ✓ Received      - its tower broadcast the alert
 *   ✗ Not reached   - its tower doesn't touch the alert circle
 *   –  Sent before your phone was placed
 * Data: GET / POST / DELETE /api/v1/admin/simulator/test-phone (Task 24 backend).
 */
import { CircleCheck, CircleMinus, CircleX, LoaderCircle, MapPinned, Smartphone, Trash2 } from "lucide-react";
import { usePrefs } from "@/components/PreferencesProvider";
import type { TextKey } from "@/lib/i18n";

export type TestPhoneReport = {
  phone: { id: string; lat: number; lng: number; label: string; tower: string | null } | null;
  alerts: { id: string; text_en: string; text_bn: string; sent_at: string | null; received: boolean; reason: string }[];
};

type Props = {
  report: TestPhoneReport | null;
  placing: boolean;
  busy: boolean;
  problem: string;
  onPlace: () => void;
  onRemove: () => void;
  onOpenPhone: (id: string) => void;
};

const REASON: Record<string, { icon: React.ReactNode; colour: string; label: TextKey }> = {
  received: { icon: <CircleCheck size={16} />, colour: "text-emerald-600", label: "test_received" },
  tower_outside: { icon: <CircleX size={16} />, colour: "text-red-600", label: "test_not_reached" },
  before_phone: { icon: <CircleMinus size={16} />, colour: "text-ink-soft", label: "test_before" },
};

export function TestModePanel({ report, placing, busy, problem, onPlace, onRemove, onOpenPhone }: Props) {
  const { t, lang } = usePrefs();
  return (
    <section className="soft-shadow rounded-[1.75rem] bg-surface p-5">
      <h2 className="flex items-center gap-2 text-sm font-semibold tracking-wide text-ink-soft uppercase">
        <Smartphone size={16} aria-hidden /> {t("test_title")}
      </h2>
      <p className="mt-1 text-sm text-ink-soft">{t("test_sub")}</p>

      <div className="mt-4 flex flex-wrap gap-2">
        <button onClick={onPlace} disabled={busy}
                className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition disabled:opacity-50 ${
                  placing ? "bg-violet-600 text-white ring-4 ring-violet-200" : "bg-violet-100 text-violet-900 hover:bg-violet-200"}`}>
          {busy ? <LoaderCircle size={16} className="animate-spin" aria-hidden /> : <MapPinned size={16} aria-hidden />}
          {placing ? t("test_tap_map") : report?.phone ? t("test_move") : t("test_place")}
        </button>
        {report?.phone && (
          <>
            <button onClick={() => onOpenPhone(report.phone!.id)} className="rounded-full border border-line px-4 py-2 text-sm text-ink hover:border-primary">
              {t("test_open_phone")}
            </button>
            <button onClick={onRemove} disabled={busy} aria-label={t("test_remove")}
                    className="inline-flex items-center gap-1.5 rounded-full px-3 py-2 text-sm text-ink-soft hover:text-red-700">
              <Trash2 size={15} aria-hidden /> {t("test_remove")}
            </button>
          </>
        )}
      </div>
      {problem && <p role="alert" className="mt-2 text-xs text-red-700">{problem}</p>}

      {report?.phone && (
        <>
          <p className="mt-4 text-xs text-ink-soft">{t("test_on_tower").replace("{tower}", report.phone.tower ?? "—")}</p>
          {report.alerts.length === 0 ? (
            <p className="mt-2 text-sm text-ink-soft">{t("test_no_alerts")}</p>
          ) : (
            <ul className="mt-2 divide-y divide-line">
              {report.alerts.map((a) => {
                const look = REASON[a.reason] ?? REASON.tower_outside;
                return (
                  <li key={a.id} className="flex items-start gap-3 py-2.5">
                    <span className={`mt-0.5 shrink-0 ${look.colour}`}>{look.icon}</span>
                    <div className="min-w-0">
                      <p className={`text-xs font-semibold ${look.colour}`}>{t(look.label)}</p>
                      <p className="truncate text-sm text-ink">{lang === "bn" ? a.text_bn : a.text_en}</p>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
