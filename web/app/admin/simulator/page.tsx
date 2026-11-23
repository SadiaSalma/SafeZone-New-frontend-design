"use client";
/**
 * Frontend (web) · Tasks 21 + 24 · /admin/simulator - the simulated phone network (staff only).
 *
 * SafeZone can't use the real mobile network, so it simulates one (Design Revisions R10):
 * cell towers on a honeycomb grid and thousands of virtual phones around Dhaka.
 *
 * Task 24 (FR-19, FR-20):
 *  - pick an alert -> its circle (red), the towers that broadcast it, and the phones that got it (red dots)
 *  - click any phone -> its messages, shown like a phone screen
 *  - admins: test mode - place your own test phone and see "Received" / "Not reached" for each alert
 *
 * Opening /admin/simulator?alert=<id> (from "Sent alerts") selects that alert straight away.
 * Data: /api/v1/admin/simulator/* and /api/v1/admin/alerts (Tasks 21, 22, 24 backend).
 */
import dynamic from "next/dynamic";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { Antenna, LoaderCircle, Lock, Smartphone } from "lucide-react";
import colourfulBus from "@/public/images/simulator-colorful-bus.jpg";
import type { StaffAlert } from "@/app/admin/alerts/page";
import { useAuth } from "@/components/AuthProvider";
import { usePrefs } from "@/components/PreferencesProvider";
import type { AlertView, Phone, Tower } from "@/components/simulator/NetworkMap";
import { PhoneScreen } from "@/components/simulator/PhoneScreen";
import { TestModePanel, type TestPhoneReport } from "@/components/simulator/TestModePanel";
import { api, ApiError } from "@/lib/api";
import { areaName } from "@/lib/areas";

const NetworkMap = dynamic(() => import("@/components/simulator/NetworkMap"), {
  ssr: false,
  loading: () => <div className="h-[560px] animate-pulse rounded-[1.5rem] bg-bg-soft" />,
});

type Network = { towers: Tower[]; phones: number; test_phones: number };

// The page reads ?alert= from the address (useSearchParams), so Next.js 16 wants it inside <Suspense>
export default function SimulatorPage() {
  return (
    <Suspense fallback={<div className="grid h-[60vh] place-items-center"><LoaderCircle className="animate-spin text-ink-soft" /></div>}>
      <Simulator />
    </Suspense>
  );
}

