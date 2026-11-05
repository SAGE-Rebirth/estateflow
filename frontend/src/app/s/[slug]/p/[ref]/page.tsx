import { redirect } from "next/navigation";

// Listing pages moved to the marketplace; keep old links (and WhatsApp shares) working.
export default async function OldListingPage({ params }: { params: Promise<{ slug: string; ref: string }> }) {
  const { slug, ref } = await params;
  redirect(`/properties/${slug}/${ref}`);
}
