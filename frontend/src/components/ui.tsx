"use client";

import { X } from "lucide-react";
import { useEffect, useRef } from "react";

type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
};

export function Button({ variant = "primary", size = "md", className = "", ...p }: BtnProps) {
  const base =
    "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none";
  const sizes = { sm: "h-8 px-2.5 text-sm", md: "h-10 px-4 text-sm" };
  const variants = {
    primary: "bg-registry text-white hover:bg-registry-deep",
    secondary: "bg-paper text-ink border border-rule hover:bg-registry-tint",
    ghost: "text-ink-soft hover:bg-registry-tint hover:text-ink",
    danger: "bg-paper text-brick border border-rule hover:bg-brick-tint",
  };
  return <button className={`${base} ${sizes[size]} ${variants[variant]} ${className}`} {...p} />;
}

const fieldCls =
  "rounded-md border border-rule bg-paper px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-registry focus:outline-none";

export function Input(p: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...p} className={`${fieldCls} h-10 ${p.className ?? ""}`} />;
}

export function Textarea(p: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...p} className={`${fieldCls} ${p.className ?? ""}`} />;
}

export function Select(p: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...p} className={`${fieldCls} h-10 ${p.className ?? ""}`} />;
}

export function Field({
  label, hint, children, className = "",
}: { label: string; hint?: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={`block [&_input]:w-full [&_select]:w-full [&_textarea]:w-full ${className}`}>
      <span className="mb-1 block text-sm font-medium text-ink">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-ink-faint">{hint}</span>}
    </label>
  );
}

const TONES = {
  neutral: "bg-stone text-ink-soft border-rule",
  green: "bg-registry-tint text-registry-deep border-transparent",
  gold: "bg-marigold-tint text-[#8a5f0c] border-transparent",
  red: "bg-brick-tint text-brick border-transparent",
};

export function Badge({
  tone = "neutral", children,
}: { tone?: keyof typeof TONES; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium ${TONES[tone]}`}>
      {children}
    </span>
  );
}

export function Modal({
  open, onClose, title, children, wide = false,
}: {
  open: boolean; onClose: () => void; title: string; children: React.ReactNode; wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      className={`m-auto w-[calc(100%-2rem)] ${wide ? "max-w-2xl" : "max-w-lg"} rounded-lg bg-paper p-0 text-ink shadow-xl backdrop:bg-ink/40`}
    >
      {open && (
        <div className="p-5">
          <div className="mb-4 flex items-start justify-between gap-4">
            <h2 className="text-lg font-semibold">{title}</h2>
            <button onClick={onClose} aria-label="Close" className="rounded p-1 text-ink-faint hover:text-ink">
              <X size={18} />
            </button>
          </div>
          {children}
        </div>
      )}
    </dialog>
  );
}

export function Empty({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="rounded-md border border-dashed border-rule px-4 py-6 text-sm text-ink-soft">
      <p>{children}</p>
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  return <p className="text-sm text-brick">{error instanceof Error ? error.message : String(error)}</p>;
}

export function PageHeader({
  title, subtitle, actions,
}: { title: string; subtitle?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold sm:text-3xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-soft">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
