import type { AppointmentKind, LeadStage, PropertyType } from "./types";

/** ₹95 L, ₹3.2 Cr, ₹28,000 — how Indian buyers actually read prices. */
export function price(value: string | number | null | undefined, currency = "INR"): string {
  if (value === null || value === undefined || value === "") return "Price on request";
  const n = Number(value);
  if (currency !== "INR") {
    return new Intl.NumberFormat("en", { style: "currency", currency, maximumFractionDigits: 0 })
      .format(n);
  }
  const trim = (x: number) => (Math.round(x * 100) / 100).toString();
  if (n >= 1e7) return `₹${trim(n / 1e7)} Cr`;
  if (n >= 1e5) return `₹${trim(n / 1e5)} L`;
  return `₹${n.toLocaleString("en-IN")}`;
}

export function time(iso: string, tz?: string) {
  return new Date(iso).toLocaleTimeString("en-IN", {
    hour: "numeric", minute: "2-digit", timeZone: tz,
  });
}

export function day(iso: string, tz?: string) {
  return new Date(iso).toLocaleDateString("en-IN", {
    weekday: "short", day: "numeric", month: "short", timeZone: tz,
  });
}

export function dateTime(iso: string, tz?: string) {
  return `${day(iso, tz)}, ${time(iso, tz)}`;
}

export function ago(iso: string | null): string {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export const STAGES: { value: LeadStage; label: string }[] = [
  { value: "new", label: "New" },
  { value: "contacted", label: "Contacted" },
  { value: "qualified", label: "Qualified" },
  { value: "visit_scheduled", label: "Visit scheduled" },
  { value: "negotiation", label: "Negotiation" },
  { value: "won", label: "Won" },
  { value: "lost", label: "Lost" },
];
export const stageLabel = (s: LeadStage) => STAGES.find((x) => x.value === s)?.label ?? s;

export const KIND_LABEL: Record<AppointmentKind, string> = {
  site_visit: "Site visit",
  call: "Call",
  office_meeting: "Office meeting",
  video_call: "Video call",
};

export const PROPERTY_TYPES: { value: PropertyType; label: string }[] = [
  { value: "apartment", label: "Apartment" },
  { value: "villa", label: "Villa" },
  { value: "independent_house", label: "Independent house" },
  { value: "plot", label: "Plot" },
  { value: "commercial", label: "Commercial" },
  { value: "office", label: "Office" },
];
export const typeLabel = (t: PropertyType) =>
  PROPERTY_TYPES.find((x) => x.value === t)?.label ?? t;

export function waLink(phone: string, text?: string) {
  const digits = phone.replace(/\D/g, "");
  return `https://wa.me/${digits}${text ? `?text=${encodeURIComponent(text)}` : ""}`;
}
