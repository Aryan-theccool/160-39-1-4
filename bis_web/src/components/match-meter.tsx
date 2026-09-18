"use client";

import { cn } from "@/lib/utils";

/**
 * A horizontal match-strength bar for a search result.
 *
 * The wording is deliberate. The API returns rank-fusion scores, not
 * probabilities, so this says "match strength, relative to the best hit" and
 * the number is a *share of the top score* -- not a confidence percentage. A
 * card reading "94% confident" next to an IS code would be the most misleading
 * element in this app, because it would be a number nothing computed.
 */
export function MatchMeter({
  value,
  className,
  label = true,
}: {
  value: number;
  className?: string;
  label?: boolean;
}) {
  const pct = Math.round(value * 100);
  const tone =
    pct >= 80 ? "bg-emerald-500" : pct >= 50 ? "bg-tricolor-saffron" : "bg-slate-400";

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full rounded-full transition-all", tone)}
          style={{ width: `${Math.max(4, pct)}%` }}
        />
      </div>
      {label ? (
        <span className="whitespace-nowrap text-xs text-muted-foreground">
          {pct}% of best
        </span>
      ) : null}
    </div>
  );
}
