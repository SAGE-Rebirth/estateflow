"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, qs } from "@/lib/api";
import { dateTime, day, KIND_LABEL, time } from "@/lib/format";
import { useMe, useTeam } from "@/lib/hooks";
import type { AppointmentKind, Contact, Page, Property, Slot } from "@/lib/types";
import { Button, ErrorText, Field, Input, Modal, Select, Textarea } from "./ui";

export function AppointmentDialog({
  open, onClose, contactId, propertyId, defaultStart,
}: {
  open: boolean; onClose: () => void; contactId?: string; propertyId?: string;
  defaultStart?: string;
}) {
  const qc = useQueryClient();
  const me = useMe();
  const team = useTeam();
  const tz = me.data?.tenant.timezone;
  const [contact, setContact] = useState(contactId ?? "");
  const [search, setSearch] = useState("");
  const [property, setProperty] = useState(propertyId ?? "");
  const [kind, setKind] = useState<AppointmentKind>("site_visit");
  const [userId, setUserId] = useState("");
  const [mode, setMode] = useState<"slot" | "custom">(defaultStart ? "custom" : "slot");
  const [slot, setSlot] = useState("");
  const [custom, setCustom] = useState(defaultStart ? defaultStart.slice(0, 16) : "");
  const [notes, setNotes] = useState("");
  const [notify, setNotify] = useState(true);

  const contacts = useQuery({
    queryKey: ["contacts", "pick", search],
    queryFn: () => api<Page<Contact>>(`/contacts${qs({ q: search, limit: 20 })}`),
    enabled: open && !contactId,
  });
  const props = useQuery({
    queryKey: ["properties", "pick"],
    queryFn: () => api<Page<Property>>("/properties?limit=200"),
    enabled: open,
  });
  const slots = useQuery({
    queryKey: ["slots", userId],
    queryFn: () => api<Slot[]>(`/availability/slots${qs({ days: 7, user_id: userId })}`),
    enabled: open && mode === "slot",
  });

  const save = useMutation({
    mutationFn: () => {
      const starts_at = mode === "slot" ? slot : new Date(custom).toISOString();
      return api("/appointments", {
        method: "POST",
        json: {
          contact_id: contact, starts_at, kind, notes: notes || null,
          property_id: property || null, user_id: userId || null,
          override_availability: mode === "custom", notify_client: notify,
        },
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["appointments"] });
      qc.invalidateQueries({ queryKey: ["today"] });
      qc.invalidateQueries({ queryKey: ["slots"] });
      onClose();
    },
  });

  // Group free slots by day so the list reads like a diary.
  const byDay = new Map<string, Slot[]>();
  for (const s of slots.data ?? []) {
    const k = day(s.starts_at, tz);
    if (!byDay.has(k)) byDay.set(k, []);
    if (!byDay.get(k)!.some((x) => x.starts_at === s.starts_at)) byDay.get(k)!.push(s);
  }
  const ready = contact && (mode === "slot" ? slot : custom);

  return (
    <Modal open={open} onClose={onClose} title="Book appointment" wide>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        {!contactId && (
          <Field label="Client">
            <Input placeholder="Search by name or phone" value={search} onChange={(e) => setSearch(e.target.value)} />
            <Select className="mt-2" required value={contact} onChange={(e) => setContact(e.target.value)}>
              <option value="">Choose a client</option>
              {contacts.data?.items.map((c) => (
                <option key={c.id} value={c.id}>{c.name ?? "Unnamed"} ({c.phone})</option>
              ))}
            </Select>
          </Field>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Type">
            <Select value={kind} onChange={(e) => setKind(e.target.value as AppointmentKind)}>
              {Object.entries(KIND_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
          </Field>
          <Field label="Property">
            <Select value={property} onChange={(e) => setProperty(e.target.value)}>
              <option value="">None</option>
              {props.data?.items.map((p) => (
                <option key={p.id} value={p.id}>{p.ref_code} {p.title}</option>
              ))}
            </Select>
          </Field>
          <Field label="With">
            <Select value={userId} onChange={(e) => setUserId(e.target.value)}>
              <option value="">{mode === "slot" ? "Whoever is free" : "Me"}</option>
              {team.data?.filter((u) => u.is_active).map((u) => (
                <option key={u.id} value={u.id}>{u.full_name}</option>
              ))}
            </Select>
          </Field>
        </div>

        <fieldset>
          <legend className="mb-2 text-sm font-medium">When</legend>
          <div className="mb-3 inline-flex rounded-md border border-rule p-0.5 text-sm">
            {(["slot", "custom"] as const).map((m) => (
              <button
                type="button" key={m} onClick={() => setMode(m)}
                className={`rounded px-3 py-1 ${mode === m ? "bg-registry text-white" : "text-ink-soft"}`}
              >
                {m === "slot" ? "Free slots" : "Any time"}
              </button>
            ))}
          </div>
          {mode === "slot" ? (
            <div className="max-h-56 space-y-3 overflow-y-auto pr-1">
              {slots.isLoading && <p className="text-sm text-ink-faint">Finding free times…</p>}
              {slots.data?.length === 0 && (
                <p className="text-sm text-ink-soft">No free slots this week. Use “Any time” or adjust availability in Settings.</p>
              )}
              {[...byDay.entries()].map(([d, list]) => (
                <div key={d}>
                  <p className="mb-1 text-xs font-medium text-ink-soft">{d}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {list.map((s) => (
                      <button
                        type="button" key={s.starts_at} onClick={() => setSlot(s.starts_at)}
                        className={`tnum rounded border px-2 py-1 text-sm ${
                          slot === s.starts_at ? "border-registry bg-registry text-white" : "border-rule hover:border-registry"
                        }`}
                      >
                        {time(s.starts_at, tz)}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <Input type="datetime-local" required value={custom} onChange={(e) => setCustom(e.target.value)} />
          )}
        </fieldset>

        <Field label="Notes"><Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} />
          Send the client a WhatsApp confirmation
        </label>
        {slot && mode === "slot" && <p className="text-sm text-ink-soft">Booking {dateTime(slot, tz)}</p>}
        <ErrorText error={save.error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={!ready || save.isPending}>
            {save.isPending ? "Booking…" : "Book appointment"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
