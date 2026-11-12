import Link from "next/link";
import { HeroSearch } from "@/components/site/hero-search";
import { ListingTile } from "@/components/site/listing-card";
import { price, typeLabel } from "@/lib/format";
import { market, RENT_BUDGETS, SALE_BUDGETS } from "@/lib/market";
import type { PropertyType } from "@/lib/types";

// Rendered per request (data cached 30 s) so builds never need a running API.
export const dynamic = "force-dynamic";

export const metadata = {
  title: "EstateFlow — homes for sale and rent, direct from sellers",
  description: "Browse apartments, villas and plots listed by brokers and builders. Ask on WhatsApp and book a site visit.",
};

export default async function Home() {
  const [summary, latest] = await Promise.all([
    market.summary(),
    market.listings(new URLSearchParams({ limit: "8", sort: "newest" })),
  ]);
  const places = [...summary.localities.map((l) => l.value), ...summary.cities.map((c) => c.value)];

  return (
    <main>
      <section className="border-b border-rule bg-stone">
        <div className="mx-auto max-w-7xl px-4 pb-14 pt-12 sm:px-6 sm:pb-20 sm:pt-16">
          {/* The hero is a sentence-shaped search form; this names the page for screen readers and search. */}
          <h1 className="sr-only">Homes for sale and rent, direct from sellers</h1>
          <HeroSearch places={places} />
          {summary.localities.length > 0 && (
            <div className="mt-10 flex flex-wrap items-center gap-2 text-sm">
              <span className="text-ink-soft">Popular right now:</span>
              {summary.localities.slice(0, 8).map((l) => (
                <Link key={l.value} href={`/properties?locality=${encodeURIComponent(l.value)}`}
                  className="rounded-full border border-rule bg-paper px-3 py-1 hover:border-registry">
                  {l.value} <span className="text-ink-faint">{l.count}</span>
                </Link>
              ))}
            </div>
          )}
        </div>
      </section>

      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <section className="py-12">
          <div className="mb-6 flex items-end justify-between gap-4">
            <div>
              <h2 className="text-2xl font-semibold">Newly listed</h2>
              <p className="text-sm text-ink-soft">
                {summary.for_sale} for sale and {summary.for_rent} for rent, straight from the sellers.
              </p>
            </div>
            <Link href="/properties" className="text-sm font-medium text-registry hover:underline">See all homes</Link>
          </div>
          {latest.items.length === 0 ? (
            <p className="text-ink-soft">No homes are listed yet. Check back soon, or list yours.</p>
          ) : (
            <ul className="grid gap-x-6 gap-y-10 sm:grid-cols-2 lg:grid-cols-4">
              {latest.items.map((l) => <li key={l.id}><ListingTile l={l} /></li>)}
            </ul>
          )}
        </section>

        <section className="grid gap-10 border-t border-rule py-12 md:grid-cols-3">
          <div>
            <h2 className="mb-3 text-lg font-semibold">By city</h2>
            <ul className="space-y-1.5">
              {summary.cities.map((c) => (
                <li key={c.value}>
                  <Link href={`/properties?city=${encodeURIComponent(c.value)}`} className="flex justify-between gap-4 hover:text-registry">
                    <span>{c.value}</span><span className="tnum text-ink-faint">{c.count}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h2 className="mb-3 text-lg font-semibold">By type</h2>
            <ul className="space-y-1.5">
              {summary.property_types.map((t) => (
                <li key={t.value}>
                  <Link href={`/properties?property_type=${t.value}`} className="flex justify-between gap-4 hover:text-registry">
                    <span>{typeLabel(t.value as PropertyType)}</span><span className="tnum text-ink-faint">{t.count}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h2 className="mb-3 text-lg font-semibold">By budget</h2>
            <ul className="space-y-1.5">
              {SALE_BUDGETS.slice(1, 5).map((b) => (
                <li key={b}><Link href={`/properties?listing_type=sale&max_price=${b}`} className="hover:text-registry">To buy, under {price(b)}</Link></li>
              ))}
              {RENT_BUDGETS.slice(1, 3).map((b) => (
                <li key={b}><Link href={`/properties?listing_type=rent&max_price=${b}`} className="hover:text-registry">To rent, under {price(b)} a month</Link></li>
              ))}
            </ul>
          </div>
        </section>

        <section className="border-t border-rule py-12">
          <h2 className="mb-6 text-lg font-semibold">How it works</h2>
          <ol className="grid gap-8 md:grid-cols-3">
            {[
              ["Find a home", "Filter by area, size and budget. Every listing shows the price and who is selling it."],
              ["Ask on WhatsApp", "Tap WhatsApp on any listing. You get answers about price, loans and possession in minutes, any time of day."],
              ["Visit", "Pick a time in the same chat or on the listing. You get a confirmation and a reminder before the visit."],
            ].map(([title, body], i) => (
              <li key={title} className="flex gap-4">
                <span className="tnum font-[family-name:var(--font-display)] text-3xl font-semibold text-registry">{i + 1}</span>
                <div><p className="font-medium">{title}</p><p className="mt-1 text-sm text-ink-soft">{body}</p></div>
              </li>
            ))}
          </ol>
        </section>

        <section className="mb-4 rounded-lg bg-registry px-6 py-10 text-white sm:px-10">
          <h2 className="text-2xl font-semibold">Selling or renting out a property?</h2>
          <p className="mt-2 max-w-2xl text-white/80">
            List it here. Buyers&apos; questions are answered on your WhatsApp number automatically, and site visits land on your calendar.
          </p>
          <Link href="/signup" className="mt-5 inline-block rounded-md bg-paper px-5 py-2.5 font-medium text-registry hover:bg-registry-tint">
            List your property
          </Link>
        </section>
      </div>
    </main>
  );
}
