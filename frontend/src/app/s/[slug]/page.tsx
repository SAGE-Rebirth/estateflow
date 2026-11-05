import { ImageOff, MessageCircle } from "lucide-react";
import Link from "next/link";
import { price, PROPERTY_TYPES, typeLabel, waLink } from "@/lib/format";
import { publicGet, type PublicProperty, type PublicTenant } from "@/lib/public-api";

export default async function Listings({
  params, searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const { slug } = await params;
  const sp = await searchParams;
  const t = await publicGet<PublicTenant>(`/${slug}`);
  const q = new URLSearchParams();
  for (const k of ["listing_type", "property_type", "min_bedrooms", "max_price", "city"]) {
    if (sp[k]) q.set(k, sp[k]!);
  }
  const data = await publicGet<{ items: PublicProperty[]; total: number }>(`/${slug}/properties?${q}`);
  const sel = "h-10 rounded-md border border-rule bg-paper px-2 text-sm";

  return (
    <main className="mx-auto max-w-6xl px-4 sm:px-6">
      <section className="grid gap-6 py-10 sm:py-14 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
        <div>
          <h1 className="max-w-2xl text-4xl font-semibold leading-tight sm:text-5xl">
            {data.total} {data.total === 1 ? "home" : "homes"} you can visit this week
          </h1>
          <p className="mt-3 max-w-xl text-ink-soft">
            Ask about any listing on WhatsApp. You get answers straight away, and can book a site visit in the same chat.
          </p>
        </div>
        {t.whatsapp_number && (
          <a href={waLink(t.whatsapp_number, `Hi ${t.name}, I'm looking for a property`)} target="_blank" rel="noreferrer"
            className="inline-flex h-12 items-center gap-2 rounded-md bg-registry px-5 font-medium text-white hover:bg-registry-deep">
            <MessageCircle size={18} /> Chat on WhatsApp
          </a>
        )}
      </section>

      <form className="mb-8 flex flex-wrap items-end gap-2 border-y border-rule py-4" method="get">
        <select name="listing_type" defaultValue={sp.listing_type ?? ""} className={sel} aria-label="Buy or rent">
          <option value="">Buy or rent</option><option value="sale">Buy</option><option value="rent">Rent</option>
        </select>
        <select name="property_type" defaultValue={sp.property_type ?? ""} className={sel} aria-label="Type">
          <option value="">Any type</option>
          {PROPERTY_TYPES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
        <select name="min_bedrooms" defaultValue={sp.min_bedrooms ?? ""} className={sel} aria-label="Bedrooms">
          <option value="">Any size</option>
          {[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}+ BHK</option>)}
        </select>
        <select name="max_price" defaultValue={sp.max_price ?? ""} className={sel} aria-label="Budget">
          <option value="">Any budget</option>
          {[5e6, 1e7, 2e7, 5e7].map((n) => <option key={n} value={n}>Up to {price(n)}</option>)}
        </select>
        <button className="h-10 rounded-md border border-ink px-4 text-sm font-medium hover:bg-stone">Show homes</button>
      </form>

      {data.items.length === 0 && (
        <p className="py-10 text-ink-soft">Nothing matches those filters right now. Message us on WhatsApp and we&apos;ll tell you when something comes up.</p>
      )}
      <ul className="grid gap-x-6 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
        {data.items.map((p) => (
          <li key={p.ref_code}>
            <Link href={`/properties/${slug}/${p.ref_code}`} className="group block">
              <div className="aspect-[4/3] overflow-hidden rounded-md bg-stone">
                {p.media[0] ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={p.media[0].url} alt={p.title} className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.02]" />
                ) : (
                  <div className="grid h-full place-items-center text-ink-faint"><ImageOff size={28} /></div>
                )}
              </div>
              <p className="tnum mt-3 font-[family-name:var(--font-display)] text-2xl font-semibold">
                {price(p.price, t.currency)}
                {p.listing_type === "rent" && <span className="text-base font-normal text-ink-soft"> a month</span>}
              </p>
              <p className="font-medium group-hover:underline">{p.title}</p>
              <p className="text-sm text-ink-soft">
                {[p.bedrooms && `${p.bedrooms} BHK`, p.area_sqft && `${Number(p.area_sqft).toLocaleString("en-IN")} sq ft`, typeLabel(p.property_type)]
                  .filter(Boolean).join(", ")}
              </p>
              <p className="text-sm text-ink-soft">{[p.locality, p.city].filter(Boolean).join(", ")}</p>
              {p.status === "under_offer" && <p className="mt-1 text-sm font-medium text-[#8a5f0c]">Under offer</p>}
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
