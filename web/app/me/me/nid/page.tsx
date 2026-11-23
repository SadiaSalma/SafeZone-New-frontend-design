"use client";
/**
 * Frontend (web) · Task 10 · /me/nid - add your NID number (needed before the first report).
 * Only for logged-in people: others are sent to /login.
 * The backend checks the format and stores the NID scrambled; only the last 4 digits are shown.
 * Buttons follow the phone reference: dark pill (main) + white pill (secondary).
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { BadgeCheck, IdCard } from "lucide-react";
import trafficPolice from "@/public/images/auth-nid-traffic-police.jpg";
import { AuthShell } from "@/components/auth/AuthShell";
import { Field, FormError, PrimaryButton } from "@/components/auth/FormParts";
import { useAuth, type User } from "@/components/AuthProvider";
import { usePrefs } from "@/components/PreferencesProvider";
import { api, ApiError } from "@/lib/api";

export default function NidPage() {
  const { t } = usePrefs();
  const { user, loading, setUser } = useAuth();
  const router = useRouter();
  const [nid, setNid] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  // Not logged in? Go to the log-in page.
  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setUser(await api<User>("/me/nid", { method: "POST", body: { nid } }));
    } catch (problem) {
      setError(problem as ApiError);
    } finally {
      setBusy(false);
    }
  }

  const shell = {
    photo: trafficPolice,
    photoAlt: "A traffic police officer on a Dhaka street at night",
    sideTitle: t("nid_side_title"),
    sideText: t("nid_side_text"),
  };
  const whitePill = "mt-3 flex w-full justify-center rounded-full bg-white px-6 py-3.5 text-sm font-semibold text-neutral-900 transition hover:bg-white/90";

  if (!user) return <AuthShell {...shell} title={t("nid_title")}><p className="text-white/75">{t("working")}</p></AuthShell>;

  // Already added: show a small "done" card
  if (user.nid_added) {
    return (
      <AuthShell {...shell} title={t("nid_done")}>
        <div className="mb-8 flex items-center gap-3 rounded-2xl border border-white/25 bg-white/10 px-4 py-4 backdrop-blur-md">
          <BadgeCheck size={28} className="text-accent" aria-hidden />
          <span>{t("nid_saved_as")} <strong className="font-mono">*******{user.nid_last4}</strong></span>
        </div>
        <Link href="/" className={whitePill}>{t("go_home")}</Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell {...shell} title={t("nid_title")} subtitle={t("nid_sub")}>
      <form onSubmit={submit} noValidate>
        <FormError>{error && !error.fields?.nid ? error.message : null}</FormError>
        <Field label={t("field_nid")} name="nid" inputMode="numeric" placeholder="1234567890" hint={t("nid_hint")}
               icon={<IdCard size={18} />} value={nid} onChange={(e) => setNid(e.target.value)} error={error?.fields?.nid} />
        <div className="mt-10">
          <PrimaryButton busy={busy}>{t("nid_button")}</PrimaryButton>
          <Link href="/" className={whitePill}>{t("later")}</Link>
        </div>
      </form>
    </AuthShell>
  );
}
