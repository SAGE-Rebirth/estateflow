"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, RotateCw, Trash2 } from "lucide-react";
import { useRef } from "react";
import { api, qs } from "@/lib/api";
import type { KnowledgeDoc } from "@/lib/types";
import { Badge, Button, ErrorText } from "./ui";

const TONE = { pending: "neutral", processing: "gold", ready: "green", failed: "red" } as const;
const LABEL = { pending: "Queued", processing: "Reading", ready: "Assistant can use it", failed: "Couldn't read" };

/** Brochures, price sheets, FAQs the WhatsApp assistant answers from. */
export function Documents({ propertyId }: { propertyId?: string }) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const key = ["documents", propertyId ?? "tenant"];
  const docs = useQuery({
    queryKey: key,
    queryFn: () => api<KnowledgeDoc[]>(`/documents${qs({ property_id: propertyId })}`),
    // Keep polling while something is still being read.
    refetchInterval: (q) =>
      q.state.data?.some((d) => d.status === "pending" || d.status === "processing") ? 3000 : false,
  });
  const visible = propertyId ? docs.data : docs.data?.filter((d) => !d.property_id);
  const upload = useMutation({
    mutationFn: async (files: FileList) => {
      for (const file of Array.from(files)) {
        const fd = new FormData();
        fd.append("file", file);
        if (propertyId) fd.append("property_id", propertyId);
        await api("/documents", { method: "POST", body: fd });
      }
    },
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
  const retry = useMutation({
    mutationFn: (id: string) => api(`/documents/${id}/retry`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/documents/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  });

  return (
    <div>
      <ul className="mb-3 divide-y divide-rule border-y border-rule">
        {visible?.length === 0 && (
          <li className="py-3 text-sm text-ink-soft">
            No documents yet. Upload a brochure or price sheet and the assistant will answer questions from it.
          </li>
        )}
        {visible?.map((d) => (
          <li key={d.id} className="flex flex-wrap items-center gap-2 py-2.5 text-sm">
            <FileText size={16} className="text-ink-faint" />
            <span className="min-w-0 flex-1 truncate">{d.filename}</span>
            <Badge tone={TONE[d.status]}>{LABEL[d.status]}</Badge>
            {d.status === "failed" && (
              <button onClick={() => retry.mutate(d.id)} className="text-ink-soft hover:text-ink" aria-label={`Retry ${d.filename}`}>
                <RotateCw size={15} />
              </button>
            )}
            <button onClick={() => remove.mutate(d.id)} className="text-ink-faint hover:text-brick" aria-label={`Delete ${d.filename}`}>
              <Trash2 size={15} />
            </button>
            {d.error && <p className="w-full text-xs text-brick">{d.error}</p>}
          </li>
        ))}
      </ul>
      <input
        ref={input} type="file" multiple hidden accept=".pdf,.docx,.txt,.md"
        onChange={(e) => { if (e.target.files?.length) upload.mutate(e.target.files); e.target.value = ""; }}
      />
      <Button type="button" variant="secondary" size="sm" disabled={upload.isPending} onClick={() => input.current?.click()}>
        {upload.isPending ? "Uploading…" : "Upload PDF, Word or text"}
      </Button>
      <ErrorText error={upload.error} />
    </div>
  );
}
