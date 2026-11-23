/**
 * Frontend (web) · useHydrated.ts - "has this page finished starting up in the browser?"
 *
 * The server never knows who is logged in, so it draws the logged-out header. In the browser,
 * React must first draw EXACTLY the same thing (this is called hydration), and only then may it
 * show "Hi, Nila". useSyncExternalStore gives `false` during that first pass (like the server)
 * and `true` right after - so the two always match and React never complains.
 */
import { useSyncExternalStore } from "react";

const nothingToWatch = () => () => {};

export function useHydrated(): boolean {
  return useSyncExternalStore(nothingToWatch, () => true, () => false);
}
