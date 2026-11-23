"use client";
/**
 * Frontend (web) · Task 29 · GdScan.tsx - "Scan your GD copy" on the GD step of the report form (FR-9).
 *
 *  1. The person takes (or picks) a photo of the GD paper.
 *  2. It is uploaded (POST /api/v1/gd-scans) and we ask for the result every second
 *     (GET /api/v1/gd-scans/{id}) while a scanning line moves over the photo.
 *  3. The boxes below fill themselves with what was read, and each one gets a "From photo" tag,
 *     so the person knows to CHECK it (the reading can be wrong; the person decides).
 *     Boxes the reader wasn't sure about stay empty, with a "please type" note (Design Revisions R10).
 *  4. The scanned photo also counts as the report's GD copy.
 *
 * If reading fails or takes too long, nothing breaks: the person simply types the details.
 */
import { useEffect, useRef, useState } from "react";
import { Camera, CircleAlert, LoaderCircle, RotateCcw, ScanText, Sparkles } from "lucide-react";
import { usePrefs } from "@/components/PreferencesProvider";
import { photoProblem } from "@/components/report/PhotoPicker";
import type { Draft } from "@/components/report/ReportSteps";
import { api, ApiError } from "@/lib/api";
import type { TextKey } from "@/lib/i18n";
import type { ReportOptions } from "@/lib/reports";

type Field = { value: string; confidence: number; name_en?: string; name_bn?: string };
export type GdScanResult = {
  id: string;
  status: "processing" | "done" | "failed";
  fields: Partial<Record<"gd_type" | "gd_number" | "gd_date" | "police_station" | "theft_type", Field>>;
  unsure: string[];
  seconds: number;
  message: string;
  message_bn: string;
  photo_url: string;
};

const FIELD_LABEL: Record<string, TextKey> = {
  gd_type: "scan_f_gd_type", gd_number: "scan_f_gd_number", gd_date: "scan_f_gd_date",
  police_station: "scan_f_police_station", theft_type: "scan_f_theft_type",
};

type Props = {
  draft: Draft;
  change: (part: Partial<Draft>) => void;
  options: ReportOptions;
};

