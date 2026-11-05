"use client";

import { SlidersHorizontal } from "lucide-react";
import { useRef } from "react";
import { price, PROPERTY_TYPES } from "@/lib/format";
import { RENT_BUDGETS, SALE_BUDGETS } from "@/lib/market";

type Params = Record<string, string[]>;

const box = "h-4 w-4 accent-[var(--color-registry)]";
const input = "h-10 w-full rounded-md border border-rule bg-paper px-3 text-sm focus:border-registry focus:outline-none";

/** GET form: works without JavaScript; with it, every change applies immediately. */
export function Filters({ params }: { params: Params }) {
  const form = useRef<HTMLFormElement>(null);
  const one = (k: string) => params[k]?.[0] ?? "";
  const has = (k: string, v: string) => params[k]?.includes(v) ?? false;
  const apply = () => form.current?.requestSubmit();
  const rent = one("listing_type") === "rent";
  const budgets = rent ? RENT_BUDGETS : SALE_BUDGETS;

  const body = (
    <div className="space-y-6">
      <fieldset>
        <legend className="mb-2 text-sm font-semibold">Looking to</legend>
        <div className="grid grid-cols-3 overflow-hidden rounded-md border border-rule text-sm">
          {[["", "Any"], ["sale", "Buy"], ["rent", "Rent"]].map(([v, label]) => (
            <label key={v} className={`cursor-pointer py-2 text-center ${one("listing_type") === v ? "bg-registry text-white" : "hover:bg-stone"}`}>
              <input type="radio" name="listing_type" value={v} defaultChecked={one("listing_type") === v}
                onChange={apply} className="sr-only" />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      <label className="block">
        <span className="mb-2 block text-sm font-semibold">Area, city or project</span>
        <input name="q" defaultValue={one("q")} placeholder="e.g. Whitefield" className={input} />
      </label>

      <fieldset>
        <legend className="mb-2 text-sm font-semibold">Bedrooms</legend>
        <div className="flex flex-wrap gap-2 text-sm">
          {["1", "2", "3", "4"].map((b) => (
            <label key={b} className="cursor-pointer">
              <input type="checkbox" name="bedrooms" value={b} defaultChecked={has("bedrooms", b)}
                onChange={apply} className="peer sr-only" />
              <span className="inline-block rounded-full border border-rule px-3 py-1 peer-checked:border-registry peer-checked:bg-registry peer-checked:text-white peer-focus-visible:outline-2">
                {b === "4" ? "4+" : b} BHK
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend className="mb-2 text-sm font-semibold">Budget{rent ? " (per month)" : ""}</legend>
        <div className="grid grid-cols-2 gap-2">
          <select name="min_price" defaultValue={one("min_price")} onChange={apply} className={input} aria-label="Minimum price">
            <option value="">No min</option>
            {budgets.map((b) => <option key={b} value={b}>{price(b)}</option>)}
          </select>
          <select name="max_price" defaultValue={one("max_price")} onChange={apply} className={input} aria-label="Maximum price">
            <option value="">No max</option>
            {budgets.map((b) => <option key={b} value={b}>{price(b)}</option>)}
          </select>
        </div>
      </fieldset>

      <fieldset>
        <legend className="mb-2 text-sm font-semibold">Property type</legend>
        <div className="space-y-1.5 text-sm">
          {PROPERTY_TYPES.map((t) => (
            <label key={t.value} className="flex cursor-pointer items-center gap-2">
              <input type="checkbox" name="property_type" value={t.value}
                defaultChecked={has("property_type", t.value)} onChange={apply} className={box} />
              {t.label}
            </label>
          ))}
        </div>
      </fieldset>

      {(one("city") || one("locality")) && (
        <>
          {one("city") && <input type="hidden" name="city" value={one("city")} />}
          {one("locality") && <input type="hidden" name="locality" value={one("locality")} />}
        </>
      )}
      <input type="hidden" name="sort" value={one("sort")} />
      <button type="submit" className="h-10 w-full rounded-md bg-registry text-sm font-medium text-white hover:bg-registry-deep">
        Show homes
      </button>
    </div>
  );

  return (
    <form ref={form} id="filters" action="/properties" method="get"
      onSubmit={(e) => {
        // Drop empty fields so shared URLs stay short.
        for (const el of Array.from(e.currentTarget.elements) as HTMLInputElement[]) {
          if (el.name && !el.value) el.disabled = true;
        }
      }}>
      <details className="rounded-lg border border-rule p-4 lg:hidden">
        <summary className="flex cursor-pointer items-center gap-2 font-medium">
          <SlidersHorizontal size={16} /> Filters
        </summary>
        <div className="mt-4">{body}</div>
      </details>
      <div className="hidden lg:block">{body}</div>
    </form>
  );
}

export function SortSelect({ value }: { value: string }) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-ink-soft">Sort by</span>
      <select
        defaultValue={value || "newest"}
        onChange={(e) => {
          const url = new URL(window.location.href);
          url.searchParams.set("sort", e.target.value);
          url.searchParams.delete("page");
          window.location.assign(url.toString());
        }}
        className="h-9 rounded-md border border-rule bg-paper px-2"
      >
        <option value="newest">Newest first</option>
        <option value="price_asc">Price: low to high</option>
        <option value="price_desc">Price: high to low</option>
        <option value="area_desc">Largest first</option>
      </select>
    </label>
  );
}
