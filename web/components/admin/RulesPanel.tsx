"use client";
/**
 * Frontend (web) · Task 30 · RulesPanel.tsx - the rules behind the automatic checks (Task 17).
 *
 *  GD formats:     the patterns a GD number may have. A new pattern needs an example that matches it
 *                  (the backend checks both). Switch a pattern off instead of deleting it.
 *  Risk settings:  how many points each warning adds to the risk score, and where Medium / High start.
 *                  The score preview shows what the verifier will see.
 * Data: /api/v1/admin/gd-formats and /api/v1/admin/settings/risk (Task 30 backend).
 */
import { useCallback, useEffect, useState } from "react";
import { CircleCheck, LoaderCircle, Plus, Save } from "lucide-react";
import { usePrefs } from "@/components/PreferencesProvider";
import { api, ApiError } from "@/lib/api";
import type { TextKey } from "@/lib/i18n";

type GdFormat = { id: string; regex: string; example: string; label: string; is_active: boolean };
type Risk = { risk_points: Record<string, number>; risk_levels: { medium_from: number; high_from: number } };
const POINT_KEYS = ["gd_format", "gd_timing", "place_in_gd_thana", "nearby_duplicate", "history", "gd_copy", "ocr_mismatch"] as const;

export function GdFormatsPanel() {
  const { t } = usePrefs();
  const [formats, setFormats] = useState<GdFormat[] | null>(null);
  const [form, setForm] = useState({ regex: "", example: "", label: "" });
  const [problems, setProblems] = useState<Record<string, string>>({});

  const load = useCallback(() => {
    api<{ formats: GdFormat[] }>("/admin/gd-formats").then((d) => setFormats(d.formats)).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setProblems({});
    try {
      await api("/admin/gd-formats", { method: "POST", body: form });
      setForm({ regex: "", example: "", label: "" });
      load();
    } catch (err) {
      const error = err as ApiError;
      setProblems(Object.keys(error.fields).length ? error.fields : { _: error.message });
    }
  }

  async function toggle(f: GdFormat) {
    await api(`/admin/gd-formats/${f.id}`, { method: "PUT", body: { is_active: !f.is_active } }).catch(() => {});
    load();
  }

  return (
    <div className="soft-shadow rounded-[1.75rem] bg-surface p-5">
      <h2 className="text-sm font-semibold tracking-wide text-ink-soft uppercase">{t("adm_tab_gd")}</h2>
      <p className="mt-1 text-sm text-ink-soft">{t("adm_gd_sub")}</p>
      {!formats ? <LoaderCircle className="mt-4 animate-spin text-ink-soft" /> : (
        <ul className="mt-4 grid gap-2 md:grid-cols-2">
          {formats.map((f) => (
            <li key={f.id} className={`flex items-center gap-3 rounded-2xl border border-line p-3 ${f.is_active ? "" : "opacity-50"}`}>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-ink">{f.label || "—"}</p>
                <p className="truncate font-mono text-xs text-ink-soft">{f.regex}</p>
                <p className="text-xs text-ink-soft">{t("adm_example")}: <span className="font-mono text-ink">{f.example}</span></p>
              </div>
              <button onClick={() => toggle(f)} className="text-xs font-medium text-primary hover:underline">
                {f.is_active ? t("crime_switch_off") : t("crime_switch_on")}
              </button>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={add} className="mt-4 grid gap-2 rounded-2xl bg-bg-soft p-3 sm:grid-cols-[1fr_1fr_1fr_auto] sm:items-start">
        {(["regex", "example", "label"] as const).map((field) => (
          <label key={field} className="text-xs text-ink-soft">
            {t(`adm_gd_${field}`)}
            <input value={form[field]} onChange={(e) => setForm({ ...form, [field]: e.target.value })} required={field !== "label"}
                   placeholder={field === "regex" ? "^DMP-\\d{4}$" : field === "example" ? "DMP-1234" : ""}
                   className={`mt-1 w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-ink ${field !== "label" ? "font-mono" : ""}`} />
            {problems[field] && <span className="mt-0.5 block text-xs text-red-600">{problems[field]}</span>}
          </label>
        ))}
        <button className="mt-5 inline-flex items-center justify-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-on-primary">
          <Plus size={15} aria-hidden /> {t("crime_add")}
        </button>
        {problems._ && <p className="text-xs text-red-600 sm:col-span-4">{problems._}</p>}
      </form>
    </div>
  );
}

export function RiskPanel() {
  const { t } = usePrefs();
  const [risk, setRisk] = useState<Risk | null>(null);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    api<Risk>("/admin/settings/risk").then(setRisk).catch(() => {});
  }, []);

  if (!risk) return <div className="grid h-40 place-items-center"><LoaderCircle className="animate-spin text-ink-soft" /></div>;

  async function save() {
    setNote(null);
    try {
      setRisk(await api<Risk>("/admin/settings/risk", { method: "PUT", body: risk }));
      setNote({ ok: true, text: t("adm_saved") });
    } catch (err) {
      const error = err as ApiError;
      setNote({ ok: false, text: Object.values(error.fields)[0] ?? error.message });
    }
  }

  const levels = risk.risk_levels;
  const setPoint = (key: string, value: number) => setRisk({ ...risk, risk_points: { ...risk.risk_points, [key]: value } });
  const number = "w-20 rounded-lg border border-line bg-bg px-2 py-1.5 text-center text-sm text-ink";

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="soft-shadow rounded-[1.75rem] bg-surface p-5">
        <h2 className="text-sm font-semibold tracking-wide text-ink-soft uppercase">{t("adm_points")}</h2>
        <p className="mt-1 text-sm text-ink-soft">{t("adm_points_sub")}</p>
        <ul className="mt-4 divide-y divide-line">
          {POINT_KEYS.map((key) => (
            <li key={key} className="flex items-center gap-3 py-2.5">
              <span className="flex-1 text-sm text-ink">{t(`adm_point_${key}` as TextKey)}</span>
              <input type="number" min={0} max={100} value={risk.risk_points[key] ?? 0} aria-label={t(`adm_point_${key}` as TextKey)}
                     onChange={(e) => setPoint(key, Number(e.target.value))} className={number} />
            </li>
          ))}
        </ul>
      </div>
      <div className="soft-shadow flex flex-col gap-3 rounded-[1.75rem] bg-surface p-5">
        <h2 className="text-sm font-semibold tracking-wide text-ink-soft uppercase">{t("adm_levels")}</h2>
        <label className="flex items-center justify-between text-sm text-ink">{t("adm_medium_from")}
          <input type="number" min={1} max={99} value={levels.medium_from} className={number}
                 onChange={(e) => setRisk({ ...risk, risk_levels: { ...levels, medium_from: Number(e.target.value) } })} /></label>
        <label className="flex items-center justify-between text-sm text-ink">{t("adm_high_from")}
          <input type="number" min={2} max={100} value={levels.high_from} className={number}
                 onChange={(e) => setRisk({ ...risk, risk_levels: { ...levels, high_from: Number(e.target.value) } })} /></label>
        {/* What the verifier's meter will show: Low | Medium | High along 0-100 */}
        <div aria-hidden className="mt-1 flex h-3 gap-[2px] overflow-hidden rounded-full">
          <span className="bg-emerald-500" style={{ width: `${levels.medium_from}%` }} />
          <span className="bg-amber-400" style={{ width: `${Math.max(0, levels.high_from - levels.medium_from)}%` }} />
          <span className="flex-1 bg-red-500" />
        </div>
        <p className="flex justify-between text-[11px] text-ink-soft">
          <span>{t("level_low")} 0–{levels.medium_from - 1}</span><span>{t("level_medium")}</span><span>{t("level_high")} {levels.high_from}+</span>
        </p>
        <button onClick={save} className="mt-2 inline-flex items-center justify-center gap-1.5 rounded-full bg-primary px-4 py-2.5 text-sm font-semibold text-on-primary">
          <Save size={15} aria-hidden /> {t("adm_save")}
        </button>
        {note && <p role="status" className={`flex items-center gap-1 text-sm ${note.ok ? "text-emerald-700" : "text-red-600"}`}>
          {note.ok && <CircleCheck size={15} aria-hidden />} {note.text}</p>}
        <p className="text-[11px] text-ink-soft">{t("adm_levels_note")}</p>
      </div>
    </div>
  );
}
