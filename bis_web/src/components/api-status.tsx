"use client";

import { AlertTriangle, CheckCircle2, Loader2, XCircle } from "lucide-react";
import * as React from "react";

import { health, type Health, type ServiceStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const STYLES: Record<ServiceStatus, { dot: string; icon: React.ElementType; label: string }> = {
  ok: { dot: "bg-emerald-500", icon: CheckCircle2, label: "API healthy" },
  degraded: { dot: "bg-amber-500", icon: AlertTriangle, label: "API degraded" },
  unavailable: { dot: "bg-red-500", icon: XCircle, label: "API unavailable" },
};

/**
 * The health pill in the header.
 *
 * It is always visible, not just when something is wrong, because "is the API
 * up" is the first question anyone opening this app has -- and answering it
 * from the header saves a click. The tooltip carries the actual problem (the
 * number of standards, or the exact issue the API reported) rather than a
 * generic status word.
 */
export function ApiStatus() {
  const [state, setState] = React.useState<Health | null>(null);
  const [failed, setFailed] = React.useState(false);

  React.useEffect(() => {
    let alive = true;
    health()
      .then((data) => {
        if (alive) setState(data);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  if (!state && !failed) {
    return (
      <span className="flex items-center gap-2 rounded-full border px-3 py-1 text-xs text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" />
        Checking API
      </span>
    );
  }

  const status: ServiceStatus = failed ? "unavailable" : state!.status;
  const style = STYLES[status];
  const Icon = style.icon;

  return (
    <TooltipProvider delayDuration={100}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={cn(
              "flex cursor-default items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium",
              status === "ok" && "border-emerald-200 bg-emerald-50 text-emerald-800",
              status === "degraded" && "border-amber-200 bg-amber-50 text-amber-800",
              status === "unavailable" && "border-red-200 bg-red-50 text-red-800",
            )}
          >
            <span className={cn("h-2 w-2 rounded-full", style.dot)} />
            {style.label}
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-sm">
          {failed ? (
            <span>
              Could not reach the API. Start it with{" "}
              <code className="font-mono">uvicorn bis_api.main:app --port 8000</code>.
            </span>
          ) : (
            <div className="space-y-1">
              <p className="font-medium">
                <Icon className="mr-1 inline h-3 w-3" />
                {state!.corpus.standards} standards · {state!.corpus.chunks} chunks
              </p>
              <p>
                {state!.retrieval.dense_enabled
                  ? `Semantic search on (${state!.retrieval.vectors} vectors)`
                  : "BM25 only — no vector store"}
              </p>
              <p>
                Answers: {state!.llm.is_llm ? state!.llm.provider : "extractive (no LLM key set)"}
              </p>
              {state!.issues.length > 0 && (
                <ul className="list-disc pl-4">
                  {state!.issues.slice(0, 3).map((issue) => (
                    <li key={issue}>{issue}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
