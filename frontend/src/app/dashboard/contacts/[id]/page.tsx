"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, MessageCircle, Phone } from "lucide-react";
import Link from "next/link";
import { use, useState } from "react";
import { AppointmentDialog } from "@/components/appointment-dialog";
import { Badge, Button, ErrorText, Field, Input, PageHeader, Select, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime, day, KIND_LABEL, PROPERTY_TYPES, STAGES, waLink } from "@/lib/format";
import { useMe, useTeam } from "@/lib/hooks";
import type { Activity, Appointment, Contact, LeadStage, Task } from "@/lib/types";

export default function ContactPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const qc = useQueryClient();
  const me = useMe();
  const team = useTeam();
  const tz = me.data?.tenant.timezone;
  const [booking, setBooking] = useState(false);
  const contact = useQuery({ queryKey: ["contact", id], queryFn: () => api<Contact>(`/contacts/${id}`) });
  const activities = useQuery({ queryKey: ["contact", id, "activities"], queryFn: () => api<Activity[]>(`/contacts/${id}/activities`) });
  const interests = useQuery({
    queryKey: ["contact", id, "interests"],
    queryFn: () => api<{ property_id: string; ref_code: string; title: string }[]>(`/contacts/${id}/interests`),
  });
  const appts = useQuery({
    queryKey: ["appointments", "contact", id],
    queryFn: () => api<Appointment[]>(`/appointments?contact_id=${id}&start=2000-01-01T00:00:00Z&end=2100-01-01T00:00:00Z&include_cancelled=true`),
  });
  const tasks = useQuery({ queryKey: ["tasks", id], queryFn: () => api<Task[]>(`/tasks?contact_id=${id}`) });

  const update = useMutation({
    mutationFn: (body: Partial<Contact>) => api<Contact>(`/contacts/${id}`, { method: "PATCH", json: body }),
    onSuccess: (c) => {
      qc.setQueryData(["contact", id], c);
      qc.invalidateQueries({ queryKey: ["contact", id, "activities"] });
      qc.invalidateQueries({ queryKey: ["contacts"] });
    },
  });

  const c = contact.data;
  if (!c) return <p className="text-ink-faint">Loading…</p>;

  return (
    <>
      <PageHeader
        title={c.name ?? c.phone}
        subtitle={<span className="tnum">{c.phone}{c.email ? `, ${c.email}` : ""}</span>}
        actions={
          <>
            <a href={`tel:${c.phone}`}><Button variant="secondary"><Phone size={16} /> Call</Button></a>
            <a href={waLink(c.phone)} target="_blank" rel="noreferrer">
              <Button variant="secondary"><MessageCircle size={16} /> WhatsApp</Button>
            </a>
            <Button onClick={() => setBooking(true)}><CalendarPlus size={16} /> Book appointment</Button>
          </>
        }
      />
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-10">
          <div className="flex flex-wrap gap-4">
            <Field label="Stage" className="w-48">
              <Select value={c.stage} onChange={(e) => update.mutate({ stage: e.target.value as LeadStage })}>
                {STAGES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </Select>
            </Field>
            <Field label="Owner" className="w-48">
              <Select value={c.assigned_to ?? ""} onChange={(e) => update.mutate({ assigned_to: e.target.value || null })}>
                <option value="">Unassigned</option>
                {team.data?.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
              </Select>
            </Field>
          </div>

          <Tasks contactId={id} tasks={tasks.data} tz={tz} />

          <section>
            <h2 className="mb-3 text-lg font-semibold">Appointments</h2>
            {appts.data?.length === 0 && <p className="text-sm text-ink-soft">None yet.</p>}
            <ul className="divide-y divide-rule border-y border-rule">
              {appts.data?.map((a) => (
                <li key={a.id} className="flex flex-wrap items-baseline gap-3 py-2.5 text-sm">
                  <span className="tnum w-40 text-ink-soft">{dateTime(a.starts_at, tz)}</span>
                  <span className="font-medium">{KIND_LABEL[a.kind]}</span>
                  {a.property_ref && <span>{a.property_ref}</span>}
                  <Badge tone={a.status === "cancelled" ? "red" : a.status === "completed" ? "green" : "neutral"}>
                    {a.status.replace("_", " ")}
                  </Badge>
                  {a.outcome && <span className="w-full text-ink-soft">{a.outcome}</span>}
                </li>
              ))}
            </ul>
          </section>

          <Timeline contactId={id} activities={activities.data} tz={tz} />
        </div>

        <aside className="space-y-8">
          <Preferences contact={c} onSave={(b) => update.mutate(b)} saving={update.isPending} error={update.error} />
          <section>
            <h2 className="mb-2 font-semibold">Interested in</h2>
            {interests.data?.length === 0 && <p className="text-sm text-ink-soft">No listings yet.</p>}
            <ul className="space-y-1 text-sm">
              {interests.data?.map((i) => (
                <li key={i.property_id}>
                  <Link href={`/dashboard/properties/${i.property_id}`} className="hover:underline">
                    <span className="font-medium text-registry">{i.ref_code}</span> {i.title}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>
      <AppointmentDialog open={booking} onClose={() => setBooking(false)} contactId={id}
        propertyId={interests.data?.[0]?.property_id} />
    </>
  );
}

function Preferences({
  contact: c, onSave, saving, error,
}: { contact: Contact; onSave: (b: Partial<Contact>) => void; saving: boolean; error: unknown }) {
  return (
    <section>
      <h2 className="mb-1 font-semibold">Looking for</h2>
      <p className="mb-3 text-xs text-ink-faint">The WhatsApp assistant fills these in as the client chats.</p>
      <form
        key={c.id + c.budget_max + c.bedrooms}
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          const num = (k: string) => (f.get(k) ? Number(f.get(k)) : null);
          onSave({
            name: (f.get("name") as string) || null,
            budget_min: num("budget_min"), budget_max: num("budget_max"),
            bedrooms: f.get("bedrooms") ? Number(f.get("bedrooms")) : null,
            preferred_property_type: (f.get("ptype") as Contact["preferred_property_type"]) || null,
            preferred_locations: String(f.get("locations") ?? "").split(",").map((s) => s.trim()).filter(Boolean),
            notes: (f.get("notes") as string) || null,
          });
        }}
      >
        <Field label="Name"><Input name="name" defaultValue={c.name ?? ""} /></Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Budget from"><Input name="budget_min" type="number" defaultValue={c.budget_min ?? ""} /></Field>
          <Field label="Budget to"><Input name="budget_max" type="number" defaultValue={c.budget_max ?? ""} /></Field>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Bedrooms"><Input name="bedrooms" type="number" min={0} defaultValue={c.bedrooms ?? ""} /></Field>
          <Field label="Type">
            <Select name="ptype" defaultValue={c.preferred_property_type ?? ""}>
              <option value="">Any</option>
              {PROPERTY_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </Select>
          </Field>
        </div>
        <Field label="Areas" hint="Comma separated"><Input name="locations" defaultValue={c.preferred_locations.join(", ")} /></Field>
        <Field label="Notes"><Textarea name="notes" rows={4} defaultValue={c.notes ?? ""} /></Field>
        <ErrorText error={error} />
        <Button type="submit" variant="secondary" disabled={saving}>Save preferences</Button>
      </form>
    </section>
  );
}

function Tasks({ contactId, tasks, tz }: { contactId: string; tasks?: Task[]; tz?: string }) {
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["tasks", contactId] });
    qc.invalidateQueries({ queryKey: ["today"] });
  };
  const add = useMutation({
    mutationFn: () => api("/tasks", { method: "POST", json: { title, due_at: new Date(due).toISOString(), contact_id: contactId } }),
    onSuccess: () => { setTitle(""); setDue(""); refresh(); },
  });
  const done = useMutation({
    mutationFn: (id: string) => api(`/tasks/${id}`, { method: "PATCH", json: { done: true } }),
    onSuccess: refresh,
  });
  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold">Follow-ups</h2>
      <ul className="mb-3 space-y-2">
        {tasks?.map((t) => {
          const overdue = new Date(t.due_at) < new Date();
          return (
            <li key={t.id} className="flex items-start gap-2 text-sm">
              <button onClick={() => done.mutate(t.id)} aria-label={`Mark "${t.title}" done`}
                className="mt-0.5 h-4 w-4 shrink-0 rounded border border-ink-faint hover:bg-registry-tint" />
              <span className="flex-1">{t.title}</span>
              <span className={`tnum text-xs ${overdue ? "text-brick" : "text-ink-faint"}`}>{day(t.due_at, tz)}</span>
            </li>
          );
        })}
      </ul>
      <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <Input placeholder="Send updated price sheet" value={title} onChange={(e) => setTitle(e.target.value)} required className="min-w-48 flex-1" />
        <Input type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} required className="w-auto" aria-label="Due" />
        <Button type="submit" variant="secondary" disabled={add.isPending}>Add follow-up</Button>
      </form>
    </section>
  );
}

function Timeline({ contactId, activities, tz }: { contactId: string; activities?: Activity[]; tz?: string }) {
  const qc = useQueryClient();
  const [note, setNote] = useState("");
  const add = useMutation({
    mutationFn: () => api(`/contacts/${contactId}/activities`, { method: "POST", json: { summary: note } }),
    onSuccess: () => { setNote(""); qc.invalidateQueries({ queryKey: ["contact", contactId, "activities"] }); },
  });
  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold">History</h2>
      <form className="mb-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <Input placeholder="Add a note about a call or meeting" value={note} onChange={(e) => setNote(e.target.value)} required className="flex-1" />
        <Button type="submit" variant="secondary" disabled={add.isPending}>Add note</Button>
      </form>
      <ol className="space-y-4 border-l-2 border-rule pl-4">
        {activities?.map((a) => (
          <li key={a.id} className="text-sm">
            <p>{a.summary}</p>
            <p className="tnum text-xs text-ink-faint">{dateTime(a.created_at, tz)}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
