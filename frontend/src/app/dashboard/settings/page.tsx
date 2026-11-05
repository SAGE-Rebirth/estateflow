"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Documents } from "@/components/documents";
import { Badge, Button, ErrorText, Field, Input, Modal, PageHeader, Select, Textarea } from "@/components/ui";
import { api, API_URL, qs, signOut } from "@/lib/api";
import { day } from "@/lib/format";
import { useMe, useTeam } from "@/lib/hooks";
import type { AvailabilityRule, Role, Tenant, User } from "@/lib/types";

const TABS = [
  { key: "availability", label: "Availability" },
  { key: "account", label: "Account" },
  { key: "assistant", label: "WhatsApp assistant" },
  { key: "whatsapp", label: "WhatsApp number" },
  { key: "business", label: "Business" },
  { key: "team", label: "Team" },
] as const;

export default function SettingsPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("availability");
  const me = useMe();
  const isAdmin = me.data && me.data.user.role !== "agent";
  return (
    <>
      <PageHeader title="Settings" />
      <div className="mb-8 flex flex-wrap gap-1 border-b border-rule" role="tablist">
        {TABS.filter((t) => isAdmin || t.key === "availability" || t.key === "account").map((t) => (
          <button key={t.key} role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${tab === t.key ? "border-registry font-medium text-ink" : "border-transparent text-ink-soft hover:text-ink"}`}>
            {t.label}
          </button>
        ))}
      </div>
      <div className="max-w-3xl">
        {tab === "availability" && <Availability />}
        {tab === "account" && <Account />}
        {tab === "assistant" && <Assistant />}
        {tab === "whatsapp" && <WhatsApp />}
        {tab === "business" && <Business />}
        {tab === "team" && <Team />}
      </div>
    </>
  );
}

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

function Availability() {
  const qc = useQueryClient();
  const me = useMe();
  const team = useTeam();
  const isAdmin = me.data?.user.role !== "agent";
  const [userId, setUserId] = useState("");
  const rules = useQuery({
    queryKey: ["rules", userId],
    queryFn: () => api<AvailabilityRule[]>(`/availability/rules${qs({ user_id: userId })}`),
  });
  const [draft, setDraft] = useState<AvailabilityRule[] | null>(null);
  const current = draft ?? rules.data ?? [];
  const save = useMutation({
    mutationFn: () => api(`/availability/rules${qs({ user_id: userId })}`, {
      method: "PUT",
      json: current.map(({ weekday, start_time, end_time, slot_minutes }) => ({ weekday, start_time, end_time, slot_minutes })),
    }),
    onSuccess: () => { setDraft(null); qc.invalidateQueries({ queryKey: ["rules"] }); qc.invalidateQueries({ queryKey: ["slots"] }); },
  });
  const edit = (i: number, patch: Partial<AvailabilityRule>) =>
    setDraft(current.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const exceptions = useQuery({
    queryKey: ["exceptions", userId],
    queryFn: () => api<{ id: string; day: string; reason: string | null }[]>(`/availability/exceptions${qs({ user_id: userId })}`),
  });
  const [off, setOff] = useState("");
  const addOff = useMutation({
    mutationFn: () => api(`/availability/exceptions${qs({ user_id: userId })}`, { method: "POST", json: { day: off } }),
    onSuccess: () => { setOff(""); qc.invalidateQueries({ queryKey: ["exceptions"] }); },
  });
  const delOff = useMutation({
    mutationFn: (id: string) => api(`/availability/exceptions/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["exceptions"] }),
  });

  return (
    <div className="space-y-10">
      <section>
        <h2 className="text-lg font-semibold">Weekly hours</h2>
        <p className="mb-4 text-sm text-ink-soft">
          The assistant and your booking page only offer times inside these hours, minus anything already booked.
        </p>
        {isAdmin && (
          <Select className="mb-4 w-64" value={userId} onChange={(e) => { setUserId(e.target.value); setDraft(null); }} aria-label="Team member">
            <option value="">My hours</option>
            {team.data?.filter((u) => u.id !== me.data?.user.id).map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </Select>
        )}
        <ul className="divide-y divide-rule border-y border-rule">
          {WEEKDAYS.map((name, wd) => {
            const dayRules = current.map((r, i) => ({ r, i })).filter(({ r }) => r.weekday === wd);
            return (
              <li key={wd} className="flex flex-wrap items-center gap-3 py-3">
                <span className="w-28 text-sm font-medium">{name}</span>
                <div className="flex flex-1 flex-col gap-2">
                  {dayRules.length === 0 && <span className="text-sm text-ink-faint">Unavailable</span>}
                  {dayRules.map(({ r, i }) => (
                    <div key={i} className="flex flex-wrap items-center gap-2 text-sm">
                      <Input type="time" value={r.start_time.slice(0, 5)} onChange={(e) => edit(i, { start_time: e.target.value })} className="w-32" aria-label="From" />
                      <span>to</span>
                      <Input type="time" value={r.end_time.slice(0, 5)} onChange={(e) => edit(i, { end_time: e.target.value })} className="w-32" aria-label="Until" />
                      <Select value={r.slot_minutes} onChange={(e) => edit(i, { slot_minutes: Number(e.target.value) })} className="w-32" aria-label="Slot length">
                        {[30, 45, 60, 90, 120].map((m) => <option key={m} value={m}>{m} min slots</option>)}
                      </Select>
                      <button onClick={() => setDraft(current.filter((_, j) => j !== i))} aria-label="Remove hours" className="text-ink-faint hover:text-brick">
                        <Trash2 size={16} />
                      </button>
                    </div>
                  ))}
                </div>
                <Button size="sm" variant="ghost" onClick={() => setDraft([...current, { weekday: wd, start_time: "10:00", end_time: "18:00", slot_minutes: 60 }])}>
                  <Plus size={14} /> Add hours
                </Button>
              </li>
            );
          })}
        </ul>
        <ErrorText error={save.error} />
        <Button className="mt-4" onClick={() => save.mutate()} disabled={!draft || save.isPending}>Save hours</Button>
      </section>

      <section>
        <h2 className="text-lg font-semibold">Days off</h2>
        <p className="mb-3 text-sm text-ink-soft">No bookings are offered on these dates.</p>
        <ul className="mb-3 space-y-1 text-sm">
          {exceptions.data?.map((x) => (
            <li key={x.id} className="flex items-center gap-2">
              {day(x.day + "T12:00:00")}
              <button onClick={() => delOff.mutate(x.id)} aria-label="Remove day off" className="text-ink-faint hover:text-brick"><Trash2 size={14} /></button>
            </li>
          ))}
        </ul>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); addOff.mutate(); }}>
          <Input type="date" required value={off} onChange={(e) => setOff(e.target.value)} className="w-48" aria-label="Day off" />
          <Button type="submit" variant="secondary">Add day off</Button>
        </form>
      </section>
    </div>
  );
}

