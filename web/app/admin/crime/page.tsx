"use client";
/**
 * Frontend (web) · Task 22 · /admin/alerts - every alert and how it went (staff only).
 *
 * For each alert: what and where, its status (queued -> sending -> sent, or failed),
 * how many towers broadcast it, how many virtual phones received it, how many seconds it took,
 * and the text that was sent. Admins can "Send again" a failed alert.
 * The page refreshes itself every 5 seconds, so you can watch a new alert go out.
 *
 * Data: GET /api/v1/admin/alerts, POST /api/v1/admin/alerts/{id}/resend (Task 22 backend).
 */
import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Antenna, Clock, LoaderCircle, Lock, Map, RotateCw, Smartphone } from "lucide-react";
import trafficJam from "@/public/images/admin-alerts-traffic-jam.jpg";
import { useAuth } from "@/components/AuthProvider";
import { usePrefs } from "@/components/PreferencesProvider";
import { api, ApiError } from "@/lib/api";
import { areaName } from "@/lib/areas";
import type { TextKey } from "@/lib/i18n";
import { dhakaTime } from "@/lib/reports";

export type StaffAlert = {
  id: string; report_id: string; theft_name_en: string; theft_name_bn: string;
  thana: { code: string; name_en: string; name_bn: string } | null;
  text_en: string; text_bn: string; status: "queued" | "sending" | "sent" | "failed";
  radius_m: number; center: { lat: number; lng: number }; towers: number; phones: number; push_sent: number;
  queued_at: string; sent_at: string | null; seconds_to_send: number | null; attempts: number; last_error: string;
};

const STATUS_PILL: Record<StaffAlert["status"], string> = {
  queued: "bg-amber-100 text-amber-900",
  sending: "bg-sky-100 text-sky-900 animate-pulse",
  sent: "bg-emerald-100 text-emerald-900",
  failed: "bg-red-100 text-red-900",
};

export default function AlertsAdminPage() {
  const { t } = usePrefs();
  const { user, loading } = useAuth();
  const [alerts, setAlerts] = useState<StaffAlert[] | null>(null);
  const [problem, setProblem] = useState("");
  const isStaff = user?.role === "verifier" || user?.role === "admin";

  const load = useCallback(() => {
    api<{ alerts: StaffAlert[] }>("/admin/alerts").then((a) => setAlerts(a.alerts)).catch((e: ApiError) => setProblem(e.message));
  }, []);

  useEffect(() => {
    if (!isStaff) return;
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [isStaff, load]);

  const sent = alerts?.filter((a) => a.status === "sent") ?? [];
  const phones = sent.reduce((sum, a) => sum + a.phones, 0);
  const seconds = sent.filter((a) => a.seconds_to_send !== null);
  const average = seconds.length ? seconds.reduce((sum, a) => sum + (a.seconds_to_send ?? 0), 0) / seconds.length : 0;

  return (
    <>
      <section data-photo-hero className="relative -mt-16 h-[34svh] min-h-[280px] overflow-hidden bg-black">
        <Image src={trafficJam} alt="Cars and buses in a traffic jam on a Dhaka street" fill preload placeholder="blur"
               sizes="100vw" className="drift object-cover" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-black/35 to-bg" />
        <div className="rise relative mx-auto flex h-full max-w-5xl flex-col justify-end px-4 pb-10 text-white">
          <p className="mb-2 inline-flex w-fit items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-xs backdrop-blur-md">
            <Lock size={13} aria-hidden /> {t("review_staff_only")}
          </p>
          <h1 className="text-4xl font-semibold md:text-5xl">{t("alerts_admin_title")}</h1>
          <p className="mt-2 text-white/80">{t("alerts_admin_sub")}</p>
        </div>
      </section>

      <section className="mx-auto -mt-4 max-w-5xl px-4">
        {loading ? <Spinner /> : !isStaff ? (
          <div className="soft-shadow rounded-[1.75rem] bg-surface p-8 text-center text-ink">{t("review_only_staff")}</div>
        ) : !alerts ? (problem ? <p role="alert" className="rounded-2xl bg-red-50 p-4 text-sm text-red-800">{problem}</p> : <Spinner />) : (
          <>
            <div className="mb-5 grid gap-3 sm:grid-cols-3">
              <Stat value={String(sent.length)} label={t("alerts_admin_sent")} />
              <Stat value={phones.toLocaleString()} label={t("alerts_admin_phones")} />
              <Stat value={`${average.toFixed(1)} s`} label={t("alerts_admin_average")} />
            </div>
            {alerts.length === 0 ? (
              <div className="soft-shadow rounded-[1.75rem] bg-surface p-10 text-center text-ink-soft">{t("alerts_admin_empty")}</div>
            ) : (
              <ul className="space-y-3">
                {alerts.map((a) => <AlertRow key={a.id} alert={a} canResend={user?.role === "admin"} onChanged={load} />)}
              </ul>
            )}
          </>
        )}
      </section>
    </>
  );
}

function Spinner() {
  return <div className="grid h-40 place-items-center"><LoaderCircle className="animate-spin text-ink-soft" /></div>;
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="rise soft-shadow rounded-[1.5rem] bg-surface p-5">
      <p className="text-3xl font-semibold text-ink">{value}</p>
      <p className="text-xs text-ink-soft">{label}</p>
    </div>
  );
}

