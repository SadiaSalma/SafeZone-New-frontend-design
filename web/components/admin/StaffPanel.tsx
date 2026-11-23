"use client";
/**
 * Frontend (web) · Task 30 · StaffPanel.tsx - verifiers and admins (FR-25).
 *
 *  - the list of staff with their role and status
 *  - "Add staff": name, phone number, a starting password, role (staff can't sign up themselves)
 *  - Suspend / Reactivate (a suspended person is logged out everywhere at once)
 *  - you can't suspend yourself (the backend refuses too)
 * Data: /api/v1/admin/staff (Task 30 backend).
 */
import { useCallback, useEffect, useState } from "react";
import { LoaderCircle, UserPlus } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import { usePrefs } from "@/components/PreferencesProvider";
import { api, ApiError } from "@/lib/api";

type Staff = { id: string; name_en: string; phone: string; role: "verifier" | "admin"; status: string };
const EMPTY = { name_en: "", phone: "", password: "", role: "verifier" as "verifier" | "admin" };

export function StaffPanel() {
  const { t } = usePrefs();
  const { user } = useAuth();
  const [staff, setStaff] = useState<Staff[] | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [problems, setProblems] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<{ staff: Staff[] }>("/admin/staff").then((d) => setStaff(d.staff)).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setProblems({}); setMessage("");
    try {
      const made = await api<Staff>("/admin/staff", { method: "POST", body: form });
      setForm(EMPTY);
      setMessage(t("adm_staff_added").replace("{name}", made.name_en));
      load();
    } catch (err) {
      const error = err as ApiError;
      setProblems(Object.keys(error.fields).length ? error.fields : { _: error.message });
    } finally {
      setBusy(false);
    }
  }

  async function change(person: Staff, status: "active" | "suspended") {
    setMessage("");
    try {
      await api(`/admin/staff/${person.id}`, { method: "PUT", body: { status } });
      load();
    } catch (err) {
      setMessage((err as ApiError).message);
    }
  }

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="soft-shadow rounded-[1.75rem] bg-surface p-5">
        <h2 className="mb-3 text-sm font-semibold tracking-wide text-ink-soft uppercase">{t("adm_tab_staff")}</h2>
        {!staff ? <LoaderCircle className="animate-spin text-ink-soft" /> : (
          <ul className="divide-y divide-line">
            {staff.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-ink">{p.name_en} {p.id === user?.id && <span className="text-xs text-ink-soft">({t("adm_you")})</span>}</p>
                  <p className="truncate text-xs text-ink-soft">{p.phone}</p>
                </div>
                <span className={`rounded-full px-2.5 py-0.5 text-xs ${p.role === "admin" ? "bg-primary/15 text-primary-strong" : "bg-bg-soft text-ink"}`}>
                  {t(p.role === "admin" ? "adm_role_admin" : "adm_role_verifier")}
                </span>
                <span className={`rounded-full px-2.5 py-0.5 text-xs ${p.status === "active" ? "bg-emerald-100 text-emerald-900" : "bg-red-100 text-red-900"}`}>
                  {t(p.status === "active" ? "adm_active" : "adm_suspended")}
                </span>
                {p.id !== user?.id && (
                  <button onClick={() => change(p, p.status === "active" ? "suspended" : "active")}
                          className="text-xs font-medium text-primary hover:underline">
                    {t(p.status === "active" ? "adm_suspend" : "adm_reactivate")}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
        {message && <p role="status" className="mt-3 rounded-xl bg-bg-soft px-3 py-2 text-sm text-ink">{message}</p>}
      </div>

      <form onSubmit={add} className="soft-shadow flex flex-col gap-2.5 rounded-[1.75rem] bg-surface p-5">
        <h2 className="flex items-center gap-2 text-sm font-semibold tracking-wide text-ink-soft uppercase">
          <UserPlus size={16} aria-hidden /> {t("adm_add_staff")}
        </h2>
        {(["name_en", "phone", "password"] as const).map((field) => (
          <label key={field} className="text-xs text-ink-soft">
            {t(`adm_field_${field}`)}
            <input value={form[field]} onChange={(e) => setForm({ ...form, [field]: e.target.value })} required
                   type={field === "password" ? "password" : field === "phone" ? "tel" : "text"} autoComplete="off"
                   className="mt-1 w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-ink" />
            {problems[field] && <span className="mt-0.5 block text-xs text-red-600">{problems[field]}</span>}
          </label>
        ))}
        <label className="text-xs text-ink-soft">
          {t("adm_field_role")}
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as "verifier" | "admin" })}
                  className="mt-1 w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm text-ink">
            <option value="verifier">{t("adm_role_verifier")}</option>
            <option value="admin">{t("adm_role_admin")}</option>
          </select>
        </label>
        {problems._ && <p className="text-xs text-red-600">{problems._}</p>}
        <button disabled={busy} className="mt-1 rounded-full bg-primary px-4 py-2.5 text-sm font-semibold text-on-primary disabled:opacity-60">
          {busy ? <LoaderCircle size={16} className="mx-auto animate-spin" /> : t("adm_add_staff")}
        </button>
        <p className="text-[11px] text-ink-soft">{t("adm_staff_note")}</p>
      </form>
    </div>
  );
}
