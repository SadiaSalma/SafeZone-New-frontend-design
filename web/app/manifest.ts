/**
 * Frontend (web) · Task 23 · manifest.ts - SafeZone as an installable app (a "PWA").
 *
 * Phones read this to "Add to Home Screen": the name, the icon and the colours.
 * On iPhones this matters for notifications: Apple allows web push only for sites
 * added to the Home Screen (Design Revisions R4).
 * See node_modules/next/dist/docs/.../metadata/manifest.md
 */
import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "SafeZone · Verified theft alerts for Dhaka",
    short_name: "SafeZone",
    description: "Verified theft alerts, crime statistics and area safety for Dhaka.",
    start_url: "/",
    display: "standalone",
    background_color: "#f4f7f4",
    theme_color: "#5c8065",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/maskable-192.png", sizes: "192x192", type: "image/png", purpose: "maskable" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
