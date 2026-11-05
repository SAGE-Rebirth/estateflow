import { Camera, MessageCircle } from "lucide-react";
import Link from "next/link";
import { price, typeLabel } from "@/lib/format";
import { listingHref, type MarketListing } from "@/lib/market";
import { PropertyArt } from "./property-art";

function facts(l: MarketListing) {
  return [
    l.bedrooms ? `${l.bedrooms} BHK` : null,
    typeLabel(l.property_type),
    l.area_sqft ? `${l.area_sqft.toLocaleString("en-IN")} sq ft` : null,
  ].filter(Boolean).join(", ");
}

function Photo({ l, className }: { l: MarketListing; className: string }) {
  return (
    <div className={`relative overflow-hidden bg-stone ${className}`}>
      {l.photo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={l.photo} alt={l.title} loading="lazy" className="h-full w-full object-cover" />
      ) : (
        <PropertyArt type={l.property_type} className="h-full w-full" />
      )}
      {l.photo_count > 1 && (
        <span className="absolute bottom-2 right-2 inline-flex items-center gap-1 rounded bg-ink/70 px-1.5 py-0.5 text-xs text-white">
          <Camera size={12} /> {l.photo_count}
        </span>
      )}
      {l.status === "under_offer" && (
        <span className="absolute left-2 top-2 rounded bg-marigold px-1.5 py-0.5 text-xs font-medium text-ink">Under offer</span>
      )}
    </div>
  );
}

function Price({ l, big = false }: { l: MarketListing; big?: boolean }) {
  return (
    <p className="tnum font-[family-name:var(--font-display)] font-semibold">
      <span className={big ? "text-2xl" : "text-xl"}>{price(l.price)}</span>
      {l.listing_type === "rent" && <span className="text-sm font-normal text-ink-soft"> a month</span>}
      {l.price_per_sqft && (
        <span className="ml-2 text-sm font-normal text-ink-faint">₹{l.price_per_sqft.toLocaleString("en-IN")}/sq ft</span>
      )}
    </p>
  );
}

/** Compact card for grids (home page, similar homes). */
export function ListingTile({ l }: { l: MarketListing }) {
  return (
    <article className="group">
      <Link href={listingHref(l)} className="block">
        <Photo l={l} className="aspect-[4/3] rounded-md" />
        <div className="mt-3">
          <Price l={l} />
          <h3 className="mt-0.5 truncate font-medium group-hover:underline">{l.title}</h3>
          <p className="text-sm text-ink-soft">{facts(l)}</p>
          <p className="text-sm text-ink-soft">{[l.locality, l.city].filter(Boolean).join(", ")}</p>
        </div>
      </Link>
    </article>
  );
}

/** Wide row for search results: photo, facts, and a direct WhatsApp button. */
export function ListingRow({ l }: { l: MarketListing }) {
  return (
    <article className="grid overflow-hidden rounded-lg border border-rule bg-paper sm:grid-cols-[18rem_minmax(0,1fr)]">
      <Link href={listingHref(l)} aria-label={l.title}>
        <Photo l={l} className="aspect-[4/3] h-full sm:aspect-auto sm:min-h-52" />
      </Link>
      <div className="flex min-w-0 flex-col p-4 sm:p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <Link href={listingHref(l)} className="hover:underline">
              <h3 className="text-lg font-semibold leading-snug">{l.title}</h3>
            </Link>
            <p className="text-sm text-ink-soft">{[l.locality, l.city].filter(Boolean).join(", ")}</p>
          </div>
          <span className="shrink-0 text-xs text-ink-faint">{l.ref_code}</span>
        </div>
        <div className="mt-3"><Price l={l} big /></div>
        <dl className="mt-3 grid grid-cols-3 gap-2 border-y border-rule py-3 text-sm">
          <div><dt className="text-ink-faint">Configuration</dt><dd className="font-medium">{l.bedrooms ? `${l.bedrooms} BHK` : typeLabel(l.property_type)}</dd></div>
          <div><dt className="text-ink-faint">Area</dt><dd className="tnum font-medium">{l.area_sqft ? `${l.area_sqft.toLocaleString("en-IN")} sq ft` : "Not given"}</dd></div>
          <div><dt className="text-ink-faint">Bathrooms</dt><dd className="font-medium">{l.bathrooms ?? "Not given"}</dd></div>
        </dl>
        {l.amenities.length > 0 && (
          <p className="mt-3 truncate text-sm capitalize text-ink-soft">{l.amenities.join(", ")}</p>
        )}
        <div className="mt-auto flex flex-wrap items-center gap-2 pt-4">
          <span className="mr-auto text-sm text-ink-soft">Listed by <span className="font-medium text-ink">{l.seller_name}</span></span>
          <Link href={listingHref(l)} className="rounded-md border border-rule px-3 py-2 text-sm font-medium hover:bg-stone">
            View details
          </Link>
          {l.whatsapp_url && (
            <a href={l.whatsapp_url} target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-md bg-registry px-3 py-2 text-sm font-medium text-white hover:bg-registry-deep">
              <MessageCircle size={16} /> WhatsApp seller
            </a>
          )}
        </div>
      </div>
    </article>
  );
}
