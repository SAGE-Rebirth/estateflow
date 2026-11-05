import { notFound } from "next/navigation";
import type { ListingType, PropertyStatus, PropertyType } from "./types";

const BASE =
  process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export interface MarketListing {
  id: string;
  slug: string;
  ref_code: string;
  title: string;
  listing_type: ListingType;
  property_type: PropertyType;
  status: PropertyStatus;
  price: number | null;
  price_per_sqft: number | null;
  area_sqft: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  locality: string | null;
  city: string | null;
  amenities: string[];
  photo: string | null;
  photo_count: number;
  seller_name: string;
  whatsapp_url: string | null;
  listed_at: string;
}

export interface MarketListingDetail extends MarketListing {
  description: string;
  photos: string[];
  floorplans: string[];
  latitude: number | null;
  longitude: number | null;
  seller: { name: string; slug: string; whatsapp_number: string | null };
  similar: MarketListing[];
}

export interface Count {
  value: string;
  count: number;
}

export interface MarketSummary {
  total: number;
  for_sale: number;
  for_rent: number;
  cities: Count[];
  localities: Count[];
  property_types: Count[];
}

export interface ListingPage {
  items: MarketListing[];
  total: number;
  limit: number;
  offset: number;
}

async function get<T>(path: string, revalidate = 30): Promise<T> {
  const res = await fetch(`${BASE}/market${path}`, { next: { revalidate } });
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error(`Couldn't load ${path} (${res.status})`);
  return res.json();
}

export const market = {
  summary: () => get<MarketSummary>("/summary", 60),
  listings: (params: URLSearchParams) => get<ListingPage>(`/listings?${params}`),
  listing: (slug: string, ref: string) =>
    get<MarketListingDetail>(`/listings/${encodeURIComponent(slug)}/${encodeURIComponent(ref)}`),
};

export const listingHref = (l: { slug: string; ref_code: string }) =>
  `/properties/${l.slug}/${l.ref_code}`;

/** Search params accepted by /properties, in the order the API expects them. */
export const FILTER_KEYS = [
  "q", "city", "locality", "listing_type", "property_type", "bedrooms",
  "min_price", "max_price", "sort",
] as const;

export const SALE_BUDGETS = [2_500_000, 5_000_000, 7_500_000, 10_000_000, 20_000_000, 50_000_000];
export const RENT_BUDGETS = [10_000, 20_000, 30_000, 50_000, 100_000];
