"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, MapPin, MessageCircle, Phone, Plus } from "lucide-react";
import Link from "next/link";
import { Fragment, useState } from "react";
import { AppointmentDialog } from "@/components/appointment-dialog";
import { OutcomeDialog } from "@/components/outcome-dialog";
import { Badge, Button, Empty } from "@/components/ui";
import { api } from "@/lib/api";
import { ago, day, KIND_LABEL, time, waLink } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import type { Appointment, Task, Today } from "@/lib/types";

function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

export default function TodayPage() {
  const me = useMe();
  const tz = me.data?.tenant.timezone;
  const [mine, setMine] = useState(false);
  const [booking, setBooking] = useState(false);
  const [outcomeFor, setOutcomeFor] = useState<Appointment | null>(null);
  const today = useQuery({
    queryKey: ["today", mine],
    queryFn: () => api<Today>(`/dashboard/today?mine=${mine}`),
    refetchInterval: 60_000,
  });
  const d = today.data;
  const now = Date.now();

  const summary: string[] = [];
  if (d) {
    summary.push(plural(d.appointments_today.length, "meeting"));
    if (d.tasks_overdue.length) summary.push(`${plural(d.tasks_overdue.length, "follow-up")} overdue`);
    if (d.tasks_due_today.length) summary.push(`${plural(d.tasks_due_today.length, "follow-up")} due`);
    if (d.conversations_needing_human)
      summary.push(`${plural(d.conversations_needing_human, "chat")} waiting for you`);
  }
  const firstUpcoming = d?.appointments_today.findIndex((a) => new Date(a.ends_at).getTime() > now) ?? -1;

  return (
    <>
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold sm:text-4xl">
            Good {greeting(tz)}, {me.data?.user.full_name.split(" ")[0]}
          </h1>
          <p className="mt-2 text-ink-soft">{d ? summary.join(", ") + "." : "Loading your day…"}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setMine((m) => !m)} aria-pressed={mine}>
            {mine ? "Showing mine" : "Showing whole team"}
          </Button>
          <Button onClick={() => setBooking(true)}><Plus size={16} /> Book appointment</Button>
        </div>
      </div>

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <section aria-labelledby="sheet">
          <h2 id="sheet" className="mb-4 text-lg font-semibold">Day sheet</h2>
          {d && d.appointments_today.length === 0 && (
            <Empty action={<Button size="sm" onClick={() => setBooking(true)}>Book appointment</Button>}>
              No meetings today. Visits the WhatsApp assistant books will appear here.
            </Empty>
          )}
          <ol className="relative">
            {d?.appointments_today.map((a, i) => (
              <Fragment key={a.id}>
                {i === firstUpcoming && i > 0 && <NowLine />}
                <DayEntry appt={a} tz={tz} past={new Date(a.ends_at).getTime() < now} onOutcome={() => setOutcomeFor(a)} />
              </Fragment>
            ))}
            {d && firstUpcoming === -1 && d.appointments_today.length > 0 && <NowLine />}
          </ol>

          {d && d.appointments_upcoming.length > 0 && (
            <div className="mt-10">
              <h2 className="mb-3 text-lg font-semibold">Next few days</h2>
              <ul className="divide-y divide-rule border-y border-rule">
                {d.appointments_upcoming.map((a) => (
                  <li key={a.id} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 py-3 text-sm">
                    <span className="tnum w-36 shrink-0 text-ink-soft">{day(a.starts_at, tz)}, {time(a.starts_at, tz)}</span>
                    <Link href={`/dashboard/contacts/${a.contact_id}`} className="font-medium hover:underline">
                      {a.contact_name ?? a.contact_phone}
                    </Link>
                    <span className="text-ink-soft">{KIND_LABEL[a.kind]}{a.property_ref ? ` at ${a.property_ref}` : ""}</span>
                    <span className="ml-auto text-ink-faint">{a.agent_name}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {d && d.awaiting_outcome.length > 0 && (
            <div className="mt-10">
              <h2 className="text-lg font-semibold">How did these go?</h2>
              <p className="mb-3 text-sm text-ink-soft">Record the outcome so the lead moves forward.</p>
              <ul className="divide-y divide-rule border-y border-rule">
                {d.awaiting_outcome.map((a) => (
                  <li key={a.id} className="flex flex-wrap items-center gap-3 py-3 text-sm">
                    <span className="tnum text-ink-soft">{day(a.starts_at, tz)}</span>
                    <span className="font-medium">{a.contact_name ?? a.contact_phone}</span>
                    <span className="text-ink-soft">{KIND_LABEL[a.kind]}</span>
                    <Button size="sm" variant="secondary" className="ml-auto" onClick={() => setOutcomeFor(a)}>
                      Record outcome
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <aside className="space-y-8">
          <TaskList title="Overdue" tasks={d?.tasks_overdue} tz={tz} overdue />
          <TaskList title="Follow-ups due today" tasks={d?.tasks_due_today} tz={tz} />
          <section>
            <h2 className="mb-2 font-semibold">WhatsApp</h2>
            {d && d.conversations_needing_human > 0 ? (
              <Link href="/dashboard/inbox?mode=human" className="block rounded-md bg-marigold-tint px-3 py-2.5 text-sm hover:underline">
                {plural(d.conversations_needing_human, "conversation")} handed over by the assistant need a reply.
              </Link>
            ) : (
              <p className="text-sm text-ink-soft">The assistant is handling every open chat.</p>
            )}
          </section>
          <section>
            <h2 className="mb-2 font-semibold">New leads</h2>
            {d?.new_leads.length === 0 && <p className="text-sm text-ink-soft">No new leads in the last two days.</p>}
            <ul className="space-y-2">
              {d?.new_leads.map((c) => (
                <li key={c.id} className="flex items-baseline justify-between gap-2 text-sm">
                  <Link href={`/dashboard/contacts/${c.id}`} className="font-medium hover:underline">{c.name ?? c.phone}</Link>
                  <span className="text-ink-faint">{ago(c.created_at)}</span>
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>

      <AppointmentDialog open={booking} onClose={() => setBooking(false)} />
      <OutcomeDialog appt={outcomeFor} onClose={() => setOutcomeFor(null)} />
    </>
  );
}

function greeting(tz?: string) {
  const h = Number(new Date().toLocaleString("en-GB", { hour: "2-digit", hour12: false, timeZone: tz }));
  return h < 12 ? "morning" : h < 17 ? "afternoon" : "evening";
}

function NowLine() {
  return (
    <li aria-hidden className="relative my-2 flex items-center gap-3 pl-[6.25rem] sm:pl-[9.25rem]">
      <span className="h-2.5 w-2.5 rounded-full bg-marigold" />
      <span className="h-px flex-1 bg-marigold" />
      <span className="text-xs font-medium text-[#8a5f0c]">Now</span>
    </li>
  );
}

function DayEntry({
  appt: a, tz, past, onOutcome,
}: { appt: Appointment; tz?: string; past: boolean; onOutcome: () => void }) {
  const [hm, ampm] = time(a.starts_at, tz).split(" ");
  return (
    <li className={`grid grid-cols-[5.5rem_minmax(0,1fr)] gap-3 border-t border-rule py-5 sm:grid-cols-[8.5rem_minmax(0,1fr)] ${past ? "opacity-60" : ""}`}>
      <div className="tnum font-[family-name:var(--font-display)] leading-none">
        <span className="text-3xl font-semibold sm:text-4xl">{hm}</span>
        <span className="ml-1 text-sm text-ink-soft">{ampm}</span>
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-ink-soft">{KIND_LABEL[a.kind]} until {time(a.ends_at, tz)}</span>
          {a.created_by_bot && <Badge tone="green">Booked on WhatsApp</Badge>}
          {a.status === "confirmed" && <Badge tone="gold">Confirmed</Badge>}
        </div>
        <Link href={`/dashboard/contacts/${a.contact_id}`} className="mt-1 block text-lg font-semibold hover:underline">
          {a.contact_name ?? a.contact_phone}
        </Link>
        {a.property_title && (
          <p className="text-sm">
            <span className="font-medium text-registry">{a.property_ref}</span> {a.property_title}
          </p>
        )}
        {a.location && (
          <a
            href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(a.location)}`}
            target="_blank" rel="noreferrer"
            className="mt-1 inline-flex items-center gap-1 text-sm text-ink-soft hover:text-ink hover:underline"
          >
            <MapPin size={14} /> {a.location}
          </a>
        )}
        {a.notes && <p className="mt-1 text-sm text-ink-soft">{a.notes}</p>}
        <div className="mt-3 flex flex-wrap gap-2">
          <a href={`tel:${a.contact_phone}`}><Button size="sm" variant="secondary"><Phone size={14} /> Call</Button></a>
          <a href={waLink(a.contact_phone)} target="_blank" rel="noreferrer">
            <Button size="sm" variant="secondary"><MessageCircle size={14} /> WhatsApp</Button>
          </a>
          <Button size="sm" variant="ghost" onClick={onOutcome}><Check size={14} /> Record outcome</Button>
          <span className="ml-auto self-center text-xs text-ink-faint">with {a.agent_name}</span>
        </div>
      </div>
    </li>
  );
}

function TaskList({
  title, tasks, tz, overdue = false,
}: { title: string; tasks?: Task[]; tz?: string; overdue?: boolean }) {
  const qc = useQueryClient();
  const done = useMutation({
    mutationFn: (id: string) => api(`/tasks/${id}`, { method: "PATCH", json: { done: true } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["today"] }),
  });
  if (!tasks || (overdue && tasks.length === 0)) return null;
  return (
    <section>
      <h2 className={`mb-2 font-semibold ${overdue ? "text-brick" : ""}`}>{title}</h2>
      {tasks.length === 0 ? (
        <p className="text-sm text-ink-soft">Nothing due. Add follow-ups from a lead&apos;s page.</p>
      ) : (
        <ul className="space-y-2">
          {tasks.map((t) => (
            <li key={t.id} className="flex items-start gap-2 text-sm">
              <button
                onClick={() => done.mutate(t.id)}
                aria-label={`Mark "${t.title}" done`}
                className="mt-0.5 h-4 w-4 shrink-0 rounded border border-ink-faint hover:border-registry hover:bg-registry-tint"
              />
              <div className="min-w-0">
                {t.contact_id ? (
                  <Link href={`/dashboard/contacts/${t.contact_id}`} className="hover:underline">{t.title}</Link>
                ) : (
                  t.title
                )}
                <p className={`tnum text-xs ${overdue ? "text-brick" : "text-ink-faint"}`}>
                  {overdue ? `Was due ${day(t.due_at, tz)}` : time(t.due_at, tz)}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
