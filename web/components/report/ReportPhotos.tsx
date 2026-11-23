"use client";
/**
 * Frontend (web) · Task 16 · ReportPhotos.tsx - the photos of one report on "My reports".
 *
 *  - small rounded thumbnails (item photos, and the GD copy with a label)
 *  - while the report is still open: "Add photo" (uploads right away) and × to remove
 *  - tap a thumbnail to see it big
 *
 * Data: POST / DELETE /api/v1/me/reports/{id}/photos (Task 16 backend).
 */
import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ImagePlus, LoaderCircle, X } from "lucide-react";
import { usePrefs } from "@/components/PreferencesProvider";
import { photoProblem } from "@/components/report/PhotoPicker";
import { api, ApiError } from "@/lib/api";
import type { Report, ReportPhoto } from "@/lib/reports";

const OPEN = ["PENDING_REVIEW", "NEEDS_INFO"];

export function ReportPhotos({ report, onChanged }: { report: Report; onChanged: (r: Report) => void }) {
  const { t } = usePrefs();
  const input = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<"item" | "gd_copy">("item");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const [big, setBig] = useState<ReportPhoto | null>(null);
  const open = OPEN.includes(report.status);
  const items = report.photos.filter((p) => p.kind === "item").length;
  const hasGd = report.photos.some((p) => p.kind === "gd_copy");

  async function refresh() {
    onChanged(await api<Report>(`/me/reports/${report.id}`));
  }

  async function upload(file: File | undefined) {
    if (!file) return;
    const bad = photoProblem(file, t);
    if (bad) return setProblem(bad);
    setBusy(true);
    setProblem("");
    const form = new FormData();
    form.append("kind", kind);
    form.append("file", file);
    try {
      await api(`/me/reports/${report.id}/photos`, { method: "POST", body: form });
      await refresh();
    } catch (e) {
      setProblem((e as ApiError).message);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  async function remove(photo: ReportPhoto) {
    setBusy(true);
    try {
      await api(`/me/reports/${report.id}/photos/${photo.id}`, { method: "DELETE" });
      await refresh();
    } catch (e) {
      setProblem((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  function choose(which: "item" | "gd_copy") {
    setKind(which);
    input.current?.click();
  }

  if (!report.photos.length && !open) return null;

  return (
    <div className="mt-4">
      <p className="mb-2 text-xs text-ink-soft">{t("photos_title")}</p>
      <div className="flex flex-wrap items-center gap-2.5">
        {report.photos.map((photo) => (
          <div key={photo.id} className="relative size-20 overflow-hidden rounded-2xl border border-line bg-bg-soft">
            <button type="button" onClick={() => setBig(photo)} className="size-full" aria-label={t("photo_open")}>
              {/* eslint-disable-next-line @next/next/no-img-element -- a private photo served by our backend */}
              <img src={photo.url} alt="" className="size-full object-cover" loading="lazy" />
            </button>
            {photo.kind === "gd_copy" && (
              <span className="absolute inset-x-0 bottom-0 bg-black/60 py-0.5 text-center text-[10px] text-white">GD</span>
            )}
            {open && (
              <button type="button" disabled={busy} onClick={() => remove(photo)} aria-label={t("photo_remove")}
                      className="absolute top-1 right-1 grid size-6 place-items-center rounded-full bg-black/60 text-white hover:bg-black/80">
                <X size={12} />
              </button>
            )}
          </div>
        ))}
        {open && items < 3 && (
          <button type="button" disabled={busy} onClick={() => choose("item")}
                  className="grid size-20 place-items-center rounded-2xl border-2 border-dashed border-line text-ink-soft hover:border-primary hover:text-primary">
            {busy ? <LoaderCircle size={20} className="animate-spin" /> : (
              <span className="flex flex-col items-center gap-1 text-[10px]"><ImagePlus size={18} aria-hidden />{t("photo_add")}</span>
            )}
          </button>
        )}
        {open && !hasGd && (
          <button type="button" disabled={busy} onClick={() => choose("gd_copy")}
                  className="rounded-full border border-line px-3 py-1.5 text-xs text-ink hover:border-primary">
            + {t("photo_gd_short")}
          </button>
        )}
      </div>
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(e) => upload(e.target.files?.[0])} />
      {problem && <p role="alert" className="mt-2 text-xs text-red-700">{problem}</p>}

      {/* The big view is drawn straight into <body> (a "portal"), so no card around it can clip it */}
      {big && createPortal(
        <div role="dialog" aria-modal="true" onClick={() => setBig(null)}
             className="fixed inset-0 z-50 grid place-items-center bg-black/80 p-4 backdrop-blur-sm">
          {/* eslint-disable-next-line @next/next/no-img-element -- a private photo served by our backend */}
          <img src={big.url} alt="" className="max-h-[85vh] max-w-full rounded-2xl shadow-2xl" />
          <button type="button" onClick={() => setBig(null)} aria-label={t("close")}
                  className="absolute top-5 right-5 grid size-10 place-items-center rounded-full bg-white text-neutral-900">
            <X size={18} />
          </button>
        </div>,
        document.body,
      )}
    </div>
  );
}
