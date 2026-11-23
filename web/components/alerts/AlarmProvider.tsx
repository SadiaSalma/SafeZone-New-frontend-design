"use client";
/**
 * Frontend (web) · AlarmProvider.tsx - the FULL-SCREEN alert: red light, siren and vibration.
 *
 * When does it appear?
 *   1. A SafeZone alert arrives by push while a SafeZone tab is open: the service worker (public/sw.js)
 *      passes it to the page, and the alarm covers the whole page.
 *   2. The person clicks the Windows/Android notification: the alert page opens with "?alarm=1"
 *      and the alarm shows there.
 *   3. "Try the alarm" (on the follow card) shows a harmless test alarm.
 *   4. The TEST alert a few seconds after following an area. The page also shows it by itself when the
 *      countdown ends, in case the browser still runs an older service worker that doesn't pass alerts on.
 *      The same alarm (same `key`) is shown only once, so the two ways never ring twice.
 *
 * A web page can't cover the screen while the browser is closed or minimised - then the system
 * notification (which stays until dismissed) does that job.
 *
 * Safety and comfort:
 *   - the red light pulses once per second (far below the 3 flashes/second that can trigger seizures),
 *     and stays steady for people who chose "reduce motion" on their device
 *   - the siren lasts 8 seconds, can be muted (remembered), and stops on Dismiss
 *   - Escape closes it; the Dismiss button gets the keyboard focus; screen readers announce it
 */
import Link from "next/link";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowRight, Siren, Volume2, VolumeX } from "lucide-react";
import { usePrefs } from "@/components/PreferencesProvider";
import { api } from "@/lib/api";
import { setSoundWanted, soundBlocked, soundWanted, startSiren, unlockSound } from "@/lib/alarm";

export type Alarm = { title: string; body: string; url: string; test?: boolean; key?: string };

const AlarmContext = createContext<(alarm: Alarm) => void>(() => {});

/** Show the full-screen alarm from anywhere (e.g. "Try the alarm"). */
export function useAlarm() {
  return useContext(AlarmContext);
}

type PublicAlert = { text_en: string; text_bn: string; theft_name_en: string; theft_name_bn: string;
  thana: { name_en: string; name_bn: string } | null };

/** The alarm for one real alert: the title says WHAT and WHERE ("Phone snatching · Tejgaon"). */
async function alarmFor(id: string, lang: "en" | "bn"): Promise<Alarm> {
  const a = await api<PublicAlert>(`/public/alerts/${id}`);
  const what = lang === "bn" ? a.theft_name_bn : a.theft_name_en;
  const where = a.thana ? (lang === "bn" ? a.thana.name_bn || a.thana.name_en : a.thana.name_en) : "";
  return { title: where ? `${what} · ${where}` : what, body: lang === "bn" ? a.text_bn : a.text_en, url: `/alerts/${id}` };
}

export function AlarmProvider({ children }: { children: ReactNode }) {
  const { lang } = usePrefs();
  const [alarm, setAlarm] = useState<Alarm | null>(null);
  const shown = useRef(new Map<string, number>()); // alarm key -> when it was shown

  // Show an alarm; one with a key is shown at most once in 30 seconds (see 4. above)
  const show = useCallback((next: Alarm) => {
    if (next.key) {
      const at = shown.current.get(next.key);
      if (at && Date.now() - at < 30_000) return;
      shown.current.set(next.key, Date.now());
    }
    setAlarm(next);
  }, []);

  // Sound needs one click on the page first (browser rule): get it ready on the first click anywhere
  useEffect(() => {
    const unlock = () => unlockSound();
    window.addEventListener("pointerdown", unlock, { once: true });
    window.addEventListener("keydown", unlock, { once: true });
    return () => { window.removeEventListener("pointerdown", unlock); window.removeEventListener("keydown", unlock); };
  }, []);

  // 1. An alert pushed while this page is open (sent on by the service worker)
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    const onMessage = (event: MessageEvent) => {
      const data = event.data;
      if (data?.type !== "safezone-alert") return;
      const test = data.test === true;
      show({ title: data.title, body: data.body, url: data.url, test, key: data.url }); // show it at once...
      const id = String(data.url).match(/^\/alerts\/([a-f0-9]{24})/)?.[1];
      // ...then name what and where in the title. The text stays as it was pushed: the server writes it
      // fresh (an older alert's own text may say "today" about a day that has passed)
      if (id) alarmFor(id, lang).then((a) => setAlarm((now) => (now?.url === a.url ? { ...now, title: a.title } : now))).catch(() => {});
    };
    navigator.serviceWorker.addEventListener("message", onMessage);
    navigator.serviceWorker.startMessages();
    return () => navigator.serviceWorker.removeEventListener("message", onMessage);
  }, [lang, show]);

  // 2. Opened from the notification: /alerts/<id>?alarm=1
  useEffect(() => {
    const url = new URL(window.location.href);
    if (url.searchParams.get("alarm") !== "1") return;
    url.searchParams.delete("alarm");
    window.history.replaceState(null, "", url.pathname + url.search); // a reload won't ring again
    const id = url.pathname.match(/^\/alerts\/([a-f0-9]{24})$/)?.[1];
    if (!id) return;
    alarmFor(id, lang).then(setAlarm).catch(() => {});
  }, [lang]);

  return (
    <AlarmContext.Provider value={show}>
      {children}
      {alarm && <AlarmOverlay alarm={alarm} onClose={() => setAlarm(null)} />}
    </AlarmContext.Provider>
  );
}

