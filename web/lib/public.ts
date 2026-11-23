/**
 * Frontend (web) · Task 25 · public.ts - what the public map and alert pages receive,
 * plus one colour per theft type (the same colours on the map, the legend and the lists).
 */
import type { Area } from "@/lib/areas";

export type Incident = {
  id: string;
  theft_type: string;
  theft_name_en: string;
  theft_name_bn: string;
  lat: number;
  lng: number;
  occurred_hour: string;
  thana: Area | null;
  ward: Area | null;
  is_demo: boolean; // Task 32: demo data, shown with a "Demo" label
};

export type Incidents = {
  days: number;
  total: number;
  points: Incident[];
  area_counts: { thana: Area; count: number; lat: number; lng: number }[]; // house burglaries, per thana only
  by_type: { code: string; name_en: string; name_bn: string; count: number }[];
};

export type PublicAlert = {
  id: string;
  text_en: string;
  text_bn: string;
  theft_type: string;
  theft_name_en: string;
  theft_name_bn: string;
  thana: Area | null;
  ward: Area | null;
  sent_at: string;
  radius_m: number;
  point: { lat: number; lng: number } | null; // moved 100-200 m; none for house burglaries
  phones: number;
  is_demo: boolean; // Task 32: demo data, shown with a "Demo" label
};

export const THEFT_COLOURS: Record<string, string> = {
  phone_snatching: "#e11d48",
  bag_snatching: "#f97316",
  pickpocket: "#a855f7",
  motorbike_theft: "#2563eb",
  bicycle_theft: "#0d9488",
  car_theft: "#0f172a",
  cng_theft: "#16a34a",
  burglary: "#b45309",
  shop_theft: "#db2777",
  other: "#64748b",
};
