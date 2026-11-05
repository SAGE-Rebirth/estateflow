"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { API_URL } from "@/lib/api";

/** "Dashboard" for signed-in sellers, "Seller sign in" for everyone else. */
export function AccountLink() {
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => {
    // Plain fetch: a 401 here just means "not signed in", never a redirect.
    fetch(`${API_URL}/auth/me`, { credentials: "include" })
      .then((r) => setSignedIn(r.ok))
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
