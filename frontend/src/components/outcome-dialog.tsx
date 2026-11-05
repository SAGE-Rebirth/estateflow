"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import type { Appointment, AppointmentStatus } from "@/lib/types";
import { Button, Modal, Textarea } from "./ui";

export function OutcomeDialog({ appt, onClose }: { appt: Appointment | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [outcome, setOutcome] = useState("");
  const save = useMutation({
    mutationFn: (status: AppointmentStatus) =>
      api(`/appointments/${appt!.id}`, { method: "PATCH", json: { status, outcome: outcome || null } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["today"] });
      qc.invalidateQueries({ queryKey: ["appointments"] });
      setOutcome("");
      onClose();
    },
  });
  return (
    <Modal open={!!appt} onClose={onClose} title={`How did it go with ${appt?.contact_name ?? "the client"}?`}>
      <Textarea
        rows={3} className="w-full" placeholder="Liked the layout, wants to bring family on Sunday…"
        value={outcome} onChange={(e) => setOutcome(e.target.value)}
      />
      <div className="mt-4 flex flex-wrap justify-end gap-2">
        <Button variant="danger" onClick={() => save.mutate("cancelled")}>Cancelled</Button>
        <Button variant="secondary" onClick={() => save.mutate("no_show")}>No-show</Button>
        <Button onClick={() => save.mutate("completed")}>Completed</Button>
      </div>
    </Modal>
  );
}