function Simulator() {
  const { t, lang } = usePrefs();
  const { user, loading } = useAuth();
  const params = useSearchParams();
  const [network, setNetwork] = useState<Network | null>(null);
  const [alerts, setAlerts] = useState<StaffAlert[]>([]);
  const [alertId, setAlertId] = useState<string | null>(params.get("alert"));
  const [alertView, setAlertView] = useState<AlertView | null>(null);
  const [problem, setProblem] = useState("");
  const [showRanges, setShowRanges] = useState(false); // the circles are clearer when zoomed in
  const [counts, setCounts] = useState({ inView: 0, received: 0 });
  const [phoneOpen, setPhoneOpen] = useState<string | null>(null);
  // Task 24 test mode (admins)
  const [testReport, setTestReport] = useState<TestPhoneReport | null>(null);
  const [placing, setPlacing] = useState(false);
  const [testBusy, setTestBusy] = useState(false);
  const [testProblem, setTestProblem] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const isStaff = user?.role === "verifier" || user?.role === "admin";
  const isAdmin = user?.role === "admin";

  useEffect(() => {
    if (!isStaff) return;
    api<Network>("/admin/simulator/network").then(setNetwork).catch((e: ApiError) => setProblem(e.message));
    api<{ alerts: StaffAlert[] }>("/admin/alerts").then((a) => setAlerts(a.alerts.filter((x) => x.status === "sent"))).catch(() => {});
  }, [isStaff]);

  useEffect(() => {
    if (!isAdmin) return;
    api<TestPhoneReport>("/admin/simulator/test-phone").then(setTestReport).catch(() => {});
  }, [isAdmin]);

  // The chosen alert's circle and towers
  useEffect(() => {
    if (!isStaff || !alertId) return;
    let current = true;
    api<AlertView>(`/admin/simulator/alerts/${alertId}`).then((v) => current && setAlertView(v)).catch(() => current && setAlertView(null));
    return () => { current = false; };
  }, [isStaff, alertId]);

  const onPhonesLoaded = useCallback((inView: number, received: number) => setCounts({ inView, received }), []);
  const onPhoneClick = useCallback((p: Phone) => setPhoneOpen(p.id), []);
  const closePhone = useCallback(() => setPhoneOpen(null), []);

  async function placeTestPhone(lat: number, lng: number) {
    setPlacing(false);
    setTestBusy(true);
    setTestProblem("");
    try {
      setTestReport(await api<TestPhoneReport>("/admin/simulator/test-phone", { method: "POST", body: { lat, lng, label: "My test phone" } }));
      setRefreshKey((k) => k + 1);
    } catch (e) {
      const error = e as ApiError;
      setTestProblem(Object.values(error.fields ?? {})[0] ?? error.message);
    } finally {
      setTestBusy(false);
    }
  }

  async function removeTestPhone() {
    setTestBusy(true);
    try {
      setTestReport(await api<TestPhoneReport>("/admin/simulator/test-phone", { method: "DELETE" }));
      setRefreshKey((k) => k + 1);
    } finally {
      setTestBusy(false);
    }
  }

  const shownAlert = alertId ? alertView : null;

  return (
    <>
      <section data-photo-hero className="relative -mt-16 h-[34svh] min-h-[280px] overflow-hidden bg-black">
        <Image src={colourfulBus} alt="A colourful Dhaka bus driving down a busy road" fill preload placeholder="blur"
               sizes="100vw" className="drift object-cover" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-black/35 to-bg" />
        <div className="rise relative mx-auto flex h-full max-w-6xl flex-col justify-end px-4 pb-10 text-white">
          <p className="mb-2 inline-flex w-fit items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-xs backdrop-blur-md">
            <Lock size={13} aria-hidden /> {t("review_staff_only")}
          </p>
          <h1 className="text-4xl font-semibold md:text-5xl">{t("sim_title")}</h1>
          <p className="mt-2 max-w-2xl text-white/80">{t("sim_sub")}</p>
        </div>
      </section>

      <section className="mx-auto -mt-4 max-w-6xl px-4">
        {loading ? <Spinner /> : !isStaff ? (
          <div className="soft-shadow rounded-[1.75rem] bg-surface p-8 text-center text-ink">{t("review_only_staff")}</div>
        ) : !network ? (problem ? <p role="alert" className="rounded-2xl bg-red-50 p-4 text-sm text-red-800">{problem}</p> : <Spinner />) : (
          <>
            <div className="mb-4 grid gap-3 sm:grid-cols-3">
              <Stat icon={<Antenna size={20} />} value={network.towers.length.toLocaleString()} label={t("sim_towers")} />
              <Stat icon={<Smartphone size={20} />} value={network.phones.toLocaleString()} label={t("sim_phones")} />
              <Stat icon={<Smartphone size={20} className="text-red-600" />}
                    value={shownAlert ? shownAlert.phones.toLocaleString() : "—"} label={t("sim_reached")} />
            </div>

            {/* Task 24: choose an alert to see who it reached */}
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <span className="text-sm text-ink-soft">{t("sim_pick_alert")}</span>
              <button onClick={() => { setAlertId(null); setAlertView(null); }}
                      className={`rounded-full px-3 py-1.5 text-xs ${!alertId ? "bg-primary text-on-primary" : "border border-line text-ink"}`}>
                {t("sim_no_alert")}
              </button>
              {alerts.map((a) => (
                <button key={a.id} onClick={() => setAlertId(a.id)}
                        className={`rounded-full px-3 py-1.5 text-xs ${alertId === a.id ? "bg-red-600 text-white" : "border border-line text-ink hover:border-red-400"}`}>
                  {lang === "bn" ? a.theft_name_bn : a.theft_name_en}{a.thana && ` · ${areaName(a.thana, lang)}`}
                </button>
              ))}
            </div>

            <div className={`grid grid-cols-[minmax(0,1fr)] gap-4 ${isAdmin ? "lg:grid-cols-[minmax(0,1fr)_340px]" : ""}`}>
              <div className="soft-shadow rounded-[1.75rem] bg-surface p-4 md:p-5">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3 text-sm">
                  <div className="flex flex-wrap items-center gap-4 text-ink-soft">
                    <Legend dot="bg-white ring-2 ring-slate-900" label={t("sim_legend_tower")} />
                    <Legend dot="bg-slate-500" label={t("sim_legend_phone")} />
                    <Legend dot="bg-red-600" label={t("sim_legend_received")} />
                    <Legend dot="bg-violet-600" label={t("sim_legend_test")} />
                    <span className="text-xs">
                      {t("sim_in_view").replace("{n}", counts.inView.toLocaleString())}
                      {shownAlert && ` · ${t("sim_red_in_view").replace("{n}", counts.received.toLocaleString())}`}
                    </span>
                  </div>
                  <label className="inline-flex cursor-pointer items-center gap-2 text-ink">
                    <input type="checkbox" checked={showRanges} onChange={(e) => setShowRanges(e.target.checked)} className="accent-[var(--primary)]" />
                    {t("sim_show_ranges")}
                  </label>
                </div>
                {placing && <p className="mb-2 rounded-xl bg-violet-100 px-3 py-2 text-sm text-violet-900">{t("test_tap_map_long")}</p>}
                <NetworkMap towers={network.towers} showRanges={showRanges} alert={shownAlert}
                            onPhoneClick={onPhoneClick} onPhonesLoaded={onPhonesLoaded} refreshKey={refreshKey}
                            onMapClick={placing ? placeTestPhone : undefined} />
                <p className="mt-3 text-xs text-ink-soft">{t("sim_note")} {t("sim_click_phone")}</p>
              </div>

              {isAdmin && (
                <TestModePanel report={testReport} placing={placing} busy={testBusy} problem={testProblem}
                               onPlace={() => setPlacing(!placing)} onRemove={removeTestPhone} onOpenPhone={setPhoneOpen} />
              )}
            </div>
          </>
        )}
      </section>
      {phoneOpen && <PhoneScreen phoneId={phoneOpen} onClose={closePhone} />}
    </>
  );
}

function Spinner() {
  return <div className="grid h-40 place-items-center"><LoaderCircle className="animate-spin text-ink-soft" /></div>;
}

function Stat({ icon, value, label }: { icon: React.ReactNode; value: string; label: string }) {
  return (
    <div className="rise soft-shadow flex items-center gap-4 rounded-[1.5rem] bg-surface p-5">
      <span className="grid size-11 place-items-center rounded-2xl bg-bg-soft text-primary">{icon}</span>
      <div>
        <p className="text-2xl font-semibold text-ink">{value}</p>
        <p className="text-xs text-ink-soft">{label}</p>
      </div>
    </div>
  );
}

function Legend({ dot, label }: { dot: string; label: string }) {
  return <span className="inline-flex items-center gap-1.5"><span className={`size-2.5 rounded-full ${dot}`} />{label}</span>;
}
