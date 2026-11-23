"use client";
/**
 * Frontend (web) · Tasks 13 + 15 · /report/new - report a theft in 4 steps.
 *
 *   1. Where  - the map picker (Task 13) + an optional landmark
 *   2. What   - theft type, when, what was stolen, a short story
 *   3. GD     - GD/FIR number (checked live), date, police station
 *   4. Check  - a summary with Edit links + "this is true" -> Send
 *
 * - Only logged-in people with an NID can send (the backend checks this too).
 * - The draft is saved on this phone while typing (FR-11), so closing the tab loses nothing.
 * - If the backend finds a problem, we jump back to the step that has it.
 *
 * Privacy (Design Revisions R8): the exact spot is only seen by the victim and staff.
 */
import dynamic from "next/dynamic";
import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, CircleCheck, CloudCheck, IdCard, Landmark, LoaderCircle, Lock, Send } from "lucide-react";
import nightRoad from "@/public/images/report-dhaka-night-road.jpg";
import type { Spot } from "@/components/map/LocationPicker";
import { useAuth } from "@/components/AuthProvider";
import { SendTips } from "@/components/report/SendTips";
import { usePrefs } from "@/components/PreferencesProvider";
import {
  dhakaNow, EMPTY_DRAFT, StepCheck, StepGd, StepWhat, type ChosenPhotos, type Draft,
} from "@/components/report/ReportSteps";
import { api, ApiError } from "@/lib/api";
import { areaName, type Lookup } from "@/lib/areas";
import type { TextKey } from "@/lib/i18n";
import type { Report, ReportOptions } from "@/lib/reports";

// Leaflet needs the browser's "window", so the map is loaded only in the browser
const LocationPicker = dynamic(() => import("@/components/map/LocationPicker"), {
  ssr: false,
  loading: () => (
    <div className="grid h-[420px] place-items-center rounded-[1.5rem] bg-bg-soft">
      <LoaderCircle className="animate-spin text-ink-soft" />
    </div>
  ),
});

const STEPS: TextKey[] = ["report_step_where", "report_step_what", "report_step_gd", "report_step_check"];
const TITLES: TextKey[] = ["report_where_title", "report_what_title", "report_gd_title", "report_check_title"];
const DRAFT_KEY = "sz-report-draft";
// Draft field -> the name of its error message
const ERROR_FOR: Record<string, string> = { spot: "location", occurred_local: "occurred_at", police_station: "gd_police_station" };

// Which step holds each field the backend may complain about
const FIELD_STEP: Record<string, number> = {
  location: 0, lat: 0, lng: 0, landmark: 0,
  theft_type: 1, occurred_at: 1, stolen_items: 1, description: 1,
  gd_number: 2, number: 2, gd_date: 2, date: 2, gd_police_station: 2, police_station: 2,
};

export default function NewReportPage() {
  const { t } = usePrefs();
  const { user, loading } = useAuth();

  return (
    <>
      <section data-photo-hero className="relative -mt-16 h-[34svh] min-h-[280px] overflow-hidden bg-black">
        <Image src={nightRoad} alt="A person standing alone on a dark tree-lined road in Dhaka at night" fill preload
               placeholder="blur" sizes="100vw" className="drift object-cover object-[50%_40%]" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-black/35 to-bg" />
        <div className="rise relative mx-auto flex h-full max-w-3xl flex-col justify-end px-4 pb-10 text-white">
          <h1 className="text-4xl font-semibold md:text-5xl">{t("report_page_title")}</h1>
          <p className="mt-2 max-w-xl text-white/80">{t("report_page_sub")}</p>
        </div>
      </section>

      <section className="mx-auto -mt-4 max-w-3xl px-4">
        {loading ? (
          <div className="grid h-40 place-items-center"><LoaderCircle className="animate-spin text-ink-soft" /></div>
        ) : !user ? (
          <Gate text={t("report_need_login")} href="/login" button={t("login")} />
        ) : user.role !== "victim" ? (
          <Gate text={t("report_staff")} href="/" button={t("go_home")} />
        ) : !user.nid_added ? (
          <Gate text={t("my_reports_nid")} href="/me/nid" button={t("nid_add_link")} icon={<IdCard className="text-amber-600" />} />
        ) : (
          <ReportForm />
        )}
      </section>
    </>
  );
}

