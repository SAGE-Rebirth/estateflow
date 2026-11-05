import { CalendarCheck, MapPin, MessageCircle } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Gallery, ShareButton } from "@/components/site/gallery";
import { ListingTile } from "@/components/site/listing-card";
import { price, typeLabel } from "@/lib/format";
import { market } from "@/lib/market";

type Params = Promise<{ slug: string; ref: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { slug, ref } = await params;
  const l = await market.listing(slug, ref);
  const where = [l.locality, l.city].filter(Boolean).join(", ");
  return {
    title: `${l.title}${where ? `, ${where}` : ""} | ${price(l.price)} | EstateFlow`,
    description: l.description.slice(0, 160) || `${l.title} listed by ${l.seller.name}.`,
    openGraph: { title: l.title, images: l.photos.slice(0, 1) },
  };
}

export default async function ListingPage({ params }: { params: Params }) {
  const { slug, ref } = await params;
  const l = await market.listing(slug, ref);
  const where = [l.locality, l.city].filter(Boolean).join(", ");
  const mapQuery = l.latitude && l.longitude ? `${l.latitude},${l.longitude}` : where;
  const rent = l.listing_type === "rent";
  const facts: [string, string | number | null][] = [
    ["Configuration", l.bedrooms ? `${l.bedrooms} BHK` : null],
    ["Type", typeLabel(l.property_type)],
    ["Area", l.area_sqft ? `${l.area_sqft.toLocaleString("en-IN")} sq ft` : null],
    ["Price per sq ft", l.price_per_sqft ? `₹${l.price_per_sqft.toLocaleString("en-IN")}` : null],
    ["Bathrooms", l.bathrooms],
    ["Status", l.status === "under_offer" ? "Under offer" : rent ? "Available to rent" : "Available"],
  ];
  const bookHref = `/s/${l.seller.slug}/book?ref=${l.ref_code}`;

  return (
    <main className="mx-auto max-w-7xl px-4 pb-28 pt-6 sm:px-6 lg:pb-10">
      <nav className="mb-4 text-sm text-ink-soft" aria-label="Breadcrumb">
        <Link href="/properties" className="hover:underline">Homes</Link>
        {l.city && (<> / <Link href={`/properties?city=${encodeURIComponent(l.city)}`} className="hover:underline">{l.city}</Link></>)}
        {l.locality && (<> / <Link href={`/properties?locality=${encodeURIComponent(l.locality)}`} className="hover:underline">{l.locality}</Link></>)}
      </nav>

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <article className="min-w-0">
          <Gallery photos={l.photos} title={l.title} type={l.property_type} />

          <div className="mt-6 flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="text-3xl font-semibold leading-tight sm:text-4xl">{l.title}</h1>
              {where && <p className="mt-1 flex items-center gap-1 text-ink-soft"><MapPin size={16} /> {where}</p>}
            </div>
            <div className="text-right">
              <p className="tnum font-[family-name:var(--font-display)] text-3xl font-semibold">{price(l.price)}</p>
              {rent && <p className="text-sm text-ink-soft">a month</p>}
            </div>
          </div>

          <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-4 border-y border-rule py-5 sm:grid-cols-3">
            {facts.filter(([, v]) => v !== null && v !== "").map(([k, v]) => (
              <div key={k}><dt className="text-sm text-ink-soft">{k}</dt><dd className="tnum font-medium">{v}</dd></div>
            ))}
          </dl>

          {l.description && (
            <section className="mt-8">
              <h2 className="text-lg font-semibold">About this home</h2>
              <p className="mt-2 max-w-prose whitespace-pre-line leading-relaxed">{l.description}</p>
            </section>
          )}

          {l.amenities.length > 0 && (
            <section className="mt-8">
              <h2 className="text-lg font-semibold">Amenities</h2>
              <ul className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
                {l.amenities.map((a) => (
                  <li key={a} className="rounded-md border border-rule px-3 py-2 text-sm capitalize">{a}</li>
                ))}
              </ul>
            </section>
          )}

          {l.floorplans.length > 0 && (
            <section className="mt-8">
              <h2 className="text-lg font-semibold">Floor plan</h2>
              {l.floorplans.map((src) => (
                // eslint-disable-next-line @next/next/no-img-element
                <img key={src} src={src} alt="Floor plan" className="mt-3 max-h-[32rem] rounded-md border border-rule" />
              ))}
            </section>
          )}

          {mapQuery && (
            <section className="mt-8">
              <h2 className="text-lg font-semibold">Location</h2>
              <p className="mt-1 text-sm text-ink-soft">The exact address is shared by the seller when you book a visit.</p>
              <iframe
                title={`Map of ${where}`}
                src={`https://maps.google.com/maps?q=${encodeURIComponent(mapQuery)}&z=14&output=embed`}
                className="mt-3 h-72 w-full rounded-md border border-rule"
                loading="lazy"
                referrerPolicy="no-referrer-when-downgrade"
              />
            </section>
          )}
        </article>

        <aside className="lg:sticky lg:top-24 lg:self-start">
          <div className="rounded-lg border border-rule p-5">
            <p className="text-sm text-ink-soft">Listed by</p>
            <p className="text-lg font-semibold">{l.seller.name}</p>
            <p className="mt-3 text-sm text-ink-soft">
              Ask about price, loans, possession or a video tour. Replies come straight away on WhatsApp.
            </p>
            {l.whatsapp_url ? (
              <a href={l.whatsapp_url} target="_blank" rel="noreferrer"
                className="mt-4 flex h-12 items-center justify-center gap-2 rounded-md bg-registry font-medium text-white hover:bg-registry-deep">
                <MessageCircle size={18} /> Chat on WhatsApp
              </a>
            ) : (
              <p className="mt-4 rounded-md bg-stone p-3 text-sm text-ink-soft">This seller hasn&apos;t connected WhatsApp yet. Book a visit instead.</p>
            )}
            <Link href={bookHref}
              className="mt-2 flex h-12 items-center justify-center gap-2 rounded-md border border-rule font-medium hover:bg-stone">
              <CalendarCheck size={18} /> Book a site visit
            </Link>
            <div className="mt-4 flex items-center justify-between border-t border-rule pt-3 text-xs text-ink-faint">
              <span>Ref {l.ref_code}</span>
              <ShareButton title={l.title} />
            </div>
          </div>
          <Link href={`/properties?seller=${l.seller.slug}`} className="mt-3 block text-sm text-registry hover:underline">
            More homes from {l.seller.name}
          </Link>
        </aside>
      </div>

      {l.similar.length > 0 && (
        <section className="mt-16 border-t border-rule pt-10">
          <h2 className="mb-6 text-2xl font-semibold">Similar homes{l.city ? ` in ${l.city}` : ""}</h2>
          <ul className="grid gap-x-6 gap-y-10 sm:grid-cols-2 lg:grid-cols-4">
            {l.similar.map((s) => <li key={s.id}><ListingTile l={s} /></li>)}
          </ul>
        </section>
      )}

      {/* Phones: keep the two actions in reach while scrolling. */}
      <div className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-2 gap-2 border-t border-rule bg-paper p-3 lg:hidden">
        {l.whatsapp_url && (
          <a href={l.whatsapp_url} target="_blank" rel="noreferrer"
            className="flex h-11 items-center justify-center gap-2 rounded-md bg-registry text-sm font-medium text-white">
            <MessageCircle size={16} /> WhatsApp
          </a>
        )}
        <Link href={bookHref} className={`flex h-11 items-center justify-center gap-2 rounded-md border border-rule text-sm font-medium ${l.whatsapp_url ? "" : "col-span-2"}`}>
          <CalendarCheck size={16} /> Book a visit
        </Link>
      </div>
    </main>
  );
}
