/**
 * Frontend (web) · Task 23 · push.ts - turning SafeZone notifications on and off in this browser.
 *
 *  pushSupport()      can this browser get notifications at all? (iPhone: only from the Home Screen app)
 *  currentFollow()    which areas this browser already follows
 *  follow(codes, lang) ask permission (first time), subscribe, and tell the backend the areas
 *  stopAll()          unsubscribe this browser completely
 *
 * The backend part is in api/app/modules/push (Task 23).
 */
import { api } from "@/lib/api";
import type { Area } from "@/lib/areas";

export type Support = "ok" | "unsupported" | "ios_home_screen" | "denied" | "off";
/** The alert a browser gets right after following an area (the area's latest real alert). */
export type FirstAlert = { title: string; body: string; url: string; test: boolean };

/** The server's public key in the form the browser wants (bytes, not text). */
function keyBytes(base64: string): Uint8Array<ArrayBuffer> {
  const padded = (base64 + "=".repeat((4 - (base64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

export function pushSupport(): Support {
  if (typeof window === "undefined") return "unsupported";
  const iPhone = /iPhone|iPad|iPod/.test(navigator.userAgent);
  const fromHomeScreen = window.matchMedia("(display-mode: standalone)").matches;
  if (iPhone && !fromHomeScreen) return "ios_home_screen"; // R4: iPhones allow push only for Home Screen apps
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) return "unsupported";
  if (Notification.permission === "denied") return "denied";
  return "ok";
}

async function registration() {
  return navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" });
}

export async function currentFollow(): Promise<{ endpoint: string | null; areas: Area[] }> {
  if (pushSupport() !== "ok") return { endpoint: null, areas: [] };
  const sub = await (await registration()).pushManager.getSubscription();
  if (!sub) return { endpoint: null, areas: [] };
  const answer = await api<{ subscribed: boolean; areas: Area[] }>("/push/status", { method: "POST", body: { endpoint: sub.endpoint } });
  return { endpoint: sub.endpoint, areas: answer.areas };
}

/** Follow exactly these areas (an empty list keeps only "news about my own reports").
 * testIn: after following a NEW area, the server sends its latest alert in this many seconds (null = none),
 * firstAlert: what that alert says (the page shows it too, in case the push is slow). */
export async function follow(codes: string[], lang: "en" | "bn"):
  Promise<{ areas: Area[]; testIn: number | null; firstAlert: FirstAlert | null }> {
  const key = await api<{ enabled: boolean; public_key: string | null }>("/push/key");
  if (!key.enabled || !key.public_key) throw new Error("off");
  if (Notification.permission !== "granted" && (await Notification.requestPermission()) !== "granted") {
    throw new Error("denied");
  }
  const reg = await registration();
  await navigator.serviceWorker.ready;
  const sub = (await reg.pushManager.getSubscription())
    ?? (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key.public_key) }));
  const json = sub.toJSON() as { endpoint: string; keys: { p256dh: string; auth: string } };
  const answer = await api<{ areas: Area[]; test_alert_in: number | null; first_alert: FirstAlert | null }>("/push/subscribe", {
    method: "POST", body: { endpoint: json.endpoint, keys: json.keys, areas: codes, lang },
  });
  return { areas: answer.areas, testIn: answer.test_alert_in ?? null, firstAlert: answer.first_alert ?? null };
}

export async function stopAll(): Promise<void> {
  const sub = await (await registration()).pushManager.getSubscription();
  if (!sub) return;
  await api("/push/unsubscribe", { method: "POST", body: { endpoint: sub.endpoint } }).catch(() => {});
  await sub.unsubscribe();
}
