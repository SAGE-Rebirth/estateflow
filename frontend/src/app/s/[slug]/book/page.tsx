"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { CalendarCheck } from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Button, ErrorText, Field, Input, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { day, time } from "@/lib/format";
import type { Slot } from "@/lib/types";

export default function BookPage() {
  return <Suspense><Booking /></Suspense>;
}

function Booking() {
  const { slug } = useParams<{ slug: string }>();
  const ref = useSearchParams().get("ref");
  const [slot, setSlot] = useState("");
  const tenant = useQuery({
    queryKey: ["public", slug],
    queryFn: () => api<{ name: string; timezone: string }>(`/public/${slug}`, { auth: false }),
  });
  const tz = tenant.data?.timezone;
  const slots = useQuery({
    queryKey: ["public", slug, "slots"],
    queryFn: () => api<Slot[]>(`/public/${slug}/slots?days=7`, { auth: false }),
  });
  const book = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<{ starts_at: string; location: string | null }>(`/public/${slug}/bookings`, { method: "POST", json: body, auth: false }),
    onError: () => slots.refetch(),
  });

  const byDay = new Map<string, Slot[]>();
  for (const s of slots.data ?? []) {
    const k = day(s.starts_at, tz);
    byDay.set(k, [...(byDay.get(k) ?? []), s]);
  }

  if (book.data) {
    return (
      <main className="mx-auto max-w-xl px-4 py-16 sm:px-6">
        <CalendarCheck size={32} className="text-registry" />
        <h1 className="mt-4 text-3xl font-semibold">Your visit is booked</h1>
        <p className="mt-2 text-lg tnum">{day(book.data.starts_at, tz)} at {time(book.data.starts_at, tz)}</p>
        {book.data.location && <p className="text-ink-soft">{book.data.location}</p>}
        <p className="mt-4 text-ink-soft">We&apos;ll confirm on WhatsApp and remind you before the visit. Reply there if you need to change the time.</p>
        <div className="mt-8 flex flex-wrap gap-4">
          {ref && <Link href={`/properties/${slug}/${ref}`} className="text-registry hover:underline">Back to the listing</Link>}
          <Link href="/properties" className="text-registry hover:underline">Browse more homes</Link>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <Link href={ref ? `/properties/${slug}/${ref}` : `/s/${slug}`} className="text-sm text-ink-soft hover:underline">
        {ref ? `Back to ${ref}` : "Back to all homes from this seller"}
      </Link>
      <h1 className="mt-2 text-3xl font-semibold">Book a site visit{ref ? ` for ${ref}` : ""}</h1>
      <p className="mt-2 text-ink-soft">Pick a time that suits you. Someone from {tenant.data?.name ?? "the team"} will meet you there.</p>
      <form
        className="mt-8 space-y-8"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          book.mutate({
            name: f.get("name"), phone: f.get("phone"), email: f.get("email") || null,
            notes: f.get("notes") || null, starts_at: slot, property_ref: ref, kind: "site_visit",
          });
        }}
      >
        <fieldset>
          <legend className="mb-3 font-semibold">Choose a time</legend>
          {slots.isLoading && <p className="text-sm text-ink-faint">Loading times…</p>}
          {slots.data?.length === 0 && <p className="text-sm text-ink-soft">No open times this week. Message us on WhatsApp and we&apos;ll fit you in.</p>}
          <div className="space-y-4">
            {[...byDay.entries()].map(([d, list]) => (
              <div key={d} className="grid gap-2 sm:grid-cols-[8rem_minmax(0,1fr)]">
                <p className="text-sm font-medium sm:pt-1.5">{d}</p>
                <div className="flex flex-wrap gap-2">
                  {list.map((s) => (
                    <button type="button" key={s.starts_at} onClick={() => setSlot(s.starts_at)} aria-pressed={slot === s.starts_at}
                      className={`tnum rounded-md border px-3 py-1.5 text-sm ${slot === s.starts_at ? "border-registry bg-registry text-white" : "border-rule hover:border-registry"}`}>
                      {time(s.starts_at, tz)}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </fieldset>
        <fieldset className="grid gap-4 sm:grid-cols-2">
          <legend className="mb-3 font-semibold">Your details</legend>
          <Field label="Name"><Input name="name" required autoComplete="name" /></Field>
          <Field label="WhatsApp number"><Input name="phone" required type="tel" autoComplete="tel" /></Field>
          <Field label="Email (optional)" className="sm:col-span-2"><Input name="email" type="email" autoComplete="email" /></Field>
          <Field label="Anything we should know?" className="sm:col-span-2">
            <Textarea name="notes" rows={2} placeholder="Coming with family, need parking…" />
          </Field>
        </fieldset>
        <ErrorText error={book.error} />
        <Button type="submit" disabled={!slot || book.isPending} className="h-12 w-full sm:w-auto">
          {book.isPending ? "Booking…" : slot ? `Book ${day(slot, tz)}, ${time(slot, tz)}` : "Choose a time first"}
        </Button>
      </form>
    </main>
  );
}
