"use client";
/**
 * Frontend (web) · Task 31 · /me/delete - "Delete my data" (FR-4, Design Revisions R8).
 *
 * Three steps:
 *   1. What happens: a clear list of what is DELETED and what is KEPT (as anonymous statistics),
 *      with the person's own numbers (reports, waiting reports, photos). Type the password -> a code is sent by SMS.
 *   2. The code: six boxes + "I understand this can't be undone" -> Delete my data (red).
 *   3. Done: the account is gone and this browser is logged out.
 *
 * Staff accounts can't use this page (an admin suspends them instead - Task 30).
 * Data: GET /api/v1/me/delete, POST /api/v1/me/delete/request, POST /api/v1/me/delete/confirm (Task 31 backend).
 */
import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Check, CircleCheck, KeyRound, LoaderCircle, ShieldAlert, Trash2, X } from "lucide-react";
import busyStreet from "@/public/images/delete-busy-street-rickshaw.jpg";
import { useAuth } from "@/components/AuthProvider";
import { CodeBoxes, EMPTY_CODE } from "@/components/auth/CodeBoxes";
import { DemoSms } from "@/components/auth/DemoSms";
import { usePrefs } from "@/components/PreferencesProvider";
import { api, ApiError } from "@/lib/api";
import type { TextKey } from "@/lib/i18n";

type Summary = { reports: number; waiting: number; photos: number; push_subscriptions: number; nid_added: boolean; phone_masked: string };
type Step = "info" | "code" | "done";

const DELETED: TextKey[] = ["del_gone_account", "del_gone_nid", "del_gone_details", "del_gone_photos", "del_gone_logins"];
const KEPT: TextKey[] = ["del_kept_reports", "del_kept_alerts", "del_kept_log"];

