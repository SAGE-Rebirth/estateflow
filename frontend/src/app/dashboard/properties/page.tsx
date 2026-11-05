"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLink, ImageOff, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Empty, Input, PageHeader, Select } from "@/components/ui";
import { api, qs } from "@/lib/api";
import { price, typeLabel } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import type { Page, Property } from "@/lib/types";

const STATUS_TONE = { draft: "neutral", available: "green", under_offer: "gold", sold: "red", rented: "red" } as const;

export default function PropertiesPage() {
  const me = useMe();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const props = useQuery({
    queryKey: ["properties", q, status],
    queryFn: () => api<Page<Property>>(`/properties${qs({ q, status, limit: 200 })}`),
  });
  const slug = me.data?.tenant.slug;

  return (
    <>
      <PageHeader
        title="Properties"
        subtitle={props.data ? `${props.data.total} listings` : undefined}
        actions={
          <>
            {slug && (
              <a href={`/s/${slug}`} target="_blank" rel="noreferrer">
                <Button variant="secondary"><ExternalLink size={16} /> View listing page</Button>
              </a>
            )}
            <Link href="/dashboard/properties/new"><Button><Plus size={16} /> Add property</Button></Link>
          </>
        }
      />
      <div className="mb-5 flex flex-wrap gap-2">
        <Input placeholder="Search title, ref code or area" value={q} onChange={(e) => setQ(e.target.value)} className="w-full max-w-xs" />
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-44" aria-label="Status">
          <option value="">Any status</option>
          <option value="available">Available</option><option value="under_offer">Under offer</option>
          <option value="sold">Sold</option><option value="rented">Rented</option><option value="draft">Draft</option>
        </Select>
      </div>
      {props.data?.items.length === 0 && (
        <Empty action={<Link href="/dashboard/properties/new"><Button size="sm">Add property</Button></Link>}>
          No properties yet. Add your first listing and the WhatsApp assistant can start offering it.
        </Empty>
      )}
      <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {props.data?.items.map((p) => (
          <li key={p.id}>
            <Link href={`/dashboard/properties/${p.id}`} className="group block overflow-hidden rounded-lg border border-rule bg-paper">
              <div className="aspect-[4/3] bg-stone">
                {p.media[0] ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={p.media[0].url} alt="" className="h-full w-full object-cover" />
                ) : (
                  <div className="grid h-full place-items-center text-ink-faint"><ImageOff size={28} /></div>
                )}
              </div>
              <div className="p-4">
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-semibold text-registry">{p.ref_code}</span>
                  <Badge tone={STATUS_TONE[p.status]}>{p.status.replace("_", " ")}</Badge>
                  {!p.published && <Badge>Hidden</Badge>}
                </div>
                <p className="mt-1.5 font-medium group-hover:underline">{p.title}</p>
                <p className="tnum mt-1 font-[family-name:var(--font-display)] text-xl font-semibold">
                  {price(p.price, me.data?.tenant.currency)}
                  {p.listing_type === "rent" && <span className="text-sm font-normal text-ink-soft"> a month</span>}
                </p>
                <p className="mt-1 text-sm text-ink-soft">
                  {[p.bedrooms && `${p.bedrooms} BHK`, typeLabel(p.property_type), p.locality].filter(Boolean).join(", ")}
                </p>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
