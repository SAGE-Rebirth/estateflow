"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  Building2, CalendarDays, ExternalLink, LogOut, Menu, MessageCircle, Settings, Store, Sun, Users, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { NotificationBell } from "@/components/notifications";
import { signOut as endSession } from "@/lib/api";
import { useMe } from "@/lib/hooks";

const NAV = [
  { href: "/dashboard", label: "Today", icon: Sun },
  { href: "/dashboard/calendar", label: "Calendar", icon: CalendarDays },
  { href: "/dashboard/contacts", label: "Leads", icon: Users },
  { href: "/dashboard/inbox", label: "WhatsApp", icon: MessageCircle },
  { href: "/dashboard/properties", label: "Properties", icon: Building2 },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const qc = useQueryClient();
  const [navOpen, setNavOpen] = useState(false);
  const me = useMe();
  useEffect(() => {
    setNavOpen(false);
  }, [path]);

  if (!me.data) {
    return <div className="grid min-h-screen place-items-center text-ink-faint">Loading…</div>;
  }

  const active = (href: string) => (href === "/dashboard" ? path === "/dashboard" : path.startsWith(href));
  const signOut = async () => {
    await endSession().catch(() => undefined);
    qc.clear();
    router.replace("/login");
  };

  const nav = (
    <nav className="flex flex-1 flex-col gap-0.5 p-3">
      {NAV.map(({ href, label, icon: Icon }) => (
        <Link
          key={href}
          href={href}
          aria-current={active(href) ? "page" : undefined}
          className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm ${
            active(href)
              ? "bg-registry text-white"
              : "text-ink-soft hover:bg-registry-tint hover:text-ink"
          }`}
        >
          <Icon size={18} />
          {label}
        </Link>
      ))}
      <p className="mt-6 px-3 text-xs font-medium text-ink-faint">What buyers see</p>
      <Link href="/" className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-ink-soft hover:bg-registry-tint hover:text-ink">
        <Store size={18} /> Marketplace
      </Link>
      <Link href={`/s/${me.data.tenant.slug}`} className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-ink-soft hover:bg-registry-tint hover:text-ink">
        <ExternalLink size={18} /> My listing page
      </Link>
      <div className="mt-auto border-t border-rule pt-3">
        <p className="px-3 text-sm font-medium">{me.data.user.full_name}</p>
        <p className="px-3 text-xs text-ink-faint">{me.data.tenant.name}</p>
        <button
          onClick={signOut}
          className="mt-2 flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-ink-soft hover:bg-registry-tint"
        >
          <LogOut size={18} /> Sign out
        </button>
      </div>
    </nav>
  );

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-rule bg-paper lg:flex">
        <Link href="/dashboard" className="px-6 py-5 font-[family-name:var(--font-display)] text-lg font-semibold text-registry">
          EstateFlow
        </Link>
        {nav}
      </aside>
      {navOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-ink/40" onClick={() => setNavOpen(false)} />
          <aside className="relative flex h-full w-64 flex-col bg-paper">
            <div className="flex items-center justify-between px-6 py-5">
              <Link href="/dashboard" className="font-[family-name:var(--font-display)] text-lg font-semibold text-registry">EstateFlow</Link>
              <button onClick={() => setNavOpen(false)} aria-label="Close menu"><X size={20} /></button>
            </div>
            {nav}
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-rule bg-stone/90 px-4 backdrop-blur sm:px-6">
          <button className="rounded-md p-2 lg:hidden" onClick={() => setNavOpen(true)} aria-label="Open menu">
            <Menu size={20} />
          </button>
          <span className="hidden text-sm text-ink-soft lg:block">
            {new Date().toLocaleDateString("en-IN", {
              weekday: "long", day: "numeric", month: "long", timeZone: me.data.tenant.timezone,
            })}
          </span>
          <div className="flex items-center gap-1">
            <Link href="/" className="hidden items-center gap-1.5 rounded-md px-3 py-2 text-sm text-ink-soft hover:bg-registry-tint hover:text-ink sm:flex">
              <Store size={16} /> View marketplace
            </Link>
            <NotificationBell />
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 sm:py-8">{children}</main>
      </div>
    </div>
  );
}