export function GdScan({ draft, change, options }: Props) {
  const { t, lang } = usePrefs();
  const input = useRef<HTMLInputElement>(null);
  const [phase, setPhase] = useState<"idle" | "reading" | "done" | "failed">(draft.gd_scan_id ? "done" : "idle");
  const [scan, setScan] = useState<GdScanResult | null>(null);
  const [preview, setPreview] = useState("");
  const [problem, setProblem] = useState("");

  // A scan saved in the draft (e.g. after a page reload): show it again
  useEffect(() => {
    if (!draft.gd_scan_id || scan) return;
    api<GdScanResult>(`/gd-scans/${draft.gd_scan_id}`)
      .then((s) => { setScan(s); setPhase(s.status === "failed" ? "failed" : "done"); })
      .catch(() => { change({ gd_scan_id: null, ocr_filled: [] }); setPhase("idle"); }); // older than 24 hours: gone
  }, [draft.gd_scan_id, scan, change]);

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  function apply(result: GdScanResult) {
    const f = result.fields;
    const part: Partial<Draft> = { gd_scan_id: result.id };
    const filled: string[] = [];
    if (f.gd_type) { part.gd_type = f.gd_type.value as "GD" | "FIR"; filled.push("gd_type"); }
    if (f.gd_number) { part.gd_number = f.gd_number.value; filled.push("gd_number"); }
    if (f.gd_date) { part.gd_date = f.gd_date.value; filled.push("gd_date"); }
    if (f.police_station) { part.police_station = f.police_station.value; filled.push("police_station"); }
    if (f.theft_type && !draft.theft_type) { part.theft_type = f.theft_type.value; filled.push("theft_type"); }
    change({ ...part, ocr_filled: filled });
  }

  async function choose(file: File | undefined) {
    if (!file) return;
    const wrong = photoProblem(file, t);
    if (wrong) { setProblem(wrong); return; }
    setProblem("");
    setPreview(URL.createObjectURL(file));
    setPhase("reading");
    try {
      const form = new FormData();
      form.append("file", file);
      let result = await api<GdScanResult>("/gd-scans", { method: "POST", body: form });
      for (let i = 0; result.status === "processing" && i < 40; i++) { // ask every second, at most 40 s
        await new Promise((r) => setTimeout(r, 1000));
        result = await api<GdScanResult>(`/gd-scans/${result.id}`);
      }
      setScan(result);
      if (result.status === "done") {
        apply(result);
        setPhase("done");
      } else {
        change({ gd_scan_id: result.id, ocr_filled: [] }); // the photo still counts as the GD copy
        setPhase("failed");
      }
    } catch (e) {
      setProblem((e as ApiError).message);
      setPhase("idle");
      setPreview("");
    }
  }

  function again() {
    change({ gd_scan_id: null, ocr_filled: [] });
    setScan(null);
    setPreview("");
    setPhase("idle");
    input.current?.click();
  }

  const shown = preview || scan?.photo_url || "";
  const found = scan ? Object.entries(scan.fields) : [];

  return (
    <div className="overflow-hidden rounded-[1.5rem] border border-dashed border-primary/40 bg-primary/5">
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" capture="environment" className="hidden"
             onChange={(e) => { choose(e.target.files?.[0]); e.target.value = ""; }} />

      {phase === "idle" ? (
        <button type="button" onClick={() => input.current?.click()}
                className="flex w-full items-center gap-4 p-5 text-left transition hover:bg-primary/10">
          <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-primary text-on-primary shadow">
            <ScanText size={24} aria-hidden />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block font-semibold text-ink">{t("scan_title")}</span>
            <span className="block text-sm text-ink-soft">{t("scan_sub")}</span>
          </span>
          <span className="hidden shrink-0 items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-on-primary sm:inline-flex">
            <Camera size={16} aria-hidden /> {t("scan_button")}
          </span>
        </button>
      ) : (
        <div className="flex flex-col gap-4 p-4 sm:flex-row">
          {/* The photo, with a scanning line while it is read */}
          <div className="relative h-44 w-full shrink-0 overflow-hidden rounded-2xl bg-black/5 sm:w-36">
            {shown && (
              // eslint-disable-next-line @next/next/no-img-element -- a local preview / a private photo, not for next/image
              <img src={shown} alt={t("scan_photo_alt")} className="size-full object-cover" />
            )}
            {phase === "reading" && <span className="sz-scanline" aria-hidden />}
          </div>

          <div className="min-w-0 flex-1" aria-live="polite">
            {phase === "reading" && (
              <p className="flex items-center gap-2 font-medium text-ink">
                <LoaderCircle size={18} className="animate-spin text-primary" aria-hidden /> {t("scan_reading")}
              </p>
            )}
            {phase === "done" && scan && (
              <>
                <p className="flex items-center gap-2 font-semibold text-ink">
                  <Sparkles size={18} className="text-primary" aria-hidden />
                  {t("scan_done").replace("{n}", String(found.length))}
                </p>
                <ul className="mt-2 space-y-1 text-sm">
                  {found.map(([key, f]) => (
                    <li key={key} className="flex flex-wrap items-baseline gap-x-2">
                      <span className="text-ink-soft">{t(FIELD_LABEL[key])}:</span>
                      <span className="font-medium text-ink">{fieldText(key, f!, lang, options)}</span>
                      <span className="text-xs text-ink-soft">{Math.round(f!.confidence)}%</span>
                    </li>
                  ))}
                </ul>
                {scan.unsure.length > 0 && (
                  <p className="mt-2 flex items-start gap-1.5 text-xs text-amber-800">
                    <CircleAlert size={14} className="mt-0.5 shrink-0" aria-hidden />
                    {t("scan_unsure").replace("{fields}", scan.unsure.map((k) => t(FIELD_LABEL[k])).join(", "))}
                  </p>
                )}
                <p className="mt-2 text-xs text-ink-soft">{t("scan_check")}</p>
              </>
            )}
            {phase === "failed" && (
              <p className="flex items-start gap-2 text-sm text-ink">
                <CircleAlert size={18} className="mt-0.5 shrink-0 text-amber-600" aria-hidden />
                <span>{scan ? (lang === "bn" ? scan.message_bn : scan.message) : t("scan_failed")} {t("scan_kept")}</span>
              </p>
            )}
            {phase !== "reading" && (
              <button type="button" onClick={again} className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline">
                <RotateCcw size={14} aria-hidden /> {t("scan_again")}
              </button>
            )}
          </div>
        </div>
      )}
      {problem && <p role="alert" className="px-5 pb-4 text-sm text-red-600">{problem}</p>}
    </div>
  );
}

function fieldText(key: string, f: Field, lang: "en" | "bn", options: ReportOptions): string {
  if (key === "police_station") return (lang === "bn" ? f.name_bn : f.name_en) || f.value;
  if (key === "theft_type" || key === "gd_type") {
    const list: { code: string; name_en: string; name_bn: string }[] = key === "theft_type" ? options.theft_types : options.gd_types;
    const type = list.find((x) => x.code === f.value);
    return type ? (lang === "bn" ? type.name_bn : type.name_en) : f.value;
  }
  if (key === "gd_date") {
    return new Intl.DateTimeFormat(lang === "bn" ? "bn-BD" : "en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })
      .format(new Date(`${f.value}T00:00:00Z`));
  }
  return f.value;
}

/** The small tag next to a box the photo filled in. */
export function FromPhoto() {
  const { t } = usePrefs();
  return (
    <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-primary/12 px-2 py-0.5 align-middle text-[11px] font-medium text-primary-strong">
      <Sparkles size={11} aria-hidden /> {t("scan_from_photo")}
    </span>
  );
}
