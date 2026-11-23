"use client";
/**
 * Frontend (web) · Task 15 · ReportSteps.tsx - steps 2, 3 and 4 of the report form.
 *
 *   StepWhat  - what was stolen: 10 big theft-type tiles, when it happened, items, a short story
 *   StepGd    - the police GD/FIR: type, number (checked live: "free" or "already reported"),
 *               date, police station (the nearest one is chosen for you)
 *   StepCheck - everything on one card with "Edit" links, and the "this is true" tick
 *   Task 16: StepWhat also takes up to 3 item photos, StepGd one photo of the GD copy.
 *   Task 29: StepGd starts with "Scan your GD copy" (GdScan): the photo is read and the boxes fill
 *            themselves; each filled box shows a "From photo" tag until the person changes it.
 *
 * The page (app/report/new/page.tsx) keeps the Draft and gives each step what it needs.
 */
import { useEffect, useState, type ReactNode } from "react";
import {
  Bike, Car, CarTaxiFront, CircleCheck, CircleHelp, CircleX, House, LoaderCircle, Motorbike, Pencil,
  ShoppingBag, Smartphone, Store, Wallet,
} from "lucide-react";
import { usePrefs } from "@/components/PreferencesProvider";
import { FromPhoto, GdScan } from "@/components/report/GdScan";
import { PhotoPicker } from "@/components/report/PhotoPicker";
import { api } from "@/lib/api";
import { areaName, type Lookup } from "@/lib/areas";
import type { ReportOptions } from "@/lib/reports";

// ---------------------------------------------------------------- the draft (saved on the phone)
export type Draft = {
  step: number;
  spot: { lat: number; lng: number } | null;
  place: Lookup | null;
  landmark: string;
  theft_type: string;
  occurred_local: string; // "2026-11-20T21:30" in Dhaka time
  stolen_items: string;
  description: string;
  gd_type: "GD" | "FIR";
  gd_number: string;
  gd_date: string; // "2026-11-20"
  police_station: string; // a police station code
  agree: boolean;
  gd_scan_id: string | null; // Task 29: the GD photo that was read
  ocr_filled: string[]; // Task 29: boxes filled from the photo (and not changed by the person yet)
};

/** Now, in Dhaka time, as "YYYY-MM-DDTHH:mm" (what <input type="datetime-local"> wants). */
export function dhakaNow(offsetDays = 0): string {
  const t = new Date(Date.now() + offsetDays * 86400000 + 6 * 3600000); // UTC + 6 hours
  return t.toISOString().slice(0, 16);
}

export const EMPTY_DRAFT: Draft = {
  step: 0, spot: null, place: null, landmark: "",
  theft_type: "", occurred_local: "", stolen_items: "", description: "",
  gd_type: "GD", gd_number: "", gd_date: "", police_station: "", agree: false,
  gd_scan_id: null, ocr_filled: [],
};

export const THEFT_ICONS: Record<string, ReactNode> = {
  phone_snatching: <Smartphone />, bag_snatching: <ShoppingBag />, pickpocket: <Wallet />,
  motorbike_theft: <Motorbike />, bicycle_theft: <Bike />, car_theft: <Car />, cng_theft: <CarTaxiFront />,
  burglary: <House />, shop_theft: <Store />, other: <CircleHelp />,
};

type StepProps = {
  draft: Draft;
  change: (part: Partial<Draft>) => void;
  options: ReportOptions;
  errors: Record<string, string>;
};

/** Task 16: the chosen photos (kept in memory only - files can't be saved in the draft). */
export type ChosenPhotos = { items: File[]; gd: File[] };
type PhotoProps = { photos: ChosenPhotos; setPhotos: (p: ChosenPhotos) => void };

// ---------------------------------------------------------------- small form pieces
function Label({ htmlFor, children, hint }: { htmlFor: string; children: ReactNode; hint?: string }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 flex items-baseline justify-between gap-2 text-sm font-medium text-ink">
      {children}
      {hint && <span className="text-xs font-normal text-ink-soft">{hint}</span>}
    </label>
  );
}

