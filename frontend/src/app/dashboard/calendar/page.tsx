"use client";

import type { DatesSetArg, EventClickArg, EventDropArg } from "@fullcalendar/core";
import dayGridPlugin from "@fullcalendar/daygrid";
import interactionPlugin, { type DateClickArg, type EventResizeDoneArg } from "@fullcalendar/interaction";
import FullCalendar from "@fullcalendar/react";
import timeGridPlugin from "@fullcalendar/timegrid";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MapPin, Plus } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { AppointmentDialog } from "@/components/appointment-dialog";
import { OutcomeDialog } from "@/components/outcome-dialog";
import { Badge, Button, ErrorText, Modal, PageHeader, Select } from "@/components/ui";
import { api, qs } from "@/lib/api";
import { dateTime, KIND_LABEL, time } from "@/lib/format";
import { useMe, useTeam } from "@/lib/hooks";
import type { Appointment } from "@/lib/types";

const COLORS: Record<string, string> = {
  site_visit: "#1f6a50",
  call: "#4d5a56",
  office_meeting: "#8a5f0c",
  video_call: "#3b5f86",
};

export default function CalendarPage() {
  return (
    <Suspense>
      <Calendar />
    </Suspense>
  );
}

function Calendar() {
  const qc = useQueryClient();
  const params = useSearchParams();
  const me = useMe();
  const team = useTeam();
  const tz = me.data?.tenant.timezone;
  const [range, setRange] = useState<{ start: string; end: string } | null>(null);
  const [userId, setUserId] = useState("");
  const [selected, setSelected] = useState<Appointment | null>(null);
  const [newAt, setNewAt] = useState<string | undefined>();
  const [booking, setBooking] = useState(false);
  const [outcomeFor, setOutcomeFor] = useState<Appointment | null>(null);

  const appts = useQuery({
    queryKey: ["appointments", range, userId],
    queryFn: () => api<Appointment[]>(`/appointments${qs({ ...range, user_id: userId })}`),
    enabled: !!range,
  });

  // Deep link from a notification: /calendar?appointment=<id>
  const deepLink = params.get("appointment");
  const linked = useQuery({
    queryKey: ["appointments", "one", deepLink],
    queryFn: () => api<Appointment>(`/appointments/${deepLink}`),
    enabled: !!deepLink,
  });
  useEffect(() => {
    if (linked.data) setSelected(linked.data);
  }, [linked.data]);

  const move = useMutation({
    mutationFn: ({ id, starts_at, ends_at }: { id: string; starts_at: string; ends_at: string }) =>
      api(`/appointments/${id}`, { method: "PATCH", json: { starts_at, ends_at } }),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["appointments"] });
      qc.invalidateQueries({ queryKey: ["today"] });
    },
  });
  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api(`/appointments/${id}`, { method: "PATCH", json: { status } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["appointments"] });
      qc.invalidateQueries({ queryKey: ["today"] });
      setSelected(null);
    },
  });

  const onMove = (arg: EventDropArg | EventResizeDoneArg) => {
    const ev = arg.event;
    move.mutate(
      { id: ev.id, starts_at: ev.start!.toISOString(), ends_at: ev.end!.toISOString() },
      { onError: () => arg.revert() },
    );
  };

  return (
    <>
      <PageHeader
        title="Calendar"
        subtitle="Drag a meeting to reschedule it. The client gets the new time on WhatsApp."
        actions={
          <>
            <Select value={userId} onChange={(e) => setUserId(e.target.value)} className="w-48" aria-label="Team member">
              <option value="">Whole team</option>
              {team.data?.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
            </Select>
            <Button onClick={() => { setNewAt(undefined); setBooking(true); }}>
              <Plus size={16} /> Book appointment
            </Button>
          </>
        }
      />
      <ErrorText error={move.error} />
      <div className="rounded-lg border border-rule bg-paper p-3 sm:p-4">
        <FullCalendar
          plugins={[timeGridPlugin, dayGridPlugin, interactionPlugin]}
          initialView={typeof window !== "undefined" && window.innerWidth < 768 ? "timeGridDay" : "timeGridWeek"}
          headerToolbar={{ left: "prev,next today", center: "title", right: "timeGridDay,timeGridWeek,dayGridMonth" }}
          buttonText={{ today: "Today", day: "Day", week: "Week", month: "Month" }}
          slotMinTime="08:00:00"
          slotMaxTime="21:00:00"
          allDaySlot={false}
          nowIndicator
          height="auto"
          editable
          eventDurationEditable
          datesSet={(arg: DatesSetArg) => setRange({ start: arg.start.toISOString(), end: arg.end.toISOString() })}
          events={(appts.data ?? []).map((a) => ({
            id: a.id,
            title: `${a.contact_name ?? a.contact_phone}${a.property_ref ? `, ${a.property_ref}` : ""}`,
            start: a.starts_at,
            end: a.ends_at,
            backgroundColor: COLORS[a.kind],
            borderColor: COLORS[a.kind],
            classNames: a.status === "completed" || a.status === "no_show" ? ["opacity-50"] : [],
            extendedProps: a,
          }))}
          eventClick={(arg: EventClickArg) => setSelected(arg.event.extendedProps as Appointment)}
          eventDrop={onMove}
          eventResize={onMove}
          dateClick={(arg: DateClickArg) => {
            const local = new Date(arg.date.getTime() - arg.date.getTimezoneOffset() * 60000);
            setNewAt(local.toISOString());
            setBooking(true);
          }}
        />
      </div>

      <Modal open={!!selected} onClose={() => setSelected(null)} title={selected ? KIND_LABEL[selected.kind] : ""}>
        {selected && (
          <div className="space-y-3 text-sm">
            <p className="tnum text-base font-medium">
              {dateTime(selected.starts_at, tz)} until {time(selected.ends_at, tz)}
            </p>
            <p>
              <Link href={`/dashboard/contacts/${selected.contact_id}`} className="font-semibold text-registry hover:underline">
                {selected.contact_name ?? selected.contact_phone}
              </Link>{" "}
              <span className="text-ink-soft">{selected.contact_phone}</span>
            </p>
            {selected.property_title && <p>{selected.property_ref} {selected.property_title}</p>}
            {selected.location && (
              <p className="flex items-center gap-1 text-ink-soft"><MapPin size={14} /> {selected.location}</p>
            )}
            <p className="text-ink-soft">With {selected.agent_name}</p>
            {selected.notes && <p className="rounded bg-stone p-2">{selected.notes}</p>}
            {selected.outcome && <p className="rounded bg-registry-tint p-2">Outcome: {selected.outcome}</p>}
            <div className="flex flex-wrap gap-2">
              <Badge tone={selected.status === "cancelled" ? "red" : selected.status === "completed" ? "green" : "gold"}>
                {selected.status.replace("_", " ")}
              </Badge>
              {selected.created_by_bot && <Badge tone="green">Booked on WhatsApp</Badge>}
            </div>
            <div className="flex flex-wrap justify-end gap-2 border-t border-rule pt-3">
              {selected.status === "scheduled" && (
                <Button size="sm" variant="secondary" onClick={() => setStatus.mutate({ id: selected.id, status: "confirmed" })}>
                  Mark confirmed
                </Button>
              )}
              {["scheduled", "confirmed"].includes(selected.status) && (
                <>
                  <Button size="sm" variant="danger" onClick={() => setStatus.mutate({ id: selected.id, status: "cancelled" })}>
                    Cancel appointment
                  </Button>
                  <Button size="sm" onClick={() => { setOutcomeFor(selected); setSelected(null); }}>
                    Record outcome
                  </Button>
                </>
              )}
            </div>
          </div>
        )}
      </Modal>
      <AppointmentDialog key={newAt ?? "new"} open={booking} onClose={() => setBooking(false)} defaultStart={newAt} />
      <OutcomeDialog appt={outcomeFor} onClose={() => setOutcomeFor(null)} />
    </>
  );
}
