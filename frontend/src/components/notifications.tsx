"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { ago } from "@/lib/format";
import type { Notification } from "@/lib/types";

export function NotificationBell() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const count = useQuery({
    queryKey: ["notifications", "count"],
    queryFn: () => api<{ count: number }>("/notifications/unread-count"),
    refetchInterval: 30_000,
  });
  const list = useQuery({
    queryKey: ["notifications", "list"],
    queryFn: () => api<Notification[]>("/notifications?limit=30"),
    enabled: open,
  });
  const markRead = useMutation({
    mutationFn: (ids?: string[]) =>
      api<void>(`/notifications/read${ids ? "?" + ids.map((i) => `ids=${i}`).join("&") : ""}`, {
        method: "POST",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const unread = count.data?.count ?? 0;
  return (
    <div className="relative" ref={box}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative rounded-md p-2 text-ink-soft hover:bg-registry-tint hover:text-ink"
        aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
        aria-expanded={open}
      >
        <Bell size={20} />
        {unread > 0 && (
          <span className="tnum absolute -right-0.5 -top-0.5 min-w-5 rounded-full bg-brick px-1 text-center text-[11px] font-semibold leading-5 text-white">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-30 mt-2 w-[min(24rem,calc(100vw-2rem))] overflow-hidden rounded-lg border border-rule bg-paper shadow-lg">
          <div className="flex items-center justify-between border-b border-rule px-4 py-3">
            <span className="font-semibold">Notifications</span>
            {unread > 0 && (
              <button className="text-sm text-registry hover:underline" onClick={() => markRead.mutate(undefined)}>
                Mark all read
              </button>
            )}
          </div>
          <ul className="max-h-[60vh] overflow-y-auto">
            {list.data?.length === 0 && (
              <li className="px-4 py-6 text-sm text-ink-soft">Nothing yet. New leads, bookings and handovers show up here.</li>
            )}
            {list.data?.map((n) => (
              <li key={n.id} className="border-b border-rule last:border-0">
                <Link
                  href={n.link ?? "/dashboard"}
                  onClick={() => {
                    if (!n.read_at) markRead.mutate([n.id]);
                    setOpen(false);
                  }}
                  className={`block px-4 py-3 hover:bg-stone ${n.read_at ? "" : "bg-marigold-tint/50"}`}
                >
                  <p className="text-sm font-medium">{n.title}</p>
                  {n.body && <p className="mt-0.5 text-sm text-ink-soft">{n.body}</p>}
                  <p className="mt-1 text-xs text-ink-faint">{ago(n.created_at)}</p>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