/** The draft turned into what POST /api/v1/reports expects. */
function reportBody(draft: Draft) {
  return {
    theft_type: draft.theft_type,
    occurred_at: `${draft.occurred_local}:00+06:00`, // Dhaka time
    lat: draft.spot?.lat, lng: draft.spot?.lng,
    landmark: draft.landmark, description: draft.description, stolen_items: draft.stolen_items,
    gd: { type: draft.gd_type, number: draft.gd_number, date: draft.gd_date, police_station: draft.police_station },
    gd_scan_id: draft.gd_scan_id ?? undefined, // Task 29: the GD photo that was read (becomes the GD copy)
  };
}

/** The draft saved on this phone, or an empty one. */
function readDraft(): Draft {
  try {
    const saved = localStorage.getItem(DRAFT_KEY);
    return saved ? { ...EMPTY_DRAFT, ...JSON.parse(saved) } : EMPTY_DRAFT;
  } catch {
    return EMPTY_DRAFT; // storage blocked or broken: start fresh
  }
}

function Gate({ text, href, button, icon }: { text: string; href: string; button: string; icon?: React.ReactNode }) {
  return (
    <div className="soft-shadow rounded-[1.75rem] bg-surface p-8 text-center">
      {icon && <div className="mb-3 flex justify-center">{icon}</div>}
      <p className="text-ink">{text}</p>
      <Link href={href} className="mt-5 inline-flex rounded-full bg-primary px-6 py-2.5 text-sm font-semibold text-on-primary">
        {button}
      </Link>
    </div>
  );
}

