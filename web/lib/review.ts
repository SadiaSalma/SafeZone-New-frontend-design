/**
 * Frontend (web) · Task 18 · review.ts - what the verifier pages receive from the backend.
 */
import type { Area } from "@/lib/areas";
import type { ReportPhoto, ReportStatus } from "@/lib/reports";

export type CheckResult = "pass" | "warning" | "fail";

export type Check = { code: string; result: CheckResult; message: string; message_bn: string };

export type RiskReason = { code: string; text: string; text_bn: string; points: number };

export type Risk = { score: number; level: "low" | "medium" | "high"; reasons?: RiskReason[] };

export type Claim = { mine: boolean; by_name: string; until: string } | null;

export type QueueCard = {
  id: string;
  status: ReportStatus;
  theft_type: string;
  theft_name_en: string;
  theft_name_bn: string;
  thana: Area | null;
  ward: Area | null;
  occurred_at: string;
  submitted_at: string;
  risk: Risk;
  has_failed_check: boolean;
  photos: number;
  claim: Claim;
};

export type ReviewDetail = Omit<QueueCard, "photos" | "has_failed_check"> & {
  lat: number;
  lng: number;
  landmark: string;
  description: string;
  stolen_items: string;
  gd: {
    type: "GD" | "FIR";
    number: string;
    date: string;
    police_station: { code: string; name_en: string; name_bn: string; lat: number; lng: number } | null;
  };
  checks: Check[];
  photos: ReportPhoto[];
  reporter: {
    account_days: number;
    nid_added: boolean;
    nid_last4: string | null;
    other_reports: number;
    verified_reports: number;
    rejected_reports: number;
  } | null;
  info_request: string | null;
  info_answer?: string | null;
  decisions: { decision: string; reason: string; created_at: string }[];
  timeline: { action: string; text: string; role: string; created_at: string }[]; // Task 19
  reject_reasons: { code: string; text: string }[]; // Task 19
  // Task 29: what OCR read from the GD photo, next to the form (null = no photo was read)
  ocr: {
    status: "processing" | "done" | "failed" | "deleted";
    seconds?: number;
    compare: {
      field: string; ocr: string; form: string | null; confidence: number; same: boolean;
      ocr_text: { en: string; bn: string }; form_text: { en: string | null; bn: string | null }; // names, not codes
    }[];
  } | null;
};

/** Colours for each risk level (used by the meter and the queue cards). */
export const RISK_COLOURS = {
  low: { bar: "#10b981", pill: "bg-emerald-100 text-emerald-900" },
  medium: { bar: "#f59e0b", pill: "bg-amber-100 text-amber-900" },
  high: { bar: "#ef4444", pill: "bg-red-100 text-red-900" },
} as const;

/** "5 min ago", "3 h ago", "2 days ago" */
export function ago(iso: string, lang: "en" | "bn") {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  const rtf = new Intl.RelativeTimeFormat(lang === "bn" ? "bn-BD" : "en", { numeric: "auto" });
  if (minutes < 60) return rtf.format(-minutes, "minute");
  if (minutes < 60 * 48) return rtf.format(-Math.round(minutes / 60), "hour");
  return rtf.format(-Math.round(minutes / 1440), "day");
}