function Problem({ text, id }: { text?: string; id?: string }) {
  return text ? <p id={id} role="alert" className="mt-1.5 text-xs text-red-700">{text}</p> : null;
}

const INPUT = "w-full rounded-2xl border border-line bg-bg px-4 py-3 text-sm text-ink placeholder:text-ink-soft/70 focus:border-primary focus:outline-none";

// ---------------------------------------------------------------- step 2: what happened
export function StepWhat({ draft, change, options, errors, photos, setPhotos }: StepProps & PhotoProps) {
  const { t, lang } = usePrefs();
  return (
    <div className="space-y-6">
      <fieldset>
        <legend className="mb-3 text-sm font-medium text-ink">{t("report_what_type")}</legend>
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-5">
          {options.theft_types.map((type) => {
            const chosen = draft.theft_type === type.code;
            return (
              <button key={type.code} type="button" aria-pressed={chosen} onClick={() => change({ theft_type: type.code })}
                      className={`flex flex-col items-center gap-2 rounded-2xl border p-3 text-center text-xs transition ${
                        chosen ? "border-primary bg-primary text-on-primary shadow-lg"
                               : "border-line bg-bg text-ink hover:-translate-y-0.5 hover:border-primary"}`}>
                <span className={chosen ? "" : "text-primary"}>{THEFT_ICONS[type.code]}</span>
                {lang === "bn" ? type.name_bn : type.name_en}
              </button>
            );
          })}
        </div>
        <Problem text={errors.theft_type} />
      </fieldset>

      <div>
        <Label htmlFor="occurred" hint={t("report_when_hint")}>{t("report_when")}</Label>
        <input id="occurred" type="datetime-local" className={INPUT} value={draft.occurred_local}
               min={dhakaNow(-options.limits.max_age_days)} max={dhakaNow()}
               onChange={(e) => change({ occurred_local: e.target.value })} aria-invalid={!!errors.occurred_at} />
        <Problem text={errors.occurred_at} />
      </div>

      <div>
        <Label htmlFor="items" hint={`${draft.stolen_items.length}/${options.limits.stolen_items}`}>{t("report_items")}</Label>
        <input id="items" className={INPUT} maxLength={options.limits.stolen_items} value={draft.stolen_items}
               placeholder={t("report_items_hint")} onChange={(e) => change({ stolen_items: e.target.value })} />
      </div>

      <div>
        <Label htmlFor="story" hint={`${draft.description.length}/${options.limits.description}`}>{t("report_story")}</Label>
        <textarea id="story" rows={4} className={INPUT} maxLength={options.limits.description} value={draft.description}
                  placeholder={t("report_story_hint")} onChange={(e) => change({ description: e.target.value })} />
        <p className="mt-1.5 text-xs text-ink-soft">{t("report_story_note")}</p>
      </div>

      <PhotoPicker files={photos.items} onChange={(items) => setPhotos({ ...photos, items })} max={3} label={t("photo_items")} />
      <p className="-mt-3 text-xs text-ink-soft">{t("photo_privacy")}</p>
    </div>
  );
}

