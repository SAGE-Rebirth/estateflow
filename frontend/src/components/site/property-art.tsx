import type { PropertyType } from "@/lib/types";

/**
 * Drawn stand-in for listings without photos: a line elevation of the property type,
 * so a grid of new listings still reads as homes rather than broken images.
 */
export function PropertyArt({ type, className = "" }: { type: PropertyType; className?: string }) {
  const stroke = "var(--color-registry)";
  const common = { fill: "none", stroke, strokeWidth: 2, strokeLinejoin: "round" as const };
  const window = (x: number, y: number, w = 10, h = 12) => (
    <rect key={`${x}-${y}`} x={x} y={y} width={w} height={h} {...common} strokeWidth={1.5} />
  );
  let art: React.ReactNode;
  switch (type) {
    case "villa":
    case "independent_house":
      art = (
        <>
          <path d="M40 78 L100 38 L160 78" {...common} />
          <rect x="52" y="74" width="96" height="58" {...common} />
          <rect x="90" y="100" width="20" height="32" {...common} />
          {window(62, 88, 18, 14)}
          {window(120, 88, 18, 14)}
          <path d="M20 132 H180" {...common} />
          <circle cx="172" cy="112" r="10" {...common} strokeWidth={1.5} />
          <path d="M172 122 V132" {...common} strokeWidth={1.5} />
        </>
      );
      break;
    case "plot":
      art = (
        <>
          <path d="M30 120 L70 70 L170 70 L130 120 Z" {...common} />
          <path d="M70 70 L74 64 M170 70 L174 64 M130 120 L134 114 M30 120 L34 114" {...common} strokeWidth={1.5} />
          <path d="M60 100 H140" {...common} strokeDasharray="4 5" strokeWidth={1.5} />
          <path d="M20 132 H180" {...common} />
        </>
      );
      break;
    case "commercial":
    case "office":
      art = (
        <>
          <rect x="62" y="30" width="76" height="102" {...common} />
          {[44, 62, 80, 98].flatMap((y) => [74, 95, 116].map((x) => window(x, y, 12, 10)))}
          <rect x="90" y="114" width="20" height="18" {...common} />
          <path d="M20 132 H180" {...common} />
        </>
      );
      break;
    default:
      art = (
        <>
          <rect x="44" y="40" width="54" height="92" {...common} />
          <rect x="98" y="24" width="58" height="108" {...common} />
          {[52, 70, 88, 106].flatMap((y) => [52, 76].map((x) => window(x, y)))}
          {[36, 54, 72, 90].flatMap((y) => [108, 134].map((x) => window(x, y)))}
          <rect x="118" y="112" width="18" height="20" {...common} />
          <path d="M20 132 H180" {...common} />
        </>
      );
  }
  return (
    <div className={`grid place-items-center bg-registry-tint ${className}`} aria-hidden>
      <svg viewBox="0 0 200 150" className="h-3/5 w-3/5 opacity-70">{art}</svg>
    </div>
  );
}
