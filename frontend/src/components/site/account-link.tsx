"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { API_URL } from "@/lib/api";

/** "Dashboard" for signed-in sellers, "Seller sign in" for everyone else. */
export function AccountLink() {
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => {
    // Always answers 200 (no console noise for visitors) and counts a still-valid
    // refresh cookie as signed in, so it stays right after the access token expires.
    fetch(`${API_URL}/auth/session`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : { signed_in: false }))
      .then((b: { signed_in: boolean }) => setSignedIn(b.signed_in))
      .catch(() => undefined);
  }, []);
  return signedIn ? (
    <Link href="/dashboard" className="rounded-md px-3 py-2 font-medium text-registry hover:bg-registry-tint">
      Dashboard
    </Link>
  ) : (
    <Link href="/login" className="rounded-md px-3 py-2 text-ink-soft hover:text-ink">Seller sign in</Link>
  );
}
