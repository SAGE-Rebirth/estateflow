"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, ChevronLeft, UserRound } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, mediaUrl, qs } from "@/lib/api";
import { ago, time } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import type { ChatMessage, ConversationItem } from "@/lib/types";
import { Button, ErrorText, Textarea } from "./ui";
import { FormAssist } from "./form-assist";

const FILTERS = [
  { key: "", label: "All open" },
  { key: "human", label: "Handed to team" },
  { key: "unread", label: "Unread" },
];

export function InboxView({ selectedId }: { selectedId?: string }) {
  const params = useSearchParams();
  const [filter, setFilter] = useState(params.get("mode") ?? "");
  const convs = useQuery({
    queryKey: ["conversations", filter],
    queryFn: () =>
      api<ConversationItem[]>(
        `/conversations${qs({ mode: filter === "human" ? "human" : undefined, unread: filter === "unread" || undefined })}`,
      ),
    refetchInterval: 10_000,
  });
  const selected = convs.data?.find((c) => c.id === selectedId);

  return (
    <div className="-my-6 grid h-[calc(100vh-3.5rem)] grid-cols-1 overflow-hidden border-rule sm:-my-8 md:grid-cols-[20rem_minmax(0,1fr)] md:border-x">
      <section className={`flex min-h-0 flex-col border-rule bg-paper md:border-r ${selectedId ? "hidden md:flex" : "flex"}`}>
        <div className="border-b border-rule p-3">
          <h1 className="mb-2 px-1 text-xl font-semibold">WhatsApp</h1>
          <div className="flex gap-1 text-sm">
            {FILTERS.map((f) => (
              <button key={f.key} onClick={() => setFilter(f.key)}
                className={`rounded px-2 py-1 ${filter === f.key ? "bg-registry text-white" : "text-ink-soft hover:bg-registry-tint"}`}>
                {f.label}
              </button>
            ))}
          </div>
        </div>
        <ul className="flex-1 overflow-y-auto">
          {convs.data?.length === 0 && (
            <li className="p-4 text-sm text-ink-soft">No conversations here. Chats start when someone messages your WhatsApp number.</li>
          )}
          {convs.data?.map((c) => (
            <li key={c.id}>
              <Link
                href={`/dashboard/inbox/${c.id}`}
                className={`block border-b border-rule px-4 py-3 hover:bg-stone ${c.id === selectedId ? "bg-registry-tint" : ""}`}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate font-medium">{c.contact_name ?? c.contact_phone}</span>
                  <span className="shrink-0 text-xs text-ink-faint">{ago(c.last_message_at)}</span>
                </div>
                <div className="mt-0.5 flex items-center gap-2">
                  {c.mode === "human" ? (
                    <UserRound size={14} className="shrink-0 text-marigold" aria-label="Team is replying" />
                  ) : (
                    <Bot size={14} className="shrink-0 text-registry" aria-label="Assistant is replying" />
                  )}
                  <span className="truncate text-sm text-ink-soft">{c.last_message}</span>
                  {c.unread_count > 0 && (
                    <span className="tnum ml-auto rounded-full bg-registry px-1.5 text-xs font-semibold text-white">{c.unread_count}</span>
                  )}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </section>
      {selectedId ? (
        <Thread id={selectedId} conv={selected} />
      ) : (
        <div className="hidden place-items-center text-sm text-ink-faint md:grid">Choose a conversation</div>
      )}
    </div>
  );
}

function Thread({ id, conv }: { id: string; conv?: ConversationItem }) {
  const qc = useQueryClient();
  const me = useMe();
  const tz = me.data?.tenant.timezone;
  const [body, setBody] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const messages = useQuery({
    queryKey: ["messages", id],
    queryFn: () => api<ChatMessage[]>(`/conversations/${id}/messages`),
    refetchInterval: 5_000,
  });
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages.data?.length]);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["messages", id] });
    qc.invalidateQueries({ queryKey: ["conversations"] });
  };
  const send = useMutation({
    mutationFn: () => api(`/conversations/${id}/messages`, { method: "POST", json: { body } }),
    onSuccess: () => { setBody(""); refresh(); },
  });
  const setMode = useMutation({
    mutationFn: (mode: "bot" | "human") => api(`/conversations/${id}`, { method: "PATCH", json: { mode } }),
    onSuccess: refresh,
  });
  const human = conv?.mode === "human";

  return (
    <section className="flex min-h-0 flex-col bg-stone">
      <header className="flex flex-wrap items-center gap-3 border-b border-rule bg-paper px-4 py-3">
        <Link href="/dashboard/inbox" className="md:hidden" aria-label="Back to conversations"><ChevronLeft size={20} /></Link>
        <div className="min-w-0">
          <Link href={conv ? `/dashboard/contacts/${conv.contact_id}` : "#"} className="font-semibold hover:underline">
            {conv?.contact_name ?? conv?.contact_phone ?? "Conversation"}
          </Link>
          <p className="text-xs text-ink-soft">
            {human ? "Your team is replying. The assistant is paused." : "The assistant is replying automatically."}
          </p>
        </div>
        <Button size="sm" variant="secondary" className="ml-auto" disabled={!conv || setMode.isPending}
          onClick={() => setMode.mutate(human ? "bot" : "human")}>
          {human ? "Hand back to assistant" : "Take over"}
        </Button>
      </header>
      <div className="flex-1 space-y-2 overflow-y-auto px-4 py-4">
        {messages.data?.map((m) => {
          const mine = m.direction === "outbound";
          return (
            <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[85%] rounded-lg px-3 py-2 text-sm sm:max-w-[70%] ${
                mine ? (m.sender_type === "bot" ? "bg-registry-tint" : "bg-registry text-white") : "border border-rule bg-paper"
              }`}>
                {m.media_kind && <MessageMedia conversationId={id} message={m} />}
                <p className="whitespace-pre-wrap break-words">{m.body}</p>
                <p className={`mt-1 text-right text-[11px] ${mine && m.sender_type !== "bot" ? "text-white/70" : "text-ink-faint"}`}>
                  {m.sender_type === "bot" && "Assistant, "}
                  {m.sender_type === "system" && "Automatic, "}
                  {time(m.created_at, tz)}
                  {mine && m.status === "failed" && <span className="text-brick"> not delivered</span>}
                  {mine && m.status === "read" && " read"}
                </p>
              </div>
            </div>
          );
        })}
        <div ref={end} />
      </div>
      <form
        className="border-t border-rule bg-paper p-3"
        onSubmit={(e) => { e.preventDefault(); if (body.trim()) send.mutate(); }}
      >
        <div className="flex items-end gap-2">
          <Textarea
            rows={2} className="flex-1" value={body} onChange={(e) => setBody(e.target.value)}
            placeholder={human ? "Write a reply" : "Replying takes over from the assistant"}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (body.trim()) send.mutate(); }
            }}
          />
          <FormAssist compact />
          <Button type="submit" disabled={!body.trim() || send.isPending}>Send</Button>
        </div>
        <ErrorText error={send.error} />
      </form>
    </section>
  );
}

/** Buyers' photos, voice notes and files, served privately by the API (session cookie). */
function MessageMedia({ conversationId, message: m }: { conversationId: string; message: ChatMessage }) {
  const src = mediaUrl(conversationId, m.id);
  if (m.media_kind === "image" || m.media_kind === "sticker") {
    return (
      <a href={src} target="_blank" rel="noreferrer" className="mb-1 block">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt="Photo from the client" className="max-h-64 rounded-md object-cover" />
      </a>
    );
  }
  if (m.media_kind === "audio") {
    return <audio controls src={src} className="mb-1 w-64 max-w-full" />;
  }
  return (
    <a href={src} target="_blank" rel="noreferrer" className="mb-1 inline-block text-sm underline">
      Open {m.media_kind === "video" ? "video" : "file"}
    </a>
  );
}
