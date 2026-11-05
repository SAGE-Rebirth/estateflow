"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Button, ErrorText, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";

export default function LoginPage() {
  return (
    <Suspense>
      <Login />
    </Suspense>
  );
}

function Login() {
  const router = useRouter();
  const next = useSearchParams().get("next");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      await api("/auth/login", {
        method: "POST", auth: false,
        json: { email: f.get("email"), password: f.get("password") },
      });
      router.replace(next?.startsWith("/") ? next : "/dashboard");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1 className="text-2xl font-semibold">Sign in</h1>
      <p className="mt-1 text-sm text-ink-soft">Welcome back. Your day sheet is waiting.</p>
      <form onSubmit={onSubmit} className="mt-8 space-y-4">
        <Field label="Email"><Input name="email" type="email" required autoComplete="email" /></Field>
        <Field label="Password">
          <Input name="password" type="password" required autoComplete="current-password" />
        </Field>
        <ErrorText error={error} />
        <Button type="submit" disabled={busy} className="w-full">
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      <p className="mt-6 text-sm text-ink-soft">
        New here? <Link href="/signup" className="text-registry hover:underline">Create your business account</Link>
      </p>
    </>
  );
}
