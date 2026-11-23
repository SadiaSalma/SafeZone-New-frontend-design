"use client";
/**
 * Frontend (web) · Task 24 · PhoneScreen.tsx - one virtual phone's messages, drawn like a phone (FR-19).
 *
 * A dark phone frame with a clock, the tower it is connected to, and every SafeZone alert it
 * received, newest first - like notifications on a lock screen. Opens over the page (a portal).
 * Data: GET /api/v1/admin/simulator/phones/{id}/inbox (Task 24 backend).
 */
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Antenna, BellRing, LoaderCircle, X } from "lucide-react";
import { usePrefs } from "@/components/PreferencesProvider";
import { api } from "@/lib/api";
import { dhakaTime } from "@/lib/reports";

type Inbox = {
  id: string; is_test: boolean; label: string; tower: string | null;
  messages: { alert_id: string; text_en: string; text_bn: string; received_at: string }[];
};

export function PhoneScreen({ phoneId, onClose }: { phoneId: string; onClose: () => void }) {
  const { t, lang } = usePrefs();
  const [inbox, setInbox] = useState<Inbox | null>(null);

  useEffect(() => {
    api<Inbox>(`/admin/simulator/phones/${phoneId}/inbox`).then(setInbox).catch(() => onClose());
  }, [phoneId, onClose]);

  const clock = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Dhaka", hour: "2-digit", minute: "2-digit" }).format(new Date());

  return createPortal(
    <div role="dialog" aria-modal="true" aria-label={t("sim_phone_title")} onClick={onClose}
         className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm">
      <div onClick={(e) => e.stopPropagation()}
           className="rise relative h-[600px] w-[300px] overflow-hidden rounded-[2.6rem] border-[10px] border-neutral-900 bg-gradient-to-b from-slate-800 via-slate-900 to-black shadow-2xl">
        <div className="absolute top-2 left-1/2 h-5 w-24 -translate-x-1/2 rounded-full bg-neutral-900" />
        <button onClick={onClose} aria-label={t("close")}
                className="absolute top-3 right-3 z-10 grid size-8 place-items-center rounded-full bg-white/15 text-white hover:bg-white/25">
          <X size={16} />
        </button>
        <div className="px-5 pt-14 text-center text-white">
          <p className="text-5xl font-light">{clock}</p>
          <p className="mt-1 flex items-center justify-center gap-1.5 text-xs text-white/60">
            <Antenna size={12} aria-hidden /> {inbox?.tower ?? "…"} {inbox?.is_test && `· ${inbox.label || t("sim_legend_test")}`}
          </p>
        </div>
        <div className="mt-6 h-[430px] space-y-2.5 overflow-y-auto px-3 pb-6">
          {!inbox ? (
            <div className="grid h-40 place-items-center"><LoaderCircle className="animate-spin text-white/60" /></div>
          ) : inbox.messages.length === 0 ? (
            <p className="mt-10 text-center text-sm text-white/50">{t("sim_phone_empty")}</p>
          ) : inbox.messages.map((m) => (
            <div key={m.alert_id} className="rounded-2xl bg-white/12 p-3 text-white backdrop-blur-md">
              <p className="mb-1 flex items-center justify-between text-[11px] text-white/60">
                <span className="inline-flex items-center gap-1"><BellRing size={11} aria-hidden /> SafeZone</span>
                <span>{dhakaTime(m.received_at, lang)}</span>
              </p>
              <p className="text-[13px] leading-snug">{lang === "bn" ? m.text_bn : m.text_en}</p>
            </div>
          ))}
        </div>
      </div>
    </div>,
    document.body,
  );
}
