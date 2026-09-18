"use client";

import { AlertTriangle, WifiOff } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ApiError } from "@/lib/api";

/**
 * Render an API failure using the API's own words.
 *
 * `detail` is never replaced with something generic. The API knows things this
 * component cannot -- which file is missing, how many bytes the upload was, how
 * many standards the corpus holds -- and every one of those details is a step
 * the user can take.
 */
export function ErrorBanner({ error }: { error: ApiError }) {
  const offline = error.code === "network_error";
  const unavailable = error.status === 503;

  return (
    <Alert variant={unavailable || offline ? "warning" : "destructive"}>
      {offline ? <WifiOff className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
      <AlertTitle>
        {offline
          ? "Cannot reach the API"
          : unavailable
            ? "The API has no data loaded"
            : `Request failed (${error.status || "no response"})`}
      </AlertTitle>
      <AlertDescription className="space-y-2">
        <p className="whitespace-pre-line">{error.message}</p>
        {error.requestId ? (
          <p className="font-mono text-xs opacity-70">request {error.requestId}</p>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}
