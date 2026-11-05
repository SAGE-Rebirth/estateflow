export type Role = "owner" | "admin" | "agent";
export type LeadStage =
  | "new" | "contacted" | "qualified" | "visit_scheduled" | "negotiation" | "won" | "lost";
export type PropertyType =
  | "apartment" | "villa" | "independent_house" | "plot" | "commercial" | "office";
export type ListingType = "sale" | "rent";
export type PropertyStatus = "draft" | "available" | "under_offer" | "sold" | "rented";
export type AppointmentKind = "site_visit" | "call" | "office_meeting" | "video_call";
export type AppointmentStatus = "scheduled" | "confirmed" | "completed" | "cancelled" | "no_show";

export interface User {
  id: string; email: string; full_name: string; phone: string | null; role: Role;
  is_active: boolean;
}
export interface Tenant {
  id: string; name: string; slug: string; timezone: string; currency: string;
  contact_email: string | null; whatsapp_phone_number_id: string | null;
  whatsapp_display_number: string | null; bot_settings: Record<string, unknown>;
  list_on_marketplace: boolean;
}
export interface Me { user: User; tenant: Tenant }

export interface Media { id: string; url: string; kind: "image" | "video" | "floorplan"; sort_order: number }
export interface Property {
  id: string; ref_code: string; title: string; description: string;
  listing_type: ListingType; property_type: PropertyType; status: PropertyStatus;
  price: number | null; area_sqft: number | null; bedrooms: number | null;
  bathrooms: number | null; city: string | null; locality: string | null;
  address: string | null; amenities: string[]; published: boolean;
  assigned_to: string | null; media: Media[]; created_at: string; updated_at: string;
}
export interface KnowledgeDoc {
  id: string; property_id: string | null; filename: string;
  status: "pending" | "processing" | "ready" | "failed"; error: string | null;
  chunk_count: number; created_at: string;
}
export interface Contact {
  id: string; phone: string; name: string | null; email: string | null;
  source: string; stage: LeadStage; budget_min: number | null; budget_max: number | null;
  preferred_locations: string[]; preferred_property_type: PropertyType | null;
  bedrooms: number | null; notes: string | null; tags: string[];
  assigned_to: string | null; last_inbound_at: string | null; created_at: string;
}
export interface Activity {
  id: string; kind: string; summary: string; user_id: string | null;
  meta: Record<string, unknown>; created_at: string;
}
export interface Task {
  id: string; title: string; description: string | null; due_at: string;
  done_at: string | null; contact_id: string | null; assigned_to: string | null;
  created_at: string;
}
export interface Appointment {
  id: string; contact_id: string; property_id: string | null; user_id: string;
  kind: AppointmentKind; status: AppointmentStatus; starts_at: string; ends_at: string;
  location: string | null; notes: string | null; outcome: string | null;
  created_by_bot: boolean; created_at: string;
  contact_name: string | null; contact_phone: string; property_ref: string | null;
  property_title: string | null; agent_name: string;
}
export interface ConversationItem {
  id: string; contact_id: string; mode: "bot" | "human"; status: "open" | "closed";
  unread_count: number; last_message_at: string | null; focus_property_id: string | null;
  contact_name: string | null; contact_phone: string; last_message: string | null;
}
export interface ChatMessage {
  id: string; direction: "inbound" | "outbound"; sender_type: "contact" | "bot" | "user" | "system";
  sender_user_id: string | null; body: string; status: string; error: string | null;
  media_kind: "image" | "audio" | "document" | "video" | "sticker" | null; created_at: string;
}
export interface Notification {
  id: string; kind: string; title: string; body: string | null; link: string | null;
  read_at: string | null; created_at: string;
}
export interface Today {
  date: string; timezone: string;
  appointments_today: Appointment[]; appointments_upcoming: Appointment[];
  tasks_overdue: Task[]; tasks_due_today: Task[]; new_leads: Contact[];
  conversations_needing_human: number; unread_conversations: number;
  awaiting_outcome: Appointment[];
}
export interface Stats {
  pipeline: Record<LeadStage, number>; leads_last_30_days: number;
  visits_last_30_days: number; won_last_30_days: number; active_listings: number;
}
export interface Slot { starts_at: string; ends_at: string; user_id: string | null }
export interface AvailabilityRule {
  id?: string; weekday: number; start_time: string; end_time: string; slot_minutes: number;
}
export interface Page<T> { items: T[]; total: number }
