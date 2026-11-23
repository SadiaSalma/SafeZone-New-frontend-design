/**
 * Frontend (web) · Task 14 · reports.ts - what a theft report looks like on the website,
 * plus the words and colours for each report status.
 *
 * Statuses (Design Revisions R7 - there is no "SUBMITTED"):
 *   PENDING_REVIEW -> a verifier will look at it
 *   NEEDS_INFO     -> the verifier asked the victim for more information
 *   VERIFIED       -> approved; the alert is being sent
 *   ALERTED        -> people nearby were warned
 *   ALERT_FAILED   -> approved, but sending the alert is being retried
 *   REJECTED / WITHDRAWN -> closed (the GD is free again)
 */
import type { Area } from "@/lib/areas";
import type { TextKey } from "@/lib/i18n";

export type ReportStatus =
  | "PENDING_REVIEW" | "NEEDS_INFO" | "VERIFIED" | "ALERTED" | "ALERT_FAILED" | "REJECTED" | "WITHDRAWN";

export type ReportPhoto = { id: string; kind: "item" | "gd_copy"; url: string; width: number; height: number };

export type Named = { code: string; name_en: string; name_bn: string };

export type Report = {
  id: string;
  status: ReportStatus;
  theft_type: string;
  theft_name_en: string;
  theft_name_bn: string;
  occurred_at: string;
  submitted_at: string;
  lat: number;
  lng: number;
  thana: Area | null;
  ward: Area | null;
  landmark: string;
  description: string;
  stolen_items: string;
  gd: { type: "GD" | "FIR"; number: string; date: string; police_station: Named | null };
  info_request: string | null;
  info_answer?: string | null; // Task 19
  needs_info_until?: string | null;
  reject_reason?: string | null;
  can_withdraw: boolean;
  photos: ReportPhoto[]; // Task 16
  alert?: { status: string; phones: number; sent_at: string | null } | null; // Task 22
};

export type ReportOptions = {
  theft_types: Named[];
  gd_types: Named[];
  police_stations: Named[];
  gd_examples: string[];
  limits: { max_age_days: number; per_day: number; landmark: number; description: number; stolen_items: number };
};

/** The label and the pill colours for each status. */
export const STATUS_LOOK: Record<ReportStatus, { label: TextKey; pill: string; step: number }> = {
  PENDING_REVIEW: { label: "status_pending", pill: "bg-amber-100 text-amber-900", step: 1 },
  NEEDS_INFO: { label: "status_needs_info", pill: "bg-sky-100 text-sky-900", step: 1 },
  VERIFIED: { label: "status_verified", pill: "bg-emerald-100 text-emerald-900", step: 2 },
  ALERT_FAILED: { label: "status_alert_failed", pill: "bg-orange-100 text-orange-900", step: 2 },
  ALERTED: { label: "status_alerted", pill: "bg-emerald-600 text-white", step: 3 },
  REJECTED: { label: "status_rejected", pill: "bg-red-100 text-red-900", step: -1 },
  WITHDRAWN: { label: "status_withdrawn", pill: "bg-neutral-200 text-neutral-700", step: -1 },
};

/** "20 Nov 2026, 9:30 pm" in Dhaka time, in English or Bangla. */
export function dhakaTime(iso: string, lang: "en" | "bn", withTime = true) {
  return new Intl.DateTimeFormat(lang === "bn" ? "bn-BD" : "en-GB", {
    timeZone: "Asia/Dhaka", day: "numeric", month: "short", year: "numeric",
    ...(withTime ? { hour: "numeric", minute: "2-digit" } : {}),
  }).format(new Date(iso));
}
