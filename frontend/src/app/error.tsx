"use client";

import Link from "next/link";

export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <main className="mx-auto max-w-3xl px-4 py-20 sm:px-6">
      <h1 className="text-3xl font-semibold">Something went wrong loading this page</h1>
      <p className="mt-2 text-ink-soft">It&apos;s usually temporary. Try again, or head back to the homes.</p>
      <div className="mt-8 flex flex-wrap gap-3">
        <button onClick={reset} className="rounded-md bg-registry px-4 py-2.5 font-medium text-white hover:bg-registry-deep">
          Try again
        </button>
        <Link href="/" className="rounded-md border border-rule px-4 py-2.5 font-medium hover:bg-stone">Go to the home page</Link>
      </div>
    </main>
  );
}
