"use client";
/**
 * Frontend (web) · Task 30 · PlacesPanel.tsx - thanas, wards and police stations (FR-25).
 *
 *  Areas:    rename (English / Bangla), switch on/off; for WARDS also the alert radius (300-3000 m, FR-17:
 *            an alert reaches as far as the radius of the ward the theft happened in). Thanas show their size.
 *  Stations: rename, phone number, switch on/off (a switched-off station is not offered on the report form)
 * A changed field is saved when you leave it (no extra "Save" button). A search box filters the list.
 * Data: /api/v1/admin/areas and /api/v1/admin/stations (Task 30 backend).
 */
import { useCallback, useEffect, useState } from "react";
import { CircleCheck, LoaderCircle, Search } from "lucide-react";
import { usePrefs } from "@/components/PreferencesProvider";
import { api, ApiError } from "@/lib/api";

type AreaRow = { code: string; name_en: string; name_bn: string; size_km2: number | null; alert_radius_m: number; is_active: boolean };
type StationRow = { code: string; name_en: string; name_bn: string; phone: string; is_active: boolean };

export function PlacesPanel({ kind }: { kind: "areas" | "stations" }) {
  const { t } = usePrefs();
  const [level, setLevel] = useState<"thana" | "ward">("thana");
  const [rows, setRows] = useState<(AreaRow | StationRow)[] | null>(null);
  const [filter, setFilter] = useState("");
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  const path = kind === "areas" ? `/admin/areas?type=${level}` : "/admin/stations";
  const load = useCallback(() => {
    api<{ areas?: AreaRow[]; stations?: StationRow[] }>(path).then((d) => setRows(d.areas ?? d.stations ?? [])).catch(() => {});
  }, [path]);
  useEffect(() => { load(); }, [load]);

  async function save(code: string, part: Record<string, unknown>) {
    setNote(null);
    try {
      await api(`/admin/${kind}/${code}`, { method: "PUT", body: part });
      setNote({ ok: true, text: t("adm_saved") });
      load();
    } catch (err) {
      const error = err as ApiError;
      setNote({ ok: false, text: Object.values(error.fields)[0] ?? error.message });
    }
  }

  const shown = (rows ?? []).filter((r) => `${r.name_en} ${r.name_bn} ${r.code}`.toLowerCase().includes(filter.toLowerCase()));
  const input = "w-full rounded-lg border border-line bg-bg px-2 py-1.5 text-sm text-ink";

  return (
    <div className="soft-shadow rounded-[1.75rem] bg-surface p-5">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        {kind === "areas" && (
          <div className="inline-flex rounded-full bg-bg-soft p-1">
            {(["thana", "ward"] as const).map((l) => (
              <button key={l} onClick={() => { setLevel(l); setRows(null); }} aria-pressed={level === l}
                      className={`rounded-full px-3.5 py-1.5 text-sm ${level === l ? "bg-primary font-medium text-on-primary" : "text-ink-soft"}`}>
                {t(l === "thana" ? "areas_thanas" : "areas_wards")}
              </button>
            ))}
          </div>
        )}
        <label className="flex flex-1 items-center gap-2 rounded-full border border-line bg-bg px-3 py-1.5 text-sm">
          <Search size={15} className="text-ink-soft" aria-hidden />
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder={t("adm_search")} aria-label={t("adm_search")}
                 className="w-full bg-transparent text-ink outline-none" />
        </label>
        {note && (
          <span role="status" className={`inline-flex items-center gap-1 text-sm ${note.ok ? "text-emerald-700" : "text-red-600"}`}>
            {note.ok && <CircleCheck size={15} aria-hidden />} {note.text}
          </span>
        )}
      </div>
      <p className="mb-3 text-xs text-ink-soft">{t(kind === "areas" ? "adm_areas_note" : "adm_stations_note")}</p>

      {!rows ? <LoaderCircle className="animate-spin text-ink-soft" /> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead><tr className="text-left text-xs text-ink-soft">
              <th className="pb-2 font-normal">{t("adm_code")}</th>
              <th className="pb-2 font-normal">{t("adm_name_en")}</th>
              <th className="pb-2 font-normal">{t("adm_name_bn")}</th>
              <th className="pb-2 font-normal">{kind === "stations" ? t("adm_phone") : level === "ward" ? t("adm_radius") : t("adm_size")}</th>
              <th className="pb-2 text-right font-normal">{t("adm_on")}</th>
            </tr></thead>
            <tbody>
              {shown.map((r) => (
                <tr key={`${r.code}-${r.is_active}`} className={`border-t border-line ${r.is_active ? "" : "opacity-55"}`}>
                  <td className="py-2 pr-2 text-xs text-ink-soft">{r.code}</td>
                  <td className="py-2 pr-2"><input defaultValue={r.name_en} aria-label={`${t("adm_name_en")} ${r.code}`} className={input}
                                                   onBlur={(e) => e.target.value !== r.name_en && save(r.code, { name_en: e.target.value })} /></td>
                  <td className="py-2 pr-2"><input defaultValue={r.name_bn} lang="bn" aria-label={`${t("adm_name_bn")} ${r.code}`} className={input}
                                                   onBlur={(e) => e.target.value !== r.name_bn && save(r.code, { name_bn: e.target.value })} /></td>
                  <td className="py-2 pr-2">
                    {"alert_radius_m" in r && level === "thana" ? (
                      <span className="text-sm text-ink-soft">{r.size_km2 ?? "—"} km²</span>
                    ) : "alert_radius_m" in r ? (
                      <span className="flex items-center gap-1">
                        <input type="number" min={300} max={3000} step={100} defaultValue={r.alert_radius_m} aria-label={`${t("adm_radius")} ${r.code}`}
                               className={`${input} w-24`}
                               onBlur={(e) => Number(e.target.value) !== r.alert_radius_m && save(r.code, { alert_radius_m: Number(e.target.value) })} />
                        <span className="text-xs text-ink-soft">m</span>
                      </span>
                    ) : (
                      <input defaultValue={(r as StationRow).phone} inputMode="tel" aria-label={`${t("adm_phone")} ${r.code}`} className={input}
                             onBlur={(e) => e.target.value !== (r as StationRow).phone && save(r.code, { phone: e.target.value })} />
                    )}
                  </td>
                  <td className="py-2 text-right">
                    <button onClick={() => save(r.code, { is_active: !r.is_active })} role="switch" aria-checked={r.is_active}
                            aria-label={`${t("adm_on")} ${r.code}`}
                            className={`relative h-6 w-11 rounded-full transition ${r.is_active ? "bg-primary" : "bg-line"}`}>
                      <span className={`absolute top-0.5 size-5 rounded-full bg-white shadow transition-all ${r.is_active ? "left-[22px]" : "left-0.5"}`} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