function AlertRow({ alert, canResend, onChanged }: { alert: StaffAlert; canResend: boolean; onChanged: () => void }) {
  const { t, lang } = usePrefs();
  const [busy, setBusy] = useState(false);

  async function resend() {
    setBusy(true);
    try { await api(`/admin/alerts/${alert.id}/resend`, { method: "POST" }); onChanged(); } finally { setBusy(false); }
  }

  return (
    <li className="rise soft-shadow rounded-[1.5rem] bg-surface p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-semibold text-ink">
            {lang === "bn" ? alert.theft_name_bn : alert.theft_name_en}
            {alert.thana && <span className="font-normal text-ink-soft"> · {areaName(alert.thana, lang)}</span>}
          </p>
          <p className="mt-0.5 flex items-center gap-1 text-xs text-ink-soft"><Clock size={12} aria-hidden /> {dhakaTime(alert.queued_at, lang)}</p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${STATUS_PILL[alert.status]}`}>{t(`alert_status_${alert.status}` as TextKey)}</span>
      </div>

      <p className="mt-3 rounded-2xl bg-bg-soft p-3 text-sm text-ink">{lang === "bn" ? alert.text_bn : alert.text_en}</p>

      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-ink">
        <span className="inline-flex items-center gap-1.5"><Antenna size={15} className="text-primary" aria-hidden /> {alert.towers} {t("sim_towers")}</span>
        <span className="inline-flex items-center gap-1.5"><Smartphone size={15} className="text-primary" aria-hidden /> {alert.phones.toLocaleString()} {t("sim_phones")}</span>
        <span className="text-ink-soft">{t("alert_radius").replace("{km}", (alert.radius_m / 1000).toFixed(1))}</span>
        {alert.seconds_to_send !== null && <span className="text-ink-soft">{t("alerts_admin_took").replace("{s}", alert.seconds_to_send.toFixed(1))}</span>}
        <Link href={`/admin/simulator?alert=${alert.id}`} className="ml-auto inline-flex items-center gap-1.5 text-primary hover:underline">
          <Map size={15} aria-hidden /> {t("alerts_admin_on_map")}
        </Link>
      </div>

      {alert.status === "failed" && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-red-50 p-3 text-sm text-red-900">
          <span>{t("alerts_admin_failed")} {alert.last_error}</span>
          {canResend && (
            <button onClick={resend} disabled={busy}
                    className="inline-flex items-center gap-1.5 rounded-full bg-red-600 px-4 py-1.5 text-xs font-semibold text-white disabled:opacity-50">
              <RotateCw size={13} aria-hidden /> {t("alerts_admin_resend")}
            </button>
          )}
        </div>
      )}
    </li>
  );
}