function useTenantSave() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api<Tenant>("/tenant", { method: "PATCH", json: body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });
}

type Templates = Record<string, { name: string; language: string }>;

function Assistant() {
  const me = useMe();
  const save = useTenantSave();
  const s = (me.data?.tenant.bot_settings ?? {}) as { persona?: string; extra_instructions?: string; templates?: Templates };
  return (
    <div className="space-y-10">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          const tpl = (k: string) => (f.get(k) ? { name: f.get(k), language: f.get("tpl_lang") || "en" } : undefined);
          save.mutate({
            bot_settings: {
              ...s,
              persona: f.get("persona") || undefined,
              extra_instructions: f.get("extra") || undefined,
              templates: {
                ...(tpl("tpl_confirm") && { appointment_confirmation: tpl("tpl_confirm") }),
                ...(tpl("tpl_remind") && { appointment_reminder: tpl("tpl_remind") }),
              },
            },
          });
        }}
      >
        <h2 className="text-lg font-semibold">How the assistant talks</h2>
        <Field label="Introduction" hint="Leave empty for the default: a helpful assistant for your business.">
          <Textarea name="persona" rows={3} defaultValue={s.persona} placeholder="You are Priya's assistant at Demo Realty. Warm, brief, never pushy." />
        </Field>
        <Field label="Extra instructions" hint="Rules specific to your business. The assistant follows these on every chat.">
          <Textarea name="extra" rows={5} defaultValue={s.extra_instructions}
            placeholder={"Site visits only Tuesday to Sunday.\nAlways mention the festive offer on PR-1003 until 15 Nov.\nAnswer in Kannada if the buyer writes in Kannada."} />
        </Field>
        <h3 className="pt-2 font-semibold">Reminder templates</h3>
        <p className="text-sm text-ink-soft">
          WhatsApp only allows free messages within 24 hours of the client&apos;s last message. For confirmations and reminders
          after that, create approved templates in Meta Business Manager with three variables (name, time, place) and enter their names here.
        </p>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Confirmation template"><Input name="tpl_confirm" defaultValue={s.templates?.appointment_confirmation?.name} /></Field>
          <Field label="Reminder template"><Input name="tpl_remind" defaultValue={s.templates?.appointment_reminder?.name} /></Field>
          <Field label="Template language"><Input name="tpl_lang" defaultValue={s.templates?.appointment_reminder?.language ?? "en"} /></Field>
        </div>
        <ErrorText error={save.error} />
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={save.isPending}>Save assistant settings</Button>
          {save.isSuccess && <span className="text-sm text-registry">Saved</span>}
        </div>
      </form>
      <section>
        <h2 className="text-lg font-semibold">Documents for every chat</h2>
        <p className="mb-3 text-sm text-ink-soft">FAQs, company profile, loan partners, payment policies. Listing-specific brochures go on each property.</p>
        <Documents />
      </section>
    </div>
  );
}

