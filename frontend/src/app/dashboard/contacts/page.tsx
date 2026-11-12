"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button, ErrorText, Field, Input, Modal, PageHeader, Select } from "@/components/ui";
import { FormAssist } from "@/components/form-assist";
import { api, qs } from "@/lib/api";
import { ago, price, STAGES, stageLabel } from "@/lib/format";
import { useMe, useTeam } from "@/lib/hooks";
import type { Contact, LeadStage, Page } from "@/lib/types";

export default function ContactsPage() {
  const qc = useQueryClient();
  const me = useMe();
  const team = useTeam();
  const [view, setView] = useState<"board" | "list">("board");
  const [q, setQ] = useState("");
  const [mine, setMine] = useState(false);
  const [adding, setAdding] = useState(false);
  const contacts = useQuery({
    queryKey: ["contacts", q, mine],
    queryFn: () => api<Page<Contact>>(`/contacts${qs({ q, mine, limit: 500 })}`),
  });
  const setStage = useMutation({
    mutationFn: ({ id, stage }: { id: string; stage: LeadStage }) =>
      api(`/contacts/${id}`, { method: "PATCH", json: { stage } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["contacts"] }),
  });
  const owner = (id: string | null) => team.data?.find((u) => u.id === id)?.full_name;
  const currency = me.data?.tenant.currency;
  const items = contacts.data?.items ?? [];

  return (
    <>
      <PageHeader
        title="Leads"
        subtitle={contacts.data ? `${contacts.data.total} people` : undefined}
        actions={<Button onClick={() => setAdding(true)}><Plus size={16} /> Add lead</Button>}
      />
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <Input placeholder="Search name, phone or email" value={q} onChange={(e) => setQ(e.target.value)} className="w-full max-w-xs" />
        <Button variant="secondary" onClick={() => setMine((m) => !m)} aria-pressed={mine}>
          {mine ? "Assigned to me" : "Everyone's leads"}
        </Button>
        <div className="ml-auto inline-flex rounded-md border border-rule bg-paper p-0.5 text-sm">
          {(["board", "list"] as const).map((v) => (
            <button key={v} onClick={() => setView(v)}
              className={`rounded px-3 py-1.5 ${view === v ? "bg-registry text-white" : "text-ink-soft"}`}>
              {v === "board" ? "Pipeline" : "List"}
            </button>
          ))}
        </div>
      </div>

      {view === "board" ? (
        <div className="-mx-4 overflow-x-auto px-4 pb-4 sm:-mx-6 sm:px-6">
          <div className="flex min-w-max gap-4">
            {STAGES.map((s) => {
              const col = items.filter((c) => c.stage === s.value);
              return (
                <section key={s.value} className="w-64 shrink-0" aria-label={s.label}>
                  <h2 className="mb-2 flex items-baseline justify-between border-b-2 border-ink pb-1 text-sm font-semibold">
                    {s.label} <span className="tnum font-normal text-ink-faint">{col.length}</span>
                  </h2>
                  <ul className="space-y-2">
                    {col.map((c) => (
                      <li key={c.id} className="rounded-md border border-rule bg-paper p-3 text-sm">
                        <Link href={`/dashboard/contacts/${c.id}`} className="font-medium hover:underline">{c.name ?? c.phone}</Link>
                        <p className="text-ink-soft">
                          {[c.bedrooms && `${c.bedrooms} BHK`, c.budget_max && `up to ${price(c.budget_max, currency)}`, c.preferred_locations[0]]
                            .filter(Boolean).join(", ") || "Preferences not known yet"}
                        </p>
                        <div className="mt-2 flex items-center justify-between gap-2">
                          <span className="text-xs text-ink-faint">{owner(c.assigned_to) ?? "Unassigned"}</span>
                          <select
                            aria-label="Move to stage" value={c.stage}
                            onChange={(e) => setStage.mutate({ id: c.id, stage: e.target.value as LeadStage })}
                            className="rounded border border-rule bg-paper px-1 py-0.5 text-xs"
                          >
                            {STAGES.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
                          </select>
                        </div>
                      </li>
                    ))}
                  </ul>
                </section>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-rule bg-paper">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-rule text-ink-soft">
              <tr>
                <th className="px-4 py-2.5 font-medium">Name</th>
                <th className="px-4 py-2.5 font-medium">Phone</th>
                <th className="px-4 py-2.5 font-medium">Stage</th>
                <th className="px-4 py-2.5 font-medium">Budget</th>
                <th className="px-4 py-2.5 font-medium">Owner</th>
                <th className="px-4 py-2.5 font-medium">Last message</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {items.map((c) => (
                <tr key={c.id} className="hover:bg-stone">
                  <td className="px-4 py-2.5"><Link href={`/dashboard/contacts/${c.id}`} className="font-medium hover:underline">{c.name ?? "Unnamed"}</Link></td>
                  <td className="tnum px-4 py-2.5">{c.phone}</td>
                  <td className="px-4 py-2.5">{stageLabel(c.stage)}</td>
                  <td className="px-4 py-2.5">{c.budget_max ? price(c.budget_max, currency) : ""}</td>
                  <td className="px-4 py-2.5">{owner(c.assigned_to) ?? ""}</td>
                  <td className="px-4 py-2.5 text-ink-faint">{ago(c.last_inbound_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {items.length === 0 && <p className="p-4 text-sm text-ink-soft">No leads match. People who message your WhatsApp number appear here automatically.</p>}
        </div>
      )}
      <AddContact open={adding} onClose={() => setAdding(false)} />
    </>
  );
}

function AddContact({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api<Contact>("/contacts", { method: "POST", json: body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["contacts"] });
      onClose();
    },
  });
  return (
    <Modal open={open} onClose={onClose} title="Add lead">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          save.mutate({
            name: f.get("name") || null, phone: f.get("phone"), email: f.get("email") || null,
            source: f.get("source"),
          });
        }}
      >
        <FormAssist paste="contact" />
        <Field label="Name"><Input name="name" /></Field>
        <Field label="Phone" hint="With country code, or a 10-digit Indian number"><Input name="phone" required /></Field>
        <Field label="Email"><Input name="email" type="email" /></Field>
        <Field label="Came from">
          <Select name="source" defaultValue="walk_in">
            <option value="walk_in">Walk-in</option>
            <option value="referral">Referral</option>
            <option value="website">Website</option>
            <option value="whatsapp">WhatsApp</option>
            <option value="other">Other</option>
          </Select>
        </Field>
        <ErrorText error={save.error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={save.isPending}>Add lead</Button>
        </div>
      </form>
    </Modal>
  );
}
