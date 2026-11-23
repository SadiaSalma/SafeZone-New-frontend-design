"use client";
/**
 * Frontend (web) · Task 16 · PhotoPicker.tsx - choose photos and see them as small previews.
 *
 *  - an "Add photo" tile opens the phone's camera or gallery
 *  - each chosen photo shows as a rounded preview with an × to remove it
 *  - we stop at `max` photos and refuse non-images or files over 5 MB right away
 *    (the backend checks again, and also removes hidden GPS data from every photo)
 *
 * The photos are only uploaded after the report is sent (see app/report/new/page.tsx).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { ImagePlus, X } from "lucide-react";
import { usePrefs } from "@/components/PreferencesProvider";

export const MAX_PHOTO_MB = 5;

type Props = {
  files: File[];
  onChange: (files: File[]) => void;
  max: number;
  label: string;
  hint?: string;
};

/** Is this file a photo we can take? Returns the problem, or "" if it's fine. */
export function photoProblem(file: File, t: (k: "photo_not_image" | "photo_too_big") => string) {
  if (!/^image\/(jpeg|png|webp)$/.test(file.type)) return t("photo_not_image");
  if (file.size > MAX_PHOTO_MB * 1024 * 1024) return t("photo_too_big");
  return "";
}

export function PhotoPicker({ files, onChange, max, label, hint }: Props) {
  const { t } = usePrefs();
  const input = useRef<HTMLInputElement>(null);
  const [problem, setProblem] = useState("");

  // Temporary addresses so the browser can show the chosen files; freed when they change
  const previews = useMemo(() => files.map((f) => URL.createObjectURL(f)), [files]);
  useEffect(() => () => previews.forEach((url) => URL.revokeObjectURL(url)), [previews]);

  function add(list: FileList | null) {
    if (!list) return;
    const good: File[] = [];
    let message = "";
    for (const file of Array.from(list)) {
      const bad = photoProblem(file, t);
      if (bad) message = bad;
      else good.push(file);
    }
    const room = max - files.length;
    if (good.length > room) message = t("photo_max").replace("{n}", String(max));
    onChange([...files, ...good.slice(0, room)]);
    setProblem(message);
    if (input.current) input.current.value = ""; // allow choosing the same file again
  }

  return (
    <div>
      <p className="mb-1.5 flex items-baseline justify-between gap-2 text-sm font-medium text-ink">
        {label}
        <span className="text-xs font-normal text-ink-soft">{hint ?? `${files.length}/${max}`}</span>
      </p>
      <div className="flex flex-wrap gap-3">
        {previews.map((url, i) => (
          <div key={url} className="rise relative size-24 overflow-hidden rounded-2xl border border-line bg-bg-soft">
            {/* eslint-disable-next-line @next/next/no-img-element -- a local preview, not a site image */}
            <img src={url} alt={`${label} ${i + 1}`} className="size-full object-cover" />
            <button type="button" onClick={() => onChange(files.filter((_, j) => j !== i))}
                    aria-label={`${t("photo_remove")} ${i + 1}`}
                    className="absolute top-1 right-1 grid size-7 place-items-center rounded-full bg-black/60 text-white hover:bg-black/80">
              <X size={14} />
            </button>
          </div>
        ))}
        {files.length < max && (
          <button type="button" onClick={() => input.current?.click()}
                  className="grid size-24 place-items-center rounded-2xl border-2 border-dashed border-line text-ink-soft transition hover:border-primary hover:text-primary">
            <span className="flex flex-col items-center gap-1 text-[11px]"><ImagePlus size={22} aria-hidden />{t("photo_add")}</span>
          </button>
        )}
      </div>
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" multiple={max > 1} hidden
             onChange={(e) => add(e.target.files)} />
      {problem && <p role="alert" className="mt-1.5 text-xs text-red-700">{problem}</p>}
    </div>
  );
}
