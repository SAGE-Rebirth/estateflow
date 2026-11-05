"use client";

import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { price } from "@/lib/format";
import { RENT_BUDGETS, SALE_BUDGETS } from "@/lib/market";

// field-sizing lets each blank shrink to its current value, so the sentence reads naturally.
const slot =
  "appearance-none rounded-none border-0 border-b-2 border-registry bg-transparent px-1 pb-0.5 font-semibold text-registry [field-sizing:content] focus:border-ink focus:outline-none";

/** "I want to buy a 3 BHK in Hebbal under ₹1 Cr" — the search reads as the buyer's sentence. */
export function HeroSearch({ places }: { places: string[] }) {
  const router = useRouter();
  const [mode, setMode] = useState<"sale" | "rent">("sale");
  const [bhk, setBhk] = useState("");
  const [where, setWhere] = useState("");
  const [budget, setBudget] = useState("");
  const budgets = mode === "sale" ? SALE_BUDGETS : RENT_BUDGETS;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const p = new URLSearchParams({ listing_type: mode });
    if (bhk) p.set("bedrooms", bhk);
    if (where.trim()) p.set("q", where.trim());
    if (budget) p.set("max_price", budget);
    router.push(`/properties?${p}`);
  }

  return (
    <form onSubmit={submit} className="max-w-6xl">
      <p className="font-[family-name:var(--font-display)] text-3xl leading-[1.5] text-ink sm:text-[2.6rem] sm:leading-[1.45]">
        I want to{" "}
        <select aria-label="Buy or rent" value={mode} className={slot}
          onChange={(e) => { setMode(e.target.value as "sale" | "rent"); setBudget(""); }}>
          <option value="sale">buy</option>
          <option value="rent">rent</option>
        </select>{" "}
        a{" "}
        <select aria-label="Size" value={bhk} onChange={(e) => setBhk(e.target.value)} className={slot}>
          <option value="">home</option>
          <option value="1">1 BHK</option>
          <option value="2">2 BHK</option>
          <option value="3">3 BHK</option>
          <option value="4">4+ BHK</option>
        </select>{" "}
        in{" "}
        <input
          aria-label="City, area or project" list="places" value={where}
          onChange={(e) => setWhere(e.target.value)} placeholder="any area"
          className={`${slot} min-w-[9ch] max-w-full placeholder:font-normal placeholder:text-ink-faint no-datalist-arrow`}
        />{" "}
        <datalist id="places">{places.map((p) => <option key={p} value={p} />)}</datalist>
        under{" "}
        <select aria-label="Budget" value={budget} onChange={(e) => setBudget(e.target.value)} className={slot}>
          <option value="">any budget</option>
          {budgets.map((b) => (
            <option key={b} value={b}>{price(b)}{mode === "rent" ? " a month" : ""}</option>
          ))}
        </select>
      </p>
      <button type="submit"
        className="mt-6 inline-flex h-12 items-center gap-2 rounded-md bg-registry px-6 font-medium text-white hover:bg-registry-deep">
        <Search size={18} /> Show me homes
      </button>
    </form>
  );
}
