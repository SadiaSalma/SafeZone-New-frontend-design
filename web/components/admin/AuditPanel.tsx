"use client";
/**
 * Frontend (web) · Task 30 · AuditPanel.tsx - the audit log (FR-27), newest first, 50 per page.
 *
 *  - filter by kind of action (reports, decisions, alerts, staff, areas, settings ...)
 *  - each line: when, who (staff by name; victims only as "Victim" - privacy, R8), what, and
 *    which fields changed (the log never holds personal values, only field names)
 * Data: GET /api/v1/admin/audit-logs (Task 30 backend). Nobody can edit or delete these lines.
 */
import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, LoaderCircle } from "lucide-react";
import { usePrefs } from "@/components/PreferencesProvider";
import { api } from "@/lib/api";
import { dhakaTime } from "@/lib/reports";

type Entry = { id: string; action: string; entity: string; entity_id: string | null; actor_role: string; actor_name: string;
  after: Record<string, unknown>; created_at: string };
type Page = { page: number; total: number; entries: Entry[] };
const FILTERS = ["", "report.", "alert.", "user.", "staff.", "area.", "police_station.", "gd_format.", "settings.", "crime", "simulator."];

function details(after: Record<string, unknown>) {
  return Object.entries(after)
    .filter(([k, v]) => !k.endsWith("_id") && v !== null && v !== "" && typeof v !== "object")
    .map(([k, v]) => `${k}: ${String(v)}`)
    .concat(Array.isArray(after.changed) ? [`changed: ${(after.changed as string[]).join(", ")}`] : [])
    .join(" · ");
}

export function AuditPanel() {
  const { t, lang } = usePrefs();
  const [action, setAction] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page | null>(null);

  useEffect(() => {
    let current = true;
    api<Page>(`/admin/audit-logs?page=${page}${action ? `&action=${encodeURIComponent(action)}` : ""}`)
      .then((d) => current && setData(d)).catch(() => {});
    return () => { current = false; };
  }, [page, action]);

  const pages = data ? Math.max(1, Math.ceil(data.total / 50)) : 1;
  return (
    <div className="soft-shadow rounded-[1.75rem] bg-surface p-5">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <select value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }} aria-label={t("adm_audit_filter")}
                className="rounded-full border border-line bg-bg px-4 py-2 text-sm text-ink">
          {FILTERS.map((f) => <option key={f} value={f}>{f ? f.replace(/\.$/, "") : t("adm_audit_all")}</option>)}
        </select>
        {data && <span className="text-sm text-ink-soft">{t("adm_audit_count").replace("{n}", String(data.total))}</span>}
        <span className="ml-auto inline-flex items-center gap-1">
          <button onClick={() => setPage(page - 1)} disabled={page <= 1} aria-label={t("adm_prev")}
                  className="rounded-full p-1.5 text-ink hover:bg-bg-soft disabled:opacity-30"><ChevronLeft size={18} /></button>
          <span className="text-sm text-ink-soft">{page} / {pages}</span>
          <button onClick={() => setPage(page + 1)} disabled={page >= pages} aria-label={t("adm_next")}
                  className="rounded-full p-1.5 text-ink hover:bg-bg-soft disabled:opacity-30"><ChevronRight size={18} /></button>
        </span>
      </div>
      <p className="mb-3 text-xs text-ink-soft">{t("adm_audit_note")}</p>
      {!data ? <LoaderCircle className="animate-spin text-ink-soft" /> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] text-sm">
            <thead><tr className="text-left text-xs text-ink-soft">
              <th className="pb-2 font-normal">{t("adm_when")}</th><th className="pb-2 font-normal">{t("adm_who")}</th>
              <th className="pb-2 font-normal">{t("adm_what")}</th><th className="pb-2 font-normal">{t("adm_details")}</th>
            </tr></thead>
            <tbody>
              {data.entries.map((e) => (
                <tr key={e.id} className="border-t border-line align-top">
                  <td className="py-2 pr-3 text-xs whitespace-nowrap text-ink-soft">{dhakaTime(e.created_at, lang)}</td>
                  <td className="py-2 pr-3 text-ink">{e.actor_name || <span className="text-ink-soft">{e.actor_role || "—"}</span>}</td>
                  <td className="py-2 pr-3"><code className="rounded bg-bg-soft px-1.5 py-0.5 text-xs text-ink">{e.action}</code></td>
                  <td className="max-w-[320px] py-2 text-xs break-words text-ink-soft">{details(e.after) || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