function ReportForm() {
  const { t, lang } = usePrefs();
  // The form only appears after the log-in check, i.e. in the browser, so it can read the saved draft right away
  const [draft, setDraft] = useState<Draft>(readDraft);
  const [options, setOptions] = useState<ReportOptions | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [problem, setProblem] = useState("");
  const [gdFree, setGdFree] = useState<boolean | null>(null);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState<Report | null>(null);
  const [photos, setPhotos] = useState<ChosenPhotos>({ items: [], gd: [] }); // Task 16 (not saved in the draft)
  const [uploading, setUploading] = useState(""); // e.g. "Uploading photo 1/3"
  const [photoFails, setPhotoFails] = useState(0);
  const card = useRef<HTMLDivElement>(null);
  const step = draft.step;

  // Load the choices for the form
  useEffect(() => {
    api<ReportOptions>("/reports/options").then(setOptions).catch((e: ApiError) => setProblem(e.message));
  }, []);

  // Save the draft on this phone whenever it changes (FR-11)
  useEffect(() => {
    if (sent) return;
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify(draft)); } catch { /* storage blocked: fine */ }
  }, [draft, sent]);

  const change = useCallback((part: Partial<Draft>) => {
    setDraft((old) => ({ ...old, ...part }));
    setErrors((old) => {
      const next = { ...old };
      for (const key of Object.keys(part)) delete next[ERROR_FOR[key] ?? key]; // fixing a field hides its error
      return next;
    });
  }, []);

  function goTo(next: number) {
    setDraft((old) => {
      const fill: Partial<Draft> = {};
      if (next >= 1 && !old.occurred_local) fill.occurred_local = dhakaNow();
      if (next >= 2 && !old.gd_date) fill.gd_date = (old.occurred_local || dhakaNow()).slice(0, 10);
      if (next >= 2 && !old.police_station && old.place?.nearest_police_stations[0]) {
        fill.police_station = old.place.nearest_police_stations[0].code;
      }
      return { ...old, ...fill, step: next };
    });
    card.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  /** The checks we can do right here, before asking the backend. */
  function problemsIn(s: number): Record<string, string> {
    const found: Record<string, string> = {};
    if (s === 0 && !(draft.spot && draft.place?.inside_dhaka)) found.location = t("report_err_place");
    if (s === 1) {
      if (!draft.theft_type) found.theft_type = t("report_err_type");
      if (!draft.occurred_local) found.occurred_at = t("report_err_when");
      else if (draft.occurred_local > dhakaNow()) found.occurred_at = t("report_err_future");
      else if (draft.occurred_local < dhakaNow(-(options?.limits.max_age_days ?? 30))) found.occurred_at = t("report_err_old");
    }
    if (s === 2) {
      if (!draft.gd_number.trim()) found.gd_number = t("report_err_gd_number");
      else if (gdFree === false) found.gd_number = t("report_gd_taken");
      if (!draft.gd_date) found.gd_date = t("report_err_gd_date");
      else if (draft.gd_date < draft.occurred_local.slice(0, 10)) found.gd_date = t("report_err_gd_before");
      if (!draft.police_station) found.gd_police_station = t("report_station_pick");
    }
    if (s === 3 && !draft.agree) found.agree = t("agree_required");
    return found;
  }

  function next() {
    const found = problemsIn(step);
    setErrors(found);
    if (Object.keys(found).length === 0) goTo(step + 1);
  }

  async function send() {
    const found = problemsIn(3);
    setErrors(found);
    if (Object.keys(found).length) return;
    setSending(true);
    setProblem("");
    try {
      const report = await api<Report>("/reports", { method: "POST", body: reportBody(draft) });
      try { localStorage.removeItem(DRAFT_KEY); } catch { /* fine */ }
      // Task 16: now that the report exists, upload its photos one by one
      const queue = [
        ...photos.items.map((file) => ({ file, kind: "item" })),
        ...photos.gd.map((file) => ({ file, kind: "gd_copy" })),
      ];
      let failed = 0;
      for (const [i, { file, kind }] of queue.entries()) {
        setUploading(`${t("photo_uploading")} ${i + 1}/${queue.length}`);
        const form = new FormData();
        form.append("kind", kind);
        form.append("file", file);
        try {
          await api(`/me/reports/${report.id}/photos`, { method: "POST", body: form });
        } catch {
          failed += 1;
        }
      }
      setUploading("");
      setPhotoFails(failed);
      setSent(report);
      card.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) {
      const error = e as ApiError;
      setProblem(error.message);
      setErrors(error.fields ?? {});
      if (error.code === "scan_not_found" || error.code === "scan_used") {
        change({ gd_scan_id: null, ocr_filled: [] }); // Task 29: that GD photo can't be used; send again without it
      }
      const steps = Object.keys(error.fields ?? {}).map((f) => FIELD_STEP[f]).filter((s) => s !== undefined);
      if (steps.length) goTo(Math.min(...steps));
    } finally {
      setSending(false);
    }
  }

  const onFreeChange = useCallback((free: boolean | null) => setGdFree(free), []);

  if (sent) return <Sent report={sent} photoFails={photoFails} />;
  if (!options) {
    return problem
      ? <p role="alert" className="rounded-2xl bg-red-50 p-4 text-sm text-red-800">{problem}</p>
      : <div className="grid h-40 place-items-center"><LoaderCircle className="animate-spin text-ink-soft" /></div>;
  }

  return (
    <div ref={card} className="scroll-mt-20">
      {/* Step bar: finished steps can be clicked to go back */}
      <ol className="mb-6 grid grid-cols-4 gap-2">
        {STEPS.map((key, i) => (
          <li key={key}>
            <button type="button" disabled={i > step} onClick={() => goTo(i)} className="flex w-full flex-col gap-2 text-left disabled:cursor-default">
              <span className={`h-1.5 rounded-full transition-colors duration-500 ${i <= step ? "bg-primary" : "bg-line"}`} />
              <span className={`text-xs ${i === step ? "font-semibold text-ink" : "text-ink-soft"}`}>{i + 1}. {t(key)}</span>
            </button>
          </li>
        ))}
      </ol>

      <div key={step} className="rise soft-shadow rounded-[1.75rem] bg-surface p-4 md:p-6">
        <h2 className="text-xl font-semibold text-ink">{t(TITLES[step])}</h2>
        {step === 0 && <p className="mt-1 mb-4 text-sm text-ink-soft">{t("report_where_sub")}</p>}
        {problem && <p role="alert" className="my-4 rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-800">{problem}</p>}
        <div className={step === 0 ? "" : "mt-5"}>
          {step === 0 && (
            <>
              <LocationPicker value={draft.spot} onChange={(spot: Spot, place: Lookup | null) => change({ spot, place })} />
              {errors.location && <p role="alert" className="mt-2 text-xs text-red-700">{errors.location}</p>}
              <label htmlFor="landmark" className="mt-5 mb-1 block text-sm font-medium text-ink">{t("report_landmark")}</label>
              <div className="flex items-center gap-2 rounded-2xl border border-line bg-bg px-4 py-3 focus-within:border-primary">
                <Landmark size={18} className="text-ink-soft" aria-hidden />
                <input id="landmark" value={draft.landmark} maxLength={120} onChange={(e) => change({ landmark: e.target.value })}
                       placeholder={t("report_landmark_hint")}
                       className="w-full bg-transparent text-sm text-ink placeholder:text-ink-soft/70 focus:outline-none" />
              </div>
              {draft.place?.inside_dhaka && (
                <p className="mt-3 text-sm text-ink-soft">
                  {areaName(draft.place.thana!, lang)} {t("areas_thana")}
                  {draft.place.ward && ` · ${areaName(draft.place.ward, lang)}`}
                </p>
              )}
              <p className="mt-4 flex items-start gap-2 text-xs text-ink-soft">
                <Lock size={14} className="mt-0.5 shrink-0" aria-hidden /> {t("report_privacy")}
              </p>
            </>
          )}
          {step === 1 && (
            <StepWhat draft={draft} change={change} options={options} errors={errors} photos={photos} setPhotos={setPhotos} />
          )}
          {step === 2 && (
            <StepGd draft={draft} change={change} options={options} errors={errors} onFreeChange={onFreeChange}
                    photos={photos} setPhotos={setPhotos} />
          )}
          {step === 3 && <div className="mb-5"><SendTips body={reportBody(draft)} hasGdCopy={photos.gd.length > 0 || !!draft.gd_scan_id} /></div>}
          {step === 3 && (
            <StepCheck draft={draft} change={change} options={options} errors={errors} goTo={goTo} photos={photos} />
          )}
        </div>

        <div className="mt-8 flex items-center justify-between gap-3 border-t border-line pt-5">
          {step > 0 ? (
            <button type="button" onClick={() => goTo(step - 1)}
                    className="inline-flex items-center gap-1 rounded-full px-4 py-2.5 text-sm text-ink-soft hover:text-ink">
              <ChevronLeft size={18} aria-hidden /> {t("back")}
            </button>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-xs text-ink-soft"><CloudCheck size={15} aria-hidden /> {t("report_draft_saved")}</span>
          )}
          {step < 3 ? (
            <button type="button" onClick={next}
                    className="inline-flex items-center gap-1 rounded-full bg-primary px-6 py-3 text-sm font-semibold text-on-primary shadow-lg transition hover:scale-[1.02]">
              {t("next")} <ChevronRight size={18} aria-hidden />
            </button>
          ) : (
            <button type="button" onClick={send} disabled={sending}
                    className="inline-flex items-center gap-2 rounded-full bg-neutral-950 px-7 py-3 text-sm font-semibold text-white shadow-lg transition hover:scale-[1.02] disabled:opacity-70">
              {sending ? <LoaderCircle size={18} className="animate-spin" aria-hidden /> : <Send size={17} aria-hidden />}
              {uploading || t("report_send")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Sent({ report, photoFails }: { report: Report; photoFails: number }) {
  const { t, lang } = usePrefs();
  return (
    <div className="rise soft-shadow rounded-[1.75rem] bg-surface p-8 text-center">
      <span className="mx-auto grid size-20 place-items-center rounded-full bg-primary/15 text-primary">
        <CircleCheck size={44} aria-hidden />
      </span>
      <h2 className="mt-5 text-2xl font-semibold text-ink">{t("report_sent_title")}</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-ink-soft">{t("report_sent_sub")}</p>
      <p className="mt-4 inline-flex rounded-full bg-amber-100 px-4 py-1.5 text-xs font-semibold text-amber-900">
        {t("status_pending")} · {lang === "bn" ? report.theft_name_bn : report.theft_name_en}
      </p>
      {photoFails > 0 && <p role="alert" className="mt-3 text-sm text-red-700">{t("photo_some_failed")}</p>}
      <div className="mt-7 flex flex-wrap justify-center gap-3">
        <Link href="/me/reports" className="rounded-full bg-primary px-6 py-2.5 text-sm font-semibold text-on-primary">{t("my_reports")}</Link>
        <Link href="/" className="rounded-full border border-line px-6 py-2.5 text-sm text-ink">{t("go_home")}</Link>
      </div>
    </div>
  );
}
