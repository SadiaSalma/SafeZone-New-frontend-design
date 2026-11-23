"use client";
/**
 * Frontend (web) · Task 23 · FollowArea.tsx - "Get alerts for this area" (FR-18).
 *
 * A bell button for the chosen thana/ward. The first time, the browser asks
 * "Allow notifications?". After that, every SafeZone alert for the area appears as a
 * notification, even when the website is closed. Below it: the areas this browser follows.
 *
 * Right after following a new area, the area's LATEST REAL alert arrives 5 seconds later (the server sends it,
 * e.g. "Phone snatching · Tejgaon" with its real date): a countdown shows under the button, then the pop-up
 * and the full-screen red alarm appear. An area without a recent alert gets an "alerts are on" note.
 *
 * When notifications can't work, it says why instead (R4):
 *   - blocked in the browser settings
 *   - an iPhone: add SafeZone to the Home Screen first
 *   - an old browser: check the Alerts page instead
 */
import Link from "next/link";
import { useEffect, useState } from "react";
import { BellOff, BellRing, LoaderCircle, X } from "lucide-react";
import { useAlarm } from "@/components/alerts/AlarmProvider";
import { usePrefs } from "@/components/PreferencesProvider";
import { areaName, type Area } from "@/lib/areas";
import { currentFollow, follow, pushSupport, stopAll, type FirstAlert, type Support } from "@/lib/push";

export function FollowArea({ area }: { area: Area }) {
  const { t, lang } = usePrefs();
  const showAlarm = useAlarm();
  const [support, setSupport] = useState<Support | null>(null);
  const [followed, setFollowed] = useState<Area[]>([]);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const [countdown, setCountdown] = useState<number | null>(null); // seconds until the first alert
  const [firstAlert, setFirstAlert] = useState<FirstAlert | null>(null); // what that alert says

  // Count down once a second until the first alert arrives
  useEffect(() => {
    if (countdown === null) return;
    const timer = setTimeout(() => setCountdown(countdown > 0 ? countdown - 1 : null), countdown > 0 ? 1000 : 6000);
    return () => clearTimeout(timer);
  }, [countdown]);

  // When the countdown ends, make sure the full-screen alarm appears - even if this browser still runs an
  // older service worker that doesn't pass the pushed alert on to the page (the pop-up comes from the push itself).
  // Same key as the pushed one, so it is never shown twice.
  useEffect(() => {
    if (countdown !== 0 || !firstAlert) return;
    const timer = setTimeout(() => showAlarm({ ...firstAlert, key: firstAlert.url }), 2000);
    return () => clearTimeout(timer);
  }, [countdown, firstAlert, showAlarm]);

  // What this browser can do, and what it already follows (asked once, after the page has started)
  useEffect(() => {
    let current = true;
    Promise.resolve(pushSupport()).then((s) => {
      if (!current) return;
      setSupport(s);
      if (s === "ok") currentFollow().then((f) => current && setFollowed(f.areas)).catch(() => {});
    });
    return () => { current = false; };
  }, []);

  const following = followed.some((a) => a.code === area.code);

  async function change(codes: string[]) {
    setBusy(true);
    setProblem("");
    try {
      if (codes.length === 0) {
        await stopAll();
        setFollowed([]);
      } else {
        const result = await follow(codes, lang);
        setFollowed(result.areas);
        setFirstAlert(result.firstAlert);
        setCountdown(result.testIn); // null when no first alert is coming
      }
    } catch (e) {
      const why = (e as Error).message;
      if (why === "denied") setSupport("denied");
      else if (why === "off") setSupport("off");
      else setProblem(t("follow_failed"));
    } finally {
      setBusy(false);
    }
  }

  if (support === null) return null;
  if (support !== "ok") {
    const message = { unsupported: "follow_unsupported", ios_home_screen: "follow_ios", denied: "follow_denied", off: "follow_off" } as const;
    return (
      <div className="mt-5">
        <p className="flex items-start gap-2 rounded-2xl bg-bg-soft p-3 text-xs text-ink-soft">
          <BellOff size={16} className="mt-0.5 shrink-0" aria-hidden />
          <span>{t(message[support])} <Link href="/alerts" className="text-primary underline">{t("follow_see_alerts")}</Link></span>
        </p>
      </div>
    );
  }

  return (
    <div className="mt-5">
      <button onClick={() => change(following ? followed.filter((a) => a.code !== area.code).map((a) => a.code) : [...followed.map((a) => a.code), area.code])}
              disabled={busy}
              className={`inline-flex w-full items-center justify-center gap-2 rounded-full px-5 py-3 text-sm font-semibold transition disabled:opacity-60 ${
                following ? "border border-primary text-primary hover:bg-bg-soft" : "bg-primary text-on-primary shadow-lg hover:scale-[1.02]"}`}>
        {busy ? <LoaderCircle size={17} className="animate-spin" aria-hidden /> : following ? <BellOff size={17} aria-hidden /> : <BellRing size={17} aria-hidden />}
        {following ? t("follow_stop") : t("follow_start").replace("{area}", areaName(area, lang))}
      </button>
      {problem && <p role="alert" className="mt-2 text-xs text-red-700">{problem}</p>}
      {countdown !== null && (
        <p role="status" className="mt-2 flex items-center justify-center gap-2 rounded-2xl bg-red-50 px-3 py-2 text-sm font-medium text-red-800">
          <BellRing size={16} className="animate-bounce" aria-hidden />
          {countdown > 0 ? t("follow_test_in").replace("{n}", String(countdown)) : t("follow_test_now")}
        </p>
      )}
      {followed.length > 0 && (
        <div className="mt-3">
          <p className="mb-1.5 text-xs text-ink-soft">{t("follow_list")}</p>
          <div className="flex flex-wrap gap-1.5">
            {followed.map((a) => (
              <span key={a.code} className="inline-flex items-center gap-1 rounded-full bg-primary/15 py-1 pr-1 pl-3 text-xs text-ink">
                {areaName(a, lang)}
                <button onClick={() => change(followed.filter((x) => x.code !== a.code).map((x) => x.code))} disabled={busy}
                        aria-label={`${t("follow_remove")} ${areaName(a, lang)}`}
                        className="grid size-5 place-items-center rounded-full hover:bg-primary/25"><X size={12} /></button>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
