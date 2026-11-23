"use client";
/**
 * Frontend (web) · Task 30 · /admin - the admin panel (FR-25, FR-27).
 *
 * Tabs:
 *   Overview         numbers and charts (verifiers may see this tab too)
 *   Staff            add verifiers/admins, suspend or reactivate them
 *   Areas            names, alert radius per thana/ward, on/off
 *   Police stations  names, phone numbers, on/off
 *   GD formats       which GD number patterns the automatic check accepts
 *   Risk settings    points per warning and where Medium / High start
 *   Audit log        every important action, newest first
 * Other admin pages are linked at the bottom: alerts, simulator, crime figures.
 *
 * The chosen tab is kept in the address (?tab=staff), so a reload or a shared link opens the same tab.
 * Data: /api/v1/admin/... (Task 30 backend). The backend checks the role on every request.
 */
import Image from "next/image";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { BarChart3, FileSearch, KeyRound, LoaderCircle, Lock, MapPinned, Radio, Shield, SlidersHorizontal, Users } from "lucide-react";
import lake from "@/public/images/admin-lake-sunset.jpg";
import { AdminOverview } from "@/components/admin/AdminOverview";
import { AuditPanel } from "@/components/admin/AuditPanel";
import { PlacesPanel } from "@/components/admin/PlacesPanel";
import { GdFormatsPanel, RiskPanel } from "@/components/admin/RulesPanel";
import { StaffPanel } from "@/components/admin/StaffPanel";
import { useAuth } from "@/components/AuthProvider";
import { usePrefs } from "@/components/PreferencesProvider";
import type { TextKey } from "@/lib/i18n";

const TABS = [
  { key: "overview", label: "adm_tab_overview", icon: BarChart3, adminOnly: false },
  { key: "staff", label: "adm_tab_staff", icon: Users, adminOnly: true },
  { key: "areas", label: "adm_tab_areas", icon: MapPinned, adminOnly: true },
  { key: "stations", label: "adm_tab_stations", icon: Shield, adminOnly: true },
  { key: "gd", label: "adm_tab_gd", icon: KeyRound, adminOnly: true },
  { key: "risk", label: "adm_tab_risk", icon: SlidersHorizontal, adminOnly: true },
  { key: "audit", label: "adm_tab_audit", icon: FileSearch, adminOnly: true },
] as const;

export default function AdminPage() {
  const { t } = usePrefs();
  return (
    <>
      <section data-photo-hero className="relative -mt-16 h-[32svh] min-h-[260px] overflow-hidden bg-black">
        <Image src={lake} alt="Sunset over a lake in Dhaka with the city skyline" fill preload placeholder="blur"
               sizes="100vw" className="drift object-cover object-[50%_60%]" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-black/30 to-bg" />
        <div className="rise relative mx-auto flex h-full max-w-6xl flex-col justify-end px-4 pb-10 text-white">
          <p className="mb-2 inline-flex w-fit items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-xs backdrop-blur-md">
            <Lock size={13} aria-hidden /> {t("adm_staff_only")}
          </p>
          <h1 className="text-4xl font-semibold md:text-5xl">{t("adm_title")}</h1>
          <p className="mt-2 max-w-2xl text-white/80">{t("adm_sub")}</p>
        </div>
      </section>
      <section className="mx-auto -mt-4 max-w-6xl px-4">
        <Suspense fallback={<Spinner />}>
          <AdminTabs />
        </Suspense>
      </section>
    </>
  );
}

function Spinner() {
  return <div className="grid h-60 place-items-center"><LoaderCircle className="animate-spin text-ink-soft" /></div>;
}

function AdminTabs() {
  const { t } = usePrefs();
  const { user, loading } = useAuth();
  const router = useRouter();
  const params = useSearchParams();

  if (loading) return <Spinner />;
  if (!user || user.role === "victim") {
    return <div className="soft-shadow rounded-[1.75rem] bg-surface p-8 text-center text-ink">{t("adm_staff_only_long")}</div>;
  }
  const isAdmin = user.role === "admin";
  const tabs = TABS.filter((tab) => isAdmin || !tab.adminOnly);
  const wanted = params.get("tab");
  const tab = tabs.find((x) => x.key === wanted)?.key ?? "overview";

  return (
    <>
      <nav aria-label={t("adm_title")} className="soft-shadow mb-4 flex gap-1 overflow-x-auto rounded-full bg-surface p-1.5 [scrollbar-width:none]">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button key={key} onClick={() => router.replace(key === "overview" ? "/admin" : `/admin?tab=${key}`, { scroll: false })}
                  aria-current={tab === key ? "page" : undefined}
                  className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-3.5 py-2 text-sm transition
                    ${tab === key ? "bg-primary font-medium text-on-primary shadow" : "text-ink-soft hover:bg-bg-soft hover:text-ink"}`}>
            <Icon size={15} aria-hidden /> {t(label as TextKey)}
          </button>
        ))}
      </nav>

      {tab === "overview" && <AdminOverview />}
      {tab === "staff" && <StaffPanel />}
      {tab === "areas" && <PlacesPanel kind="areas" />}
      {tab === "stations" && <PlacesPanel kind="stations" />}
      {tab === "gd" && <GdFormatsPanel />}
      {tab === "risk" && <RiskPanel />}
      {tab === "audit" && <AuditPanel />}

      <div className="mt-6 flex flex-wrap gap-2 text-sm">
        <span className="py-1.5 text-ink-soft">{t("adm_more")}</span>
        <Link href="/review" className="rounded-full bg-bg-soft px-3.5 py-1.5 text-ink hover:bg-line">{t("nav_review")}</Link>
        <Link href="/admin/alerts" className="inline-flex items-center gap-1 rounded-full bg-bg-soft px-3.5 py-1.5 text-ink hover:bg-line">
          <Radio size={14} aria-hidden /> {t("nav_staff_alerts")}</Link>
        <Link href="/admin/simulator" className="rounded-full bg-bg-soft px-3.5 py-1.5 text-ink hover:bg-line">{t("nav_simulator")}</Link>
        {isAdmin && <Link href="/admin/crime" className="rounded-full bg-bg-soft px-3.5 py-1.5 text-ink hover:bg-line">{t("nav_crime_admin")}</Link>}
      </div>
    </>
  );
}