export default function DeleteMyDataPage() {
  const { t } = usePrefs();
  const { user, loading, setUser } = useAuth();
  const [step, setStep] = useState<Step>("info");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [password, setPassword] = useState("");
  const [digits, setDigits] = useState(EMPTY_CODE);
  const [sure, setSure] = useState(false);
  const [notice, setNotice] = useState("");
  const [demoCode, setDemoCode] = useState<string | null>(null); // development only
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const boxes = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => {
    if (user?.role === "victim") api<Summary>("/me/delete").then(setSummary).catch(() => {});
  }, [user]);

  async function askForCode(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const answer = await api<{ message: string; demo_code: string | null }>("/me/delete/request", { method: "POST", body: { password } });
      setNotice(answer.message);
      setDemoCode(answer.demo_code);
      setPassword("");
      setStep("code");
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setBusy(false);
    }
  }

  async function confirm(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      await api("/me/delete/confirm", { method: "POST", body: { code: digits.join("") } });
      setStep("done");
      setUser(null); // the backend already removed the log-in cookies
    } catch (err) {
      setError(err as ApiError);
      setDigits(EMPTY_CODE);
      boxes.current[0]?.focus();
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section data-photo-hero className="relative -mt-16 h-[34svh] min-h-[280px] overflow-hidden bg-black">
        <Image src={busyStreet} alt="A busy Dhaka street full of rickshaws" fill preload placeholder="blur"
               sizes="100vw" className="drift object-cover" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-black/35 to-bg" />
        <div className="rise relative mx-auto flex h-full max-w-3xl flex-col justify-end px-4 pb-10 text-white">
          <h1 className="text-4xl font-semibold md:text-5xl">{t("del_title")}</h1>
          <p className="mt-2 max-w-xl text-white/80">{t("del_sub")}</p>
        </div>
      </section>

      <section className="mx-auto -mt-4 max-w-3xl px-4">
        {step === "done" ? (
          <div className="soft-shadow rise rounded-[1.75rem] bg-surface p-8 text-center">
            <CircleCheck size={44} className="mx-auto text-emerald-600" aria-hidden />
            <h2 className="mt-3 text-2xl font-semibold text-ink">{t("del_done_title")}</h2>
            <p className="mx-auto mt-2 max-w-md text-ink-soft">{t("del_done_sub")}</p>
            <Link href="/" className="mt-6 inline-flex rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-on-primary">{t("del_home")}</Link>
          </div>
        ) : loading ? (
          <div className="grid h-40 place-items-center"><LoaderCircle className="animate-spin text-ink-soft" /></div>
        ) : !user ? (
          <div className="soft-shadow rounded-[1.75rem] bg-surface p-8 text-ink">
            <p>{t("del_login")}</p>
            <Link href="/login" className="mt-4 inline-flex rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-on-primary">{t("login")}</Link>
          </div>
        ) : user.role !== "victim" ? (
          <div className="soft-shadow rounded-[1.75rem] bg-surface p-8 text-ink">{t("del_staff")}</div>
        ) : (
          <div className="flex flex-col gap-4">
            {/* What is deleted and what is kept */}
            <div className="soft-shadow grid gap-5 rounded-[1.75rem] bg-surface p-6 md:grid-cols-2">
              <div>
                <h2 className="mb-3 text-sm font-semibold tracking-wide text-red-700 uppercase">{t("del_gone")}</h2>
                <ul className="space-y-2.5 text-sm text-ink">
                  {DELETED.map((k) => (
                    <li key={k} className="flex gap-2"><X size={16} className="mt-0.5 shrink-0 text-red-600" aria-hidden /> {t(k)}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h2 className="mb-3 text-sm font-semibold tracking-wide text-ink-soft uppercase">{t("del_kept")}</h2>
                <ul className="space-y-2.5 text-sm text-ink">
                  {KEPT.map((k) => (
                    <li key={k} className="flex gap-2"><Check size={16} className="mt-0.5 shrink-0 text-primary" aria-hidden /> {t(k)}</li>
                  ))}
                </ul>
              </div>
              {summary && (
                <p className="rounded-2xl bg-bg-soft px-4 py-3 text-sm text-ink md:col-span-2">
                  {t("del_yours").replace("{reports}", String(summary.reports)).replace("{waiting}", String(summary.waiting))
                    .replace("{photos}", String(summary.photos))}
                </p>
              )}
            </div>

            {step === "info" && (
              <form onSubmit={askForCode} className="soft-shadow rounded-[1.75rem] bg-surface p-6">
                <h2 className="flex items-center gap-2 font-semibold text-ink"><KeyRound size={18} aria-hidden /> {t("del_step1")}</h2>
                <p className="mt-1 text-sm text-ink-soft">
                  {t("del_step1_sub").replace("{phone}", summary?.phone_masked ?? "")}
                </p>
                <label className="mt-4 block text-sm text-ink">
                  {t("field_password")}
                  <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password"
                         className="mt-1 w-full rounded-xl border border-line bg-bg px-3 py-2.5 text-ink" />
                </label>
                {error && <p role="alert" className="mt-2 text-sm text-red-600">{error.fields.password ?? error.message}</p>}
                <div className="mt-5 flex flex-wrap items-center gap-3">
                  <button disabled={busy || !password} className="inline-flex items-center gap-2 rounded-full bg-ink px-5 py-2.5 text-sm font-semibold text-bg disabled:opacity-50">
                    {busy && <LoaderCircle size={16} className="animate-spin" aria-hidden />} {t("del_send_code")}
                  </button>
                  <Link href="/me/reports" className="text-sm text-ink-soft hover:text-ink">{t("del_cancel")}</Link>
                </div>
              </form>
            )}

            {step === "code" && (
              <form onSubmit={confirm} className="rise rounded-[1.75rem] bg-neutral-900 p-6 text-white shadow-xl">
                <h2 className="mb-1 flex items-center gap-2 font-semibold"><ShieldAlert size={18} aria-hidden /> {t("del_step2")}</h2>
                {notice && <p role="status" className="mb-5 text-sm text-white/75">{notice}</p>}
                <DemoSms code={demoCode} purpose="delete" />
                <CodeBoxes digits={digits} onChange={setDigits} label={t("code_label")} boxes={boxes} />
                <label className="-mt-3 flex items-start gap-2.5 text-sm text-white/90">
                  <input type="checkbox" checked={sure} onChange={(e) => setSure(e.target.checked)} className="mt-0.5 size-4 accent-red-500" />
                  {t("del_sure")}
                </label>
                {error && <p role="alert" className="mt-3 text-sm text-red-300">{error.fields.code ?? error.message}</p>}
                <div className="mt-5 flex flex-wrap items-center gap-3">
                  <button disabled={busy || !sure || digits.join("").length !== 6}
                          className="inline-flex items-center gap-2 rounded-full bg-red-600 px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-40">
                    {busy ? <LoaderCircle size={16} className="animate-spin" aria-hidden /> : <Trash2 size={16} aria-hidden />} {t("del_button")}
                  </button>
                  <Link href="/me/reports" className="text-sm text-white/70 hover:text-white">{t("del_cancel")}</Link>
                </div>
              </form>
            )}
          </div>
        )}
      </section>
    </>
  );
}
