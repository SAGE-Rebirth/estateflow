"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { use, useRef } from "react";
import { Documents } from "@/components/documents";
import { PropertyForm } from "@/components/property-form";
import { Button, ErrorText, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import type { Property } from "@/lib/types";

export default function PropertyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const qc = useQueryClient();
  const me = useMe();
  const input = useRef<HTMLInputElement>(null);
  const prop = useQuery({ queryKey: ["property", id], queryFn: () => api<Property>(`/properties/${id}`) });
  const refresh = () => qc.invalidateQueries({ queryKey: ["property", id] });
  const upload = useMutation({
    mutationFn: async (files: FileList) => {
      for (const file of Array.from(files)) {
        const fd = new FormData();
        fd.append("file", file);
        await api(`/properties/${id}/media`, { method: "POST", body: fd });
      }
    },
    onSettled: refresh,
  });
  const removeMedia = useMutation({
    mutationFn: (mediaId: string) => api(`/properties/${id}/media/${mediaId}`, { method: "DELETE" }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: () => api(`/properties/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["properties"] });
      router.replace("/dashboard/properties");
    },
  });
  const p = prop.data;
  if (!p) return <p className="text-ink-faint">Loading…</p>;

  return (
    <>
      <PageHeader
        title={p.title}
        subtitle={<>Ref code <span className="font-semibold text-registry">{p.ref_code}</span>. Buyers who mention it on WhatsApp are linked to this listing.</>}
        actions={
          <>
            {p.published && me.data && (
              <a href={`/properties/${me.data.tenant.slug}/${p.ref_code}`} target="_blank" rel="noreferrer">
                <Button variant="secondary">View public page</Button>
              </a>
            )}
            <Button variant="danger" onClick={() => confirm(`Delete ${p.ref_code}? This can't be undone.`) && remove.mutate()}>
              Delete
            </Button>
          </>
        }
      />
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <PropertyForm key={p.updated_at} property={p} />
        <aside className="space-y-8">
          <section>
            <h2 className="mb-3 font-semibold">Photos</h2>
            <ul className="mb-3 grid grid-cols-2 gap-2">
              {p.media.map((m) => (
                <li key={m.id} className="group relative aspect-square overflow-hidden rounded bg-stone">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={m.url} alt="" className="h-full w-full object-cover" />
                  <button
                    onClick={() => removeMedia.mutate(m.id)} aria-label="Remove photo"
                    className="absolute right-1 top-1 rounded bg-paper/90 p-1 text-brick opacity-0 group-hover:opacity-100 focus:opacity-100"
                  >
                    <Trash2 size={14} />
                  </button>
                </li>
              ))}
            </ul>
            <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" multiple hidden
              onChange={(e) => { if (e.target.files?.length) upload.mutate(e.target.files); e.target.value = ""; }} />
            <Button size="sm" variant="secondary" disabled={upload.isPending} onClick={() => input.current?.click()}>
              {upload.isPending ? "Uploading…" : "Add photos"}
            </Button>
            <ErrorText error={upload.error} />
          </section>
          <section>
            <h2 className="mb-1 font-semibold">Brochures and price sheets</h2>
            <p className="mb-3 text-xs text-ink-faint">The assistant answers questions about this property from these.</p>
            <Documents propertyId={p.id} />
          </section>
        </aside>
      </div>
    </>
  );
}
