import { notFound } from "next/navigation";
import type { ListingType, Media, PropertyStatus, PropertyType } from "./types";

// Server-side fetches can use an internal URL (e.g. http://api:8000 in docker).
const BASE =
  process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export interface PublicTenant {
  name: string; slug: string; currency: string; timezone: string; whatsapp_number: string | null;
}
export interface PublicProperty {
  ref_code: string; title: string; description: string; listing_type: ListingType;
  property_type: PropertyType; status: PropertyStatus; price: string | null;
  area_sqft: string | null; bedrooms: number | null; bathrooms: number | null;
  city: string | null; locality: string | null; amenities: string[]; media: Media[];
  whatsapp_url: string | null;
}

export async function publicGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}/public${path}`, { next: { revalidate: 60 } });
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error(`Failed to load ${path}`);
  return res.json();
}