function WhatsApp() {
  const qc = useQueryClient();
  const me = useMe();
  const t = me.data?.tenant;
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api("/tenant/whatsapp", { method: "PUT", json: body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });
  const webhook = `${API_URL}/webhooks/whatsapp`;
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        const f = new FormData(e.currentTarget);
        save.mutate({ phone_number_id: f.get("pnid"), display_number: f.get("display"), access_token: f.get("token") });
      }}
    >
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-semibold">WhatsApp Business number</h2>
        {t?.whatsapp_phone_number_id ? <Badge tone="green">Connected</Badge> : <Badge tone="gold">Not connected</Badge>}
      </div>
      <ol className="list-decimal space-y-1 pl-5 text-sm text-ink-soft">
        <li>In Meta for Developers, add the WhatsApp product to your app and register your business number.</li>
        <li>Set the webhook URL to <code className="rounded bg-paper px-1 text-ink">{webhook}</code> and subscribe to <em>messages</em>.</li>
        <li>Create a permanent system-user access token with <em>whatsapp_business_messaging</em> permission and paste it below.</li>
      </ol>
      <Field label="Phone number ID"><Input name="pnid" required defaultValue={t?.whatsapp_phone_number_id ?? ""} /></Field>
      <Field label="Number buyers see" hint="Used for the Chat on WhatsApp buttons on your listing page">
        <Input name="display" required defaultValue={t?.whatsapp_display_number ?? ""} placeholder="+91 98765 43210" />
      </Field>
      <Field label="Access token" hint="Stored encrypted. Paste again to replace it.">
        <Input name="token" type="password" required autoComplete="off" />
      </Field>
      <ErrorText error={save.error} />
      <Button type="submit" disabled={save.isPending}>{t?.whatsapp_phone_number_id ? "Update connection" : "Connect number"}</Button>
      {save.isSuccess && <span className="ml-3 text-sm text-registry">Connected</span>}
    </form>
  );
}

function Business() {
  const me = useMe();
  const save = useTenantSave();
  const t = me.data?.tenant;
  if (!t) return null;
  return (
    <form className="space-y-4" onSubmit={(e) => {
      e.preventDefault();
      const f = new FormData(e.currentTarget);
      save.mutate({
        name: f.get("name"), timezone: f.get("tz"), contact_email: f.get("email") || null,
        list_on_marketplace: f.get("marketplace") === "on",
      });
    }}>
      <Field label="Business name"><Input name="name" defaultValue={t.name} required /></Field>
      <Field label="Contact email"><Input name="email" type="email" defaultValue={t.contact_email ?? ""} /></Field>
      <Field label="Time zone" hint="All booking times are shown in this zone">
        <Select name="tz" defaultValue={t.timezone}>
          {Intl.supportedValuesOf("timeZone").map((z) => <option key={z} value={z}>{z}</option>)}
        </Select>
      </Field>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" name="marketplace" defaultChecked={t.list_on_marketplace} className="mt-0.5" />
        <span>
          Show my published listings on the EstateFlow home page and search, where buyers can find
          them and contact me on WhatsApp
        </span>
      </label>
      <p className="text-sm text-ink-soft">
        Your own listing page: <a className="text-registry hover:underline" href={`/s/${t.slug}`}>/s/{t.slug}</a>
      </p>
      <ErrorText error={save.error} />
      <Button type="submit" disabled={save.isPending}>Save</Button>
    </form>
  );
}

