"use client";

import { Search, X } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const EXAMPLES = [
  "ordinary portland cement 33 grade",
  "drinking water quality limits",
  "steel tubes for water supply",
  "concrete mix design",
];

/**
 * The search input. Home uses the `hero` size; the results page uses `inline`
 * and reflects the live query rather than redirecting on submit, so refining a
 * search does not add a history entry per keystroke.
 */
export function SearchBar({
  size = "hero",
  initialValue = "",
  onSubmit,
  showExamples = false,
  busy = false,
}: {
  size?: "hero" | "inline";
  initialValue?: string;
  onSubmit: (query: string) => void;
  showExamples?: boolean;
  busy?: boolean;
}) {
  const [value, setValue] = React.useState(initialValue);
  const router = useRouter();

  // Keep the box in sync when the URL changes underneath it (browser back).
  React.useEffect(() => {
    setValue(initialValue);
  }, [initialValue]);

  function submit(query: string) {
    const trimmed = query.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
  }

  const hero = size === "hero";

  return (
    <div className="w-full space-y-3">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          submit(value);
        }}
        className={cn("relative flex w-full items-center", hero ? "gap-2" : "gap-2")}
      >
        <div className="relative flex-1">
          <Search
            className={cn(
              "pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground",
              hero ? "h-5 w-5" : "h-4 w-4",
            )}
          />
          <input
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="Search 197 Indian Standards — by product, material or IS code"
            aria-label="Search Indian Standards"
            autoComplete="off"
            className={cn(
              "w-full rounded-xl border bg-background shadow-sm outline-none transition-all placeholder:text-muted-foreground focus:border-tricolor-saffron focus:ring-4 focus:ring-tricolor-saffron/15",
              hero ? "h-14 pl-12 pr-10 text-base" : "h-11 pl-10 pr-9 text-sm",
            )}
          />
          {value ? (
            <button
              type="button"
              onClick={() => setValue("")}
              aria-label="Clear search"
              className="absolute right-3 top-1/2 -translate-y-1/2 rounded-full p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          ) : null}
        </div>
        <Button
          type="submit"
          size={hero ? "lg" : "default"}
          disabled={busy}
          className={cn("shrink-0", hero && "h-14 px-7 text-base")}
        >
          {busy ? "Searching…" : "Search"}
        </Button>
      </form>

      {showExamples ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">Try:</span>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => {
                setValue(example);
                router.push(`/search?q=${encodeURIComponent(example)}`);
              }}
              className="rounded-full border bg-muted/50 px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-tricolor-saffron hover:bg-accent hover:text-accent-foreground"
            >
              {example}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
