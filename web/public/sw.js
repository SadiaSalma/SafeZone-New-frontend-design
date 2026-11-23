/*
 * Frontend (web) · Task 23 · sw.js - SafeZone's service worker.
 *
 * A service worker is a small script the browser keeps running in the background, even when
 * the SafeZone tab is closed. It does two jobs here:
 *   push              - a SafeZone alert arrived from the server -> show it as a notification
 *   notificationclick - the person tapped it -> open (or focus) the page the alert links to
 *
 * It must stay a plain file in /public, so the browser can load it from the site's root ("/sw.js").
 *
 * Alerts (tag "alert-..." ): the notification STAYS on screen until the person closes it, with the
 * system sound, and every open SafeZone tab is told to show the full-screen red alarm with a siren
 * (components/alerts/AlarmProvider.tsx). Clicking the notification opens the alert with "?alarm=1".
 */
self.addEventListener("push", (event) => {
  let data = { title: "SafeZone", body: "", url: "/", tag: "safezone" };
  try {
    data = { ...data, ...event.data.json() };
  } catch {
    data.body = event.data ? event.data.text() : "";
  }
  const isAlert = String(data.tag).startsWith("alert-") || data.alarm === true;
  event.waitUntil(Promise.all([
    self.registration.showNotification(isAlert ? `\u{1F6A8} ${data.title}` : data.title, {
      body: data.body,
      icon: "/icons/icon-192.png",
      badge: "/icons/badge-72.png",
      tag: data.tag, // a newer message with the same tag replaces the older one
      renotify: true,
      requireInteraction: isAlert, // alerts stay on screen until the person closes them
      silent: false, // with the system's notification sound
      vibrate: isAlert ? [400, 200, 400, 200, 800] : [120, 60, 120],
      data: { url: isAlert ? `${data.url}${data.url.includes("?") ? "&" : "?"}alarm=1` : data.url },
    }),
    // Open SafeZone tabs show the full-screen alarm right away
    isAlert
      ? self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) =>
          windows.forEach((w) => w.postMessage({ type: "safezone-alert", title: data.title, body: data.body, url: data.url,
                                                  test: data.test === true })))
      : null,
  ]));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      const open = windows.find((w) => w.url.startsWith(self.location.origin));
      if (open) {
        open.navigate(url);
        return open.focus();
      }
      return self.clients.openWindow(url);
    }),
  );
});

// A new version of this file takes over at once (instead of waiting until every SafeZone tab is closed),
// so improvements to alerts reach people straight away.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
