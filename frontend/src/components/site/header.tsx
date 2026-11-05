import Link from "next/link";
import { AccountLink } from "./account-link";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-30 border-b border-rule bg-paper/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-6 px-4 sm:px-6">
        <Link href="/" className="font-[family-name:var(--font-display)] text-xl font-semibold text-registry">
          EstateFlow
        </Link>
        <nav className="hidden items-center gap-5 text-sm sm:flex" aria-label="Browse">
          <Link href="/properties?listing_type=sale" className="text-ink-soft hover:text-ink">Buy</Link>
          <Link href="/properties?listing_type=rent" className="text-ink-soft hover:text-ink">Rent</Link>
          <Link href="/properties?property_type=plot" className="text-ink-soft hover:text-ink">Plots</Link>
          <Link href="/properties?property_type=commercial&property_type=office" className="text-ink-soft hover:text-ink">
            Commercial
          </Link>
        </nav>
        <div className="ml-auto flex items-center gap-2 text-sm">
          <AccountLink />
          <Link href="/signup" className="hidden rounded-md border border-registry px-3 py-2 font-medium text-registry hover:bg-registry-tint sm:block">
            List your property
          </Link>
        </div>
      </div>
      <nav className="flex gap-5 overflow-x-auto border-t border-rule px-4 py-2 text-sm sm:hidden" aria-label="Browse">
        <Link href="/properties?listing_type=sale" className="text-ink-soft">Buy</Link>
        <Link href="/properties?listing_type=rent" className="text-ink-soft">Rent</Link>
        <Link href="/properties?property_type=plot" className="text-ink-soft">Plots</Link>
        <Link href="/signup" className="ml-auto whitespace-nowrap font-medium text-registry">List your property</Link>
      </nav>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="mt-20 border-t border-rule bg-paper">
      <div className="mx-auto grid max-w-7xl gap-8 px-4 py-10 text-sm sm:grid-cols-3 sm:px-6">
        <div>
          <p className="font-[family-name:var(--font-display)] text-lg font-semibold text-registry">EstateFlow</p>
          <p className="mt-2 max-w-xs text-ink-soft">
            Homes listed directly by brokers and builders. Ask anything on WhatsApp and get an answer in minutes.
          </p>
        </div>
        <div>
          <p className="font-medium">Browse</p>
          <ul className="mt-2 space-y-1 text-ink-soft">
            <li><Link href="/properties?listing_type=sale" className="hover:text-ink">Homes for sale</Link></li>
            <li><Link href="/properties?listing_type=rent" className="hover:text-ink">Homes for rent</Link></li>
            <li><Link href="/properties?property_type=plot" className="hover:text-ink">Plots</Link></li>
          </ul>
        </div>
        <div>
          <p className="font-medium">For sellers</p>
          <ul className="mt-2 space-y-1 text-ink-soft">
            <li><Link href="/signup" className="hover:text-ink">List your property</Link></li>
            <li><Link href="/login" className="hover:text-ink">Seller sign in</Link></li>
          </ul>
        </div>
      </div>
      <p className="mx-auto max-w-7xl px-4 pb-8 text-xs text-ink-faint sm:px-6">
        Prices and availability are set by each seller and confirmed at the time of visit.
      </p>
    </footer>
  );
}