// ---------------------------------------------------------------- step 3: the GD
export function StepGd({ draft, change, options, errors, onFreeChange, photos, setPhotos }:
  StepProps & PhotoProps & { onFreeChange: (free: boolean | null) => void }) {
  const { t, lang } = usePrefs();
  const [answer, setAnswer] = useState<boolean | null>(null);
  const [checking, setChecking] = useState(false);
  const theftDay = draft.occurred_local.slice(0, 10);
  const ready = Boolean(draft.gd_number.trim() && draft.gd_date && draft.police_station);
  const free = ready ? answer : null; // nothing to say until the number, date and station are filled in
  // Task 29: a box the person changes is theirs now - its "From photo" tag goes away
  const edit = (part: Partial<Draft>) => change({ ...part, ocr_filled: draft.ocr_filled.filter((k) => !(k in part)) });
  const fromPhoto = (key: string) => (draft.ocr_filled.includes(key) ? <FromPhoto /> : null);

  // Ask "is this GD free?" half a second after the person stops typing
  useEffect(() => {
    if (!ready) return;
    const timer = setTimeout(() => {
      setChecking(true);
      api<{ free: boolean }>("/reports/gd-check", {
        method: "POST",
        body: { type: draft.gd_type, number: draft.gd_number, date: draft.gd_date, police_station: draft.police_station },
      })
        .then((reply) => { setAnswer(reply.free); onFreeChange(reply.free); })
        .catch(() => { setAnswer(null); onFreeChange(null); })
        .finally(() => setChecking(false));
    }, 500);
    return () => clearTimeout(timer);
  }, [ready, draft.gd_type, draft.gd_number, draft.gd_date, draft.police_station, onFreeChange]);

  return (
    <div className="space-y-6">
      <div className="rounded-2xl bg-bg-soft p-4 text-sm text-ink-soft">{t("report_gd_why")}</div>
      <GdScan draft={draft} change={change} options={options} />

      <fieldset>
        <legend className="mb-2 text-sm font-medium text-ink">{t("report_gd_type")}{fromPhoto("gd_type")}</legend>
        <div className="inline-flex rounded-full bg-bg-soft p-1">
          {options.gd_types.map((type) => (
            <button key={type.code} type="button" aria-pressed={draft.gd_type === type.code}
                    onClick={() => edit({ gd_type: type.code as "GD" | "FIR" })}
                    className={`rounded-full px-5 py-2 text-sm font-medium transition ${
                      draft.gd_type === type.code ? "bg-primary text-on-primary shadow" : "text-ink-soft hover:text-ink"}`}>
              {lang === "bn" ? type.name_bn : type.name_en}
            </button>
          ))}
        </div>
      </fieldset>

      <div className="grid gap-5 sm:grid-cols-2">
        <div>
          <Label htmlFor="gd-number" hint={options.gd_examples[0] ? `${t("report_eg")} ${options.gd_examples[0]}` : undefined}>
            <span>{draft.gd_type === "GD" ? t("report_gd_number") : t("report_fir_number")}{fromPhoto("gd_number")}</span>
          </Label>
          <input id="gd-number" className={INPUT} inputMode="text" maxLength={30} value={draft.gd_number}
                 onChange={(e) => edit({ gd_number: e.target.value })} aria-invalid={!!errors.gd_number}
                 aria-describedby="gd-free" />
          <div id="gd-free" aria-live="polite" className="mt-1.5 min-h-5 text-xs">
            {checking ? (
              <span className="inline-flex items-center gap-1 text-ink-soft"><LoaderCircle size={13} className="animate-spin" /> {t("report_gd_checking")}</span>
            ) : free === true ? (
              <span className="inline-flex items-center gap-1 text-emerald-700"><CircleCheck size={13} /> {t("report_gd_free")}</span>
            ) : free === false ? (
              <span className="inline-flex items-center gap-1 text-red-700"><CircleX size={13} /> {t("report_gd_taken")}</span>
            ) : null}
          </div>
          <Problem text={errors.gd_number || errors.number} />
        </div>
        <div>
          <Label htmlFor="gd-date"><span>{t("report_gd_date")}{fromPhoto("gd_date")}</span></Label>
          <input id="gd-date" type="date" className={INPUT} value={draft.gd_date} min={theftDay || undefined}
                 max={dhakaNow().slice(0, 10)} onChange={(e) => edit({ gd_date: e.target.value })}
                 aria-invalid={!!errors.gd_date} />
          <Problem text={errors.gd_date} />
        </div>
      </div>

      <div>
        <Label htmlFor="station" hint={draft.place?.nearest_police_stations[0] ? t("report_station_hint") : undefined}>
          <span>{t("my_reports_station")}{fromPhoto("police_station")}</span>
        </Label>
        <select id="station" className={INPUT} value={draft.police_station}
                onChange={(e) => edit({ police_station: e.target.value })} aria-invalid={!!errors.gd_police_station}>
          <option value="">{t("report_station_pick")}</option>
          {draft.place?.nearest_police_stations.length ? (
            <optgroup label={t("report_station_near")}>
              {draft.place.nearest_police_stations.map((s) => (
                <option key={`near-${s.code}`} value={s.code}>{areaName(s, lang)} · {(s.distance_m! / 1000).toFixed(1)} km</option>
              ))}
            </optgroup>
          ) : null}
          <optgroup label={t("report_station_all")}>
            {options.police_stations.map((s) => <option key={s.code} value={s.code}>{areaName(s, lang)}</option>)}
          </optgroup>
        </select>
        <Problem text={errors.gd_police_station} />
      </div>

      {/* The scanned photo already is the GD copy; otherwise the person may still add one by hand */}
      {!draft.gd_scan_id && (
        <PhotoPicker files={photos.gd} onChange={(gd) => setPhotos({ ...photos, gd })} max={1}
                     label={t("photo_gd")} hint={t("photo_gd_hint")} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------- step 4: check and send
export function StepCheck({ draft, change, options, errors, goTo, photos }:
  StepProps & { goTo: (step: number) => void; photos: ChosenPhotos }) {
  const { t, lang } = usePrefs();
  const type = options.theft_types.find((x) => x.code === draft.theft_type);
  const station = options.police_stations.find((s) => s.code === draft.police_station);
  const when = draft.occurred_local
    ? new Intl.DateTimeFormat(lang === "bn" ? "bn-BD" : "en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" })
        .format(new Date(`${draft.occurred_local}:00Z`))
    : "—";

  const rows: { step: number; label: string; value: ReactNode }[] = [
    { step: 0, label: t("report_check_place"), value: (
      <>
        {draft.place?.thana ? areaName(draft.place.thana, lang) : "—"}
        {draft.place?.ward && ` · ${areaName(draft.place.ward, lang)}`}
        {draft.landmark && <span className="block text-ink-soft">{draft.landmark}</span>}
      </>
    ) },
    { step: 1, label: t("report_check_what"), value: (
      <>
        {type ? (lang === "bn" ? type.name_bn : type.name_en) : "—"} · {when}
        {draft.stolen_items && <span className="block text-ink-soft">{draft.stolen_items}</span>}
        {photos.items.length > 0 && <span className="block text-ink-soft">{photos.items.length} {t("photo_count")}</span>}
      </>
    ) },
    { step: 2, label: draft.gd_type, value: (
      <>
        #{draft.gd_number} · {draft.gd_date}<span className="block text-ink-soft">{station ? areaName(station, lang) : "—"}</span>
        {(photos.gd.length > 0 || draft.gd_scan_id) && <span className="block text-ink-soft">{t("photo_gd_added")}</span>}
      </>
    ) },
  ];

  return (
    <div className="space-y-5">
      <ul className="divide-y divide-line rounded-2xl border border-line">
        {rows.map((row) => (
          <li key={row.step} className="flex items-start gap-4 p-4">
            <div className="flex-1">
              <p className="text-xs tracking-wide text-ink-soft uppercase">{row.label}</p>
              <p className="mt-1 text-sm text-ink">{row.value}</p>
            </div>
            <button type="button" onClick={() => goTo(row.step)}
                    className="inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-xs text-primary hover:bg-bg-soft">
              <Pencil size={13} aria-hidden /> {t("edit")}
            </button>
          </li>
        ))}
      </ul>
      {draft.description && (
        <p className="rounded-2xl bg-bg-soft p-4 text-sm whitespace-pre-line text-ink">{draft.description}</p>
      )}
      <label className="flex cursor-pointer items-start gap-3 rounded-2xl border border-line p-4 text-sm text-ink">
        <input type="checkbox" checked={draft.agree} onChange={(e) => change({ agree: e.target.checked })}
               className="mt-0.5 size-4 shrink-0 accent-[var(--primary)]" />
        <span>{t("report_agree")}<Problem text={errors.agree} /></span>
      </label>
    </div>
  );
}