function Team() {
  const qc = useQueryClient();
  const team = useTeam();
  const [adding, setAdding] = useState(false);
  const update = useMutation({
    mutationFn: ({ id, ...body }: { id: string } & Partial<User>) => api(`/users/${id}`, { method: "PATCH", json: body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
  const add = useMutation({
    mutationFn: (body: Record<string, unknown>) => api("/users", { method: "POST", json: body }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["users"] }); setAdding(false); },
  });
  return (
    <section>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Team</h2>
        <Button size="sm" onClick={() => setAdding(true)}><Plus size={14} /> Add member</Button>
      </div>
      <ErrorText error={update.error} />
      <ul className="divide-y divide-rule border-y border-rule">
        {team.data?.map((u) => (
          <li key={u.id} className="flex flex-wrap items-center gap-3 py-3 text-sm">
            <div className="min-w-0 flex-1">
              <p className="font-medium">{u.full_name} {!u.is_active && <Badge tone="red">Deactivated</Badge>}</p>
              <p className="text-ink-soft">{u.email}</p>
            </div>
            <Select value={u.role} onChange={(e) => update.mutate({ id: u.id, role: e.target.value as Role })} className="w-32" aria-label="Role">
              <option value="owner">Owner</option><option value="admin">Admin</option><option value="agent">Agent</option>
            </Select>
            <Button size="sm" variant="ghost" onClick={() => update.mutate({ id: u.id, is_active: !u.is_active })}>
              {u.is_active ? "Deactivate" : "Reactivate"}
            </Button>
          </li>
        ))}
      </ul>
      <Modal open={adding} onClose={() => setAdding(false)} title="Add team member">
        <form className="space-y-4" onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          add.mutate({ full_name: f.get("name"), email: f.get("email"), phone: f.get("phone") || null, password: f.get("password"), role: f.get("role") });
        }}>
          <Field label="Name"><Input name="name" required /></Field>
          <Field label="Email"><Input name="email" type="email" required /></Field>
          <Field label="Phone"><Input name="phone" /></Field>
          <Field label="Temporary password" hint="Share it with them; they sign in with their email"><Input name="password" minLength={8} required /></Field>
          <Field label="Role" hint="Agents see everything but can't change settings or the team">
            <Select name="role" defaultValue="agent"><option value="agent">Agent</option><option value="admin">Admin</option></Select>
          </Field>
          <ErrorText error={add.error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setAdding(false)}>Cancel</Button>
            <Button type="submit" disabled={add.isPending}>Add member</Button>
          </div>
        </form>
      </Modal>
    </section>
  );
}

function Account() {
  const router = useRouter();
  const [done, setDone] = useState(false);
  const change = useMutation({
    mutationFn: (body: Record<string, unknown>) => api("/auth/password", { method: "POST", json: body }),
    onSuccess: () => setDone(true),
  });
  const everywhere = useMutation({
    mutationFn: () => signOut(true),
    onSuccess: () => router.replace("/login"),
  });
  return (
    <div className="space-y-10">
      <form
        className="max-w-sm space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          setDone(false);
          change.mutate({ current_password: f.get("current"), new_password: f.get("next") });
          e.currentTarget.reset();
        }}
      >
        <h2 className="text-lg font-semibold">Change password</h2>
        <Field label="Current password"><Input name="current" type="password" required autoComplete="current-password" /></Field>
        <Field label="New password" hint="At least 8 characters. Other devices are signed out.">
          <Input name="next" type="password" minLength={8} required autoComplete="new-password" />
        </Field>
        <ErrorText error={change.error} />
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={change.isPending}>Change password</Button>
          {done && <span className="text-sm text-registry">Password changed</span>}
        </div>
      </form>
      <section>
        <h2 className="text-lg font-semibold">Sign out everywhere</h2>
        <p className="mb-3 text-sm text-ink-soft">Ends every session for your account, including on lost or shared devices.</p>
        <Button variant="danger" onClick={() => everywhere.mutate()} disabled={everywhere.isPending}>
          Sign out everywhere
        </Button>
      </section>
    </div>
  );
}