function AlarmOverlay({ alarm, onClose }: { alarm: Alarm; onClose: () => void }) {
  const { t } = usePrefs();
  const [sound, setSound] = useState(soundWanted);
  const [blocked, setBlocked] = useState(false);
  const stop = useRef<() => void>(() => {});
  const dismiss = useRef<HTMLButtonElement>(null);

  const ring = useCallback(() => {
    stop.current();
    unlockSound();
    stop.current = startSiren();
    window.setTimeout(() => setBlocked(soundBlocked()), 150);
  }, []);

  useEffect(() => {
    dismiss.current?.focus();
    if ("vibrate" in navigator) navigator.vibrate([400, 200, 400, 200, 800]); // phones only
    if (sound) ring();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); stop.current(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- ring once when the alarm opens
  }, []);

  // While the person is on ANOTHER tab or website, a web page can't cover their screen (browser security rule).
  // So the SafeZone tab draws attention instead: its title flashes "🚨 SAFEZONE ALERT" in the tab bar
  // (the siren also plays from this tab), and the alarm is already waiting full screen when they come back.
  useEffect(() => {
    const original = document.title;
    let flash = false;
    const timer = window.setInterval(() => {
      flash = document.hidden ? !flash : false;
      document.title = flash ? `🚨 ${t("alarm_tab_title")}` : original;
    }, 1000);
    return () => { window.clearInterval(timer); document.title = original; };
  }, [t]);

  function toggleSound() {
    const next = !sound;
    setSound(next);
    setSoundWanted(next);
    if (next) ring();
    else stop.current();
  }

  return (
    <div role="alertdialog" aria-modal="true" aria-labelledby="sz-alarm-title" aria-describedby="sz-alarm-body"
         className="sz-alarm fixed inset-0 z-[100] flex flex-col items-center justify-center overflow-y-auto px-6 py-10 text-center text-white">
      <div className="sz-alarm-glow pointer-events-none absolute inset-0" aria-hidden />

      <button onClick={toggleSound} aria-pressed={sound}
              className="absolute top-5 right-5 inline-flex items-center gap-2 rounded-full bg-white/15 px-4 py-2 text-sm font-medium backdrop-blur-md hover:bg-white/25">
        {sound ? <Volume2 size={18} aria-hidden /> : <VolumeX size={18} aria-hidden />}
        {sound ? t("alarm_sound_on") : t("alarm_sound_off")}
      </button>

      <div className="relative mb-8 grid size-28 place-items-center">
        <span className="sz-alarm-ring absolute inset-0 rounded-full border-4 border-white/70" aria-hidden />
        <span className="grid size-24 place-items-center rounded-full bg-white text-red-700 shadow-2xl">
          <Siren size={52} aria-hidden />
        </span>
      </div>

      <p className="mb-2 text-sm font-semibold tracking-[0.3em] text-white/85 uppercase">
        {alarm.test ? t("alarm_test_label") : t("alarm_label")}
      </p>
      <h2 id="sz-alarm-title" className="max-w-3xl text-3xl font-bold md:text-5xl">{alarm.title}</h2>
      <p id="sz-alarm-body" className="mt-5 max-w-2xl text-lg leading-relaxed text-white/95 md:text-2xl">{alarm.body}</p>

      {sound && blocked && (
        <button onClick={ring} className="mt-6 inline-flex items-center gap-2 rounded-full bg-black/25 px-5 py-2.5 text-sm font-semibold hover:bg-black/35">
          <Volume2 size={17} aria-hidden /> {t("alarm_tap_sound")}
        </button>
      )}

      <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
        {!alarm.test && (
          <Link href={alarm.url} onClick={onClose}
                className="inline-flex items-center gap-2 rounded-full bg-white px-7 py-3.5 text-base font-bold text-red-700 shadow-xl hover:scale-[1.03]">
            {t("alarm_open")} <ArrowRight size={18} aria-hidden />
          </Link>
        )}
        <button ref={dismiss} onClick={onClose}
                className="rounded-full border-2 border-white/80 px-7 py-3 text-base font-semibold hover:bg-white/15">
          {t("alarm_dismiss")}
        </button>
      </div>
    </div>
  );
}
