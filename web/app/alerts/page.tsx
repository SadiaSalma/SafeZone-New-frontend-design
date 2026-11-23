"use client";
/**
 * Frontend (web) · Task 25 · /alerts - the latest SafeZone alerts, for everyone (no log-in).
 *
 * Each card: the kind of theft (icon + colour), the area, how long ago, the alert text in your
 * language and how many phones it reached. Tap a card for the alert's own page.
 * A banner explains how to get these as notifications (follow an area on the Areas page).
 *
 * Data: GET /api/v1/public/alerts (Task 25 backend).
 */
import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { BellRing, ChevronRight, Clock, LoaderCircle, MapPin, Smartphone } from "lucide-react";
import busyNight from "@/public/images/alerts-busy-night-street.jpg";
import { TheftGallery } from "@/components/home/TheftGallery";
import { usePrefs } from "@/components/PreferencesProvider";
import { THEFT_ICONS } from "@/components/report/ReportSteps";
import { api } from "@/lib/api";
import { areaName } from "@/lib/areas";
import { THEFT_COLOURS, type PublicAlert } from "@/lib/public";
import { ago } from "@/lib/review";

export default function AlertsPage() {
  const { t, lang } = usePrefs();
  const [alerts, setAlerts] = useState<PublicAlert[] | null>(null);

  useEffect(() => {
    api<{ alerts: PublicAlert[] }>("/public/alerts").then((a) => setAlerts(a.alerts)).catch(() => setAlerts([]));
  }, []);

  return (
    <>
      <section data-photo-hero className="relative -mt-16 h-[40svh] min-h-[320px] overflow-hidden bg-black">
        <Image src={busyNight} alt="A busy Dhaka street at night under a brightly lit building" fill preload placeholder="blur"
               sizes="100vw" className="drift object-cover" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-black/30 to-bg" />
        <div className="rise relative mx-auto flex h-full max-w-3xl flex-col justify-end px-4 pb-12 text-white">
          <p className="mb-3 inline-flex w-fit items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-xs backdrop-blur-md">
            <span className="size-2 animate-pulse rounded-full bg-red-500" aria-hidden /> {t("alerts_badge")}
          </p>
          <h1 className="text-4xl font-semibold md:text-6xl">{t("alerts_title")}</h1>
          <p className="mt-2 max-w-xl text-white/80">{t("alerts_sub")}</p>
        </div>
      </section>

      <section className="mx-auto -mt-6 max-w-3xl space-y-3 px-4">
        <Link href="/areas" className="soft-shadow group flex items-center gap-4 rounded-[1.5rem] bg-primary p-4 text-on-primary">
          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-white/20"><BellRing size={20} aria-hidden /></span>
          <span className="flex-1 text-sm"><strong className="block">{t("alerts_get_title")}</strong>{t("alerts_get_sub")}</span>
          <ChevronRight size={18} className="transition group-hover:translate-x-0.5" aria-hidden />
        </Link>

        {!alerts ? (
          <div className="grid h-40 place-items-center"><LoaderCircle className="animate-spin text-ink-soft" /></div>
        ) : alerts.length === 0 ? (
          <div className="soft-shadow rounded-[1.75rem] bg-surface p-10 text-center text-ink-soft">{t("alerts_none")}</div>
        ) : alerts.map((a) => (
          <Link key={a.id} href={`/alerts/${a.id}`}
                className="rise soft-shadow group block rounded-[1.5rem] bg-surface p-5 transition hover:-translate-y-0.5">
            <div className="flex items-start gap-4">
              <span className="grid size-12 shrink-0 place-items-center rounded-2xl text-white"
                    style={{ background: THEFT_COLOURS[a.theft_type] }}>{THEFT_ICONS[a.theft_type]}</span>
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-ink">{lang === "bn" ? a.theft_name_bn : a.theft_name_en}{a.is_demo && <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 align-middle text-[10px] font-semibold tracking-wide text-amber-900 uppercase">{t("demo_label")}</span>}</p>
                <p className="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-ink-soft">
                  <span className="inline-flex items-center gap-1"><MapPin size={12} aria-hidden />
                    {a.thana ? areaName(a.thana, lang) : "—"}{a.ward && ` · ${areaName(a.ward, lang)}`}</span>
                  <span className="inline-flex items-center gap-1"><Clock size={12} aria-hidden />{ago(a.sent_at, lang)}</span>
                  <span className="inline-flex items-center gap-1"><Smartphone size={12} aria-hidden />
                    {t("alerts_reached").replace("{n}", a.phones.toLocaleString())}</span>
                </p>
                <p className="mt-3 text-sm leading-relaxed text-ink">{lang === "bn" ? a.text_bn : a.text_en}</p>
              </div>
              <ChevronRight size={18} className="mt-1 shrink-0 text-ink-soft transition group-hover:translate-x-0.5" aria-hidden />
            </div>
          </Link>
        ))}
      </section>

      <TheftGallery only={["pickpocket", "shop_mugging", "car_theft", "park_phone"]}
                    title="tg_alerts_title" sub="tg_alerts_sub" className="mx-auto mt-14 max-w-6xl px-4" />
    </>
  );
}
