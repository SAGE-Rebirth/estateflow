import { MessageCircle } from "lucide-react";
import Link from "next/link";
import { SiteFooter, SiteHeader } from "@/components/site/header";
import { waLink } from "@/lib/format";
import { publicGet, type PublicTenant } from "@/lib/public-api";

/** A seller's own pages, inside the marketplace frame so buyers can always browse on. */
export default async function SellerLayout({
  children, params,
}: { children: React.ReactNode; params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const t = await publicGet<PublicTenant>(`/${slug}`);
  return (
    <div className="flex min-h-screen flex-col bg-paper">
      <SiteHeader />
      <div className="border-b border-rule bg-stone">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:px-6">
          <nav className="text-sm text-ink-soft" aria-label="Breadcrumb">
            <Link href="/properties" className="hover:underline">Homes</Link> /{" "}
            <Link href={`/s/${slug}`} className="font-medium text-ink hover:underline">{t.name}</Link>
          </nav>
          {t.whatsapp_number && (
            <a href={waLink(t.whatsapp_number, `Hi ${t.name}, I'm looking for a property`)} target="_blank" rel="noreferrer"
              className="ml-auto inline-flex items-center gap-1.5 text-sm text-registry hover:underline">
              <MessageCircle size={16} /> <span className="tnum">{t.whatsapp_number}</span>
            </a>
          )}
        </div>
      </div>
      <div className="flex-1">{children}</div>
      <SiteFooter />
    </div>
  );
}
