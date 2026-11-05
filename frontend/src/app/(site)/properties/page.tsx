import { X } from "lucide-react";
import Link from "next/link";
import { Filters, SortSelect } from "@/components/site/filters";
import { ListingRow } from "@/components/site/listing-card";
import { price, typeLabel } from "@/lib/format";
import { FILTER_KEYS, market } from "@/lib/market";
import type { PropertyType } from "@/lib/types";

const PAGE_SIZE = 12;

type SP = Record<string, string | string[] | undefined>;

function normalize(sp: SP): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const k of [...FILTER_KEYS, "page"]) {
    const v = sp[k];
    const list = (Array.isArray(v) ? v : v ? [v] : []).filter(Boolean);
    if (list.length) out[k] = list;
  }
  return out;
}

function headline(p: Record<string, string[]>, total: number) {
  const what = p.listing_type?.[0] === "rent" ? "for rent" : p.listing_type?.[0] === "sale" ? "for sale" : "";
  const where = p.locality?.[0] ?? p.city?.[0] ?? p.q?.[0];
  return `${total} ${total === 1 ? "home" : "homes"}${what ? ` ${what}` : ""}${where ? ` in ${where}` : ""}`;
}

export async function generateMetadata({ searchParams }: { searchParams: Promise<SP> }) {
  const p = normalize(await searchParams);
  const where = p.locality?.[0] ?? p.city?.[0];
  return { title: `Homes${where ? ` in ${where}` : ""} | EstateFlow` };
}

export default async function PropertiesPage({ searchParams }: { searchParams: Promise<SP> }) {
  const p = normalize(await searchParams);
  const page = Math.max(1, Number(p.page?.[0] ?? 1) || 1);
  const api = new URLSearchParams();
  for (const k of FILTER_KEYS) for (const v of p[k] ?? []) api.append(k, v);
  api.set("limit", String(PAGE_SIZE));
  api.set("offset", String((page - 1) * PAGE_SIZE));
  const data = await market.listings(api);
  const pages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));

  const without = (key: string, value?: string) => {
    const q = new URLSearchParams();
    for (const [k, vs] of Object.entries(p)) {
      if (k === "page") continue;
      for (const v of vs) if (!(k === key && (value === undefined || v === value))) q.append(k, v);
    }
    const s = q.toString();
    return s ? `/properties?${s}` : "/properties";
  };
  const pageHref = (n: number) => {
    const q = new URLSearchParams(without("page").split("?")[1] ?? "");
    if (n > 1) q.set("page", String(n));
    const s = q.toString();
    return s ? `/properties?${s}` : "/properties";
  };

  const chips: { label: string; href: string }[] = [];
  if (p.listing_type) chips.push({ label: p.listing_type[0] === "rent" ? "To rent" : "To buy", href: without("listing_type") });
  for (const k of ["q", "city", "locality"] as const) {
    if (p[k]) chips.push({ label: p[k][0], href: without(k) });
  }
  for (const b of p.bedrooms ?? []) chips.push({ label: `${b === "4" ? "4+" : b} BHK`, href: without("bedrooms", b) });
  for (const t of p.property_type ?? []) chips.push({ label: typeLabel(t as PropertyType), href: without("property_type", t) });
  if (p.min_price) chips.push({ label: `From ${price(p.min_price[0])}`, href: without("min_price") });
  if (p.max_price) chips.push({ label: `Up to ${price(p.max_price[0])}`, href: without("max_price") });

  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <div className="grid gap-8 lg:grid-cols-[17rem_minmax(0,1fr)]">
        <aside className="lg:sticky lg:top-24 lg:self-start">
          <Filters params={p} />
        </aside>
        <section aria-labelledby="results">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <h1 id="results" className="text-2xl font-semibold sm:text-3xl">{headline(p, data.total)}</h1>
            <SortSelect value={p.sort?.[0] ?? ""} />
          </div>
          {chips.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {chips.map((c) => (
                <Link key={c.label + c.href} href={c.href} aria-label={`Remove filter ${c.label}`}
                  className="inline-flex items-center gap-1 rounded-full bg-registry-tint px-3 py-1 text-sm text-registry-deep hover:bg-rule">
                  {c.label} <X size={14} />
                </Link>
              ))}
              <Link href="/properties" className="px-2 py-1 text-sm text-ink-soft underline">Clear all</Link>
            </div>
          )}

          {data.items.length === 0 ? (
            <div className="mt-10 max-w-md">
              <p className="font-medium">No homes match these filters.</p>
              <p className="mt-1 text-sm text-ink-soft">Try a wider budget, another area, or remove a filter above.</p>
            </div>
          ) : (
            <ul className="mt-6 space-y-5">
              {data.items.map((l) => <li key={l.id}><ListingRow l={l} /></li>)}
            </ul>
          )}

          {pages > 1 && (
            <nav className="mt-10 flex items-center justify-center gap-1 text-sm" aria-label="Pages">
              {page > 1 && <Link href={pageHref(page - 1)} className="rounded-md px-3 py-2 hover:bg-stone">Previous</Link>}
              {Array.from({ length: pages }, (_, i) => i + 1).map((n) => (
                <Link key={n} href={pageHref(n)} aria-current={n === page ? "page" : undefined}
                  className={`tnum rounded-md px-3 py-2 ${n === page ? "bg-registry text-white" : "hover:bg-stone"}`}>
                  {n}
                </Link>
              ))}
              {page < pages && <Link href={pageHref(page + 1)} className="rounded-md px-3 py-2 hover:bg-stone">Next</Link>}
            </nav>
          )}
        </section>
      </div>
    </main>
  );
}
