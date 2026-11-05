"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import type { PropertyType } from "@/lib/types";
import { PropertyArt } from "./property-art";

export function Gallery({ photos, title, type }: { photos: string[]; title: string; type: PropertyType }) {
  const [i, setI] = useState(0);
  if (photos.length === 0) {
    return (
      <div>
        <PropertyArt type={type} className="aspect-[16/9] w-full rounded-lg" />
        <p className="mt-2 text-sm text-ink-soft">The seller hasn&apos;t added photos yet. Ask for some on WhatsApp.</p>
      </div>
    );
  }
  const go = (d: number) => setI((n) => (n + d + photos.length) % photos.length);
  return (
    <div>
      <div className="relative overflow-hidden rounded-lg bg-stone">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={photos[i]} alt={`${title}, photo ${i + 1} of ${photos.length}`} className="aspect-[16/9] w-full object-cover" />
        {photos.length > 1 && (
          <>
            <button onClick={() => go(-1)} aria-label="Previous photo"
              className="absolute left-3 top-1/2 -translate-y-1/2 rounded-full bg-paper/90 p-2 shadow hover:bg-paper">
              <ChevronLeft size={20} />
            </button>
            <button onClick={() => go(1)} aria-label="Next photo"
              className="absolute right-3 top-1/2 -translate-y-1/2 rounded-full bg-paper/90 p-2 shadow hover:bg-paper">
              <ChevronRight size={20} />
            </button>
            <span className="tnum absolute bottom-3 right-3 rounded bg-ink/70 px-2 py-0.5 text-xs text-white">
              {i + 1} / {photos.length}
            </span>
          </>
        )}
      </div>
      {photos.length > 1 && (
        <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
          {photos.map((src, n) => (
            <button key={src} onClick={() => setI(n)} aria-label={`Show photo ${n + 1}`} aria-current={n === i}
              className={`shrink-0 overflow-hidden rounded ${n === i ? "ring-2 ring-registry" : "opacity-70 hover:opacity-100"}`}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={src} alt="" className="h-16 w-24 object-cover" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function ShareButton({ title }: { title: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        const url = window.location.href;
        if (navigator.share) {
          await navigator.share({ title, url }).catch(() => undefined);
        } else {
          await navigator.clipboard.writeText(url);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        }
      }}
      className="text-sm text-ink-soft underline hover:text-ink"
    >
      {copied ? "Link copied" : "Share this home"}
    </button>
  );
}
