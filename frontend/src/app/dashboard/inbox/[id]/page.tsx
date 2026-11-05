"use client";

import { Suspense, use } from "react";
import { InboxView } from "@/components/inbox";

export default function ConversationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <Suspense><InboxView selectedId={id} /></Suspense>;
}
