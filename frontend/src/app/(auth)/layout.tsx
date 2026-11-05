import { ArrowLeft } from "lucide-react";
import Link from "next/link";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[1fr_minmax(0,32rem)]">
      <section className="hidden flex-col justify-between bg-registry p-12 text-white lg:flex">
        <Link href="/" className="font-[family-name:var(--font-display)] text-xl font-semibold">EstateFlow</Link>
        <div className="max-w-md">
          <p className="font-[family-name:var(--font-display)] text-4xl font-semibold leading-tight">
            Buyers message you on WhatsApp. The assistant answers, books the visit, and it lands on
            your day sheet.
          </p>
          <p className="mt-6 text-white/75">
            List properties, let the assistant handle first questions from your brochures, and
            walk into every site visit knowing who you&apos;re meeting.
          </p>
        </div>
        <span className="text-sm text-white/60">For brokers, resellers and builders</span>
      </section>
      <main className="flex flex-col px-4 py-6 sm:px-8">
        <div className="flex items-center justify-between">
          <Link href="/" className="font-[family-name:var(--font-display)] text-lg font-semibold text-registry lg:invisible">
            EstateFlow
          </Link>
          <Link href="/" className="inline-flex items-center gap-1 text-sm text-ink-soft hover:text-ink">
            <ArrowLeft size={16} /> Back to homes
          </Link>
        </div>
        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-sm">{children}</div>
        </div>
      </main>
    </div>
  );
}
