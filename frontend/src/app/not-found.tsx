import Link from "next/link";
import { SiteFooter, SiteHeader } from "@/components/site/header";

export const metadata = { title: "Page not found | EstateFlow" };

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col bg-paper">
      <SiteHeader />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-20 sm:px-6">
        <h1 className="text-3xl font-semibold">This page isn&apos;t here</h1>
        <p className="mt-2 text-ink-soft">
          The listing may have been sold, rented or taken down by the seller, or the link is mistyped.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link href="/properties" className="rounded-md bg-registry px-4 py-2.5 font-medium text-white hover:bg-registry-deep">
            Browse all homes
          </Link>
          <Link href="/" className="rounded-md border border-rule px-4 py-2.5 font-medium hover:bg-stone">Go to the home page</Link>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
