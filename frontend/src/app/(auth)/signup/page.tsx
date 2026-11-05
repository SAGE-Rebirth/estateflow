"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, ErrorText, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";

const slugify = (s: string) =>
  s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60);

export default function SignupPage() {
  const router = useRouter();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [business, setBusiness] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      await api("/auth/signup", {
        method: "POST", auth: false,
        json: {
          business_name: business, slug, full_name: f.get("full_name"),
          email: f.get("email"), password: f.get("password"),
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Kolkata",
        },
      });
      router.replace("/dashboard");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1 className="text-2xl font-semibold">Create your business account</h1>
      <p className="mt-1 text-sm text-ink-soft">You&apos;ll be the owner. Add your team later.</p>
      <form onSubmit={onSubmit} className="mt-8 space-y-4">
        <Field label="Business name">
          <Input
            required value={business}
            onChange={(e) => {
              setBusiness(e.target.value);
              if (!slugEdited) setSlug(slugify(e.target.value));
            }}
          />
        </Field>
        <Field label="Listing page address" hint={`Your public listings live at /s/${slug || "your-business"}`}>
          <Input
            required value={slug} pattern="[a-z0-9][a-z0-9-]{1,78}[a-z0-9]"
            onChange={(e) => {
              setSlugEdited(true);
              setSlug(slugify(e.target.value));
            }}
          />
        </Field>
        <Field label="Your name"><Input name="full_name" required autoComplete="name" /></Field>
        <Field label="Email"><Input name="email" type="email" required autoComplete="email" /></Field>
        <Field label="Password" hint="At least 8 characters">
          <Input name="password" type="password" minLength={8} required autoComplete="new-password" />
        </Field>
        <ErrorText error={error} />
        <Button type="submit" disabled={busy} className="w-full">
          {busy ? "Creating account…" : "Create account"}
        </Button>
      </form>
      <p className="mt-6 text-sm text-ink-soft">
        Already have an account? <Link href="/login" className="text-registry hover:underline">Sign in</Link>
      </p>
    </>
  );
}
