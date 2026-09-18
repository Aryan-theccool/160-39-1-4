"use client";

import { FileText, Loader2, UploadCloud, X } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const MAX_BYTES = 10 * 1024 * 1024; // matches BIS_MAX_PDF_BYTES

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} kB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UploadDropzone({
  onFile,
  busy = false,
  file,
  onClear,
}: {
  onFile: (file: File) => void;
  busy?: boolean;
  file: File | null;
  onClear: () => void;
}) {
  const [dragging, setDragging] = React.useState(false);
  const [localError, setLocalError] = React.useState<string | null>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  /**
   * Checking the type and size here as well as on the server is not redundant.
   * The server check is the one that matters -- it cannot be bypassed -- but it
   * costs a 10 MB round trip to be told a file is too big, and the user waits
   * for it. This check is a courtesy; the server's is the truth.
   */
  function accept(candidate: File) {
    setLocalError(null);
    if (candidate.type && candidate.type !== "application/pdf") {
      setLocalError(`${candidate.name} is not a PDF. Upload a tender document or specification sheet.`);
      return;
    }
    if (candidate.size > MAX_BYTES) {
      setLocalError(
        `${candidate.name} is ${humanSize(candidate.size)}; the limit is 10.0 MB. Split it, or paste the text into a query instead.`,
      );
      return;
    }
    onFile(candidate);
  }

  if (file) {
    return (
      <div className="flex items-center gap-3 rounded-xl border bg-muted/40 p-4">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-tricolor-saffron/15 text-tricolor-saffron">
          <FileText className="h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{file.name}</p>
          <p className="text-xs text-muted-foreground">
            {humanSize(file.size)} · {busy ? "analysing…" : "ready"}
          </p>
        </div>
        {busy ? (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        ) : (
          <Button variant="ghost" size="icon" onClick={onClear} aria-label="Remove file">
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          const dropped = event.dataTransfer.files?.[0];
          if (dropped) accept(dropped);
        }}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
        role="button"
        tabIndex={0}
        aria-label="Upload a PDF tender document"
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-12 text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          dragging
            ? "border-tricolor-saffron bg-accent"
            : "border-border bg-muted/20 hover:border-tricolor-saffron/60 hover:bg-accent/40",
        )}
      >
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-tricolor-saffron/15 text-tricolor-saffron">
          <UploadCloud className="h-6 w-6" />
        </span>
        <div className="space-y-1">
          <p className="font-medium">Drop a tender or specification PDF here</p>
          <p className="text-sm text-muted-foreground">
            or click to browse · PDF only · up to 10 MB
          </p>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="hidden"
          onChange={(event) => {
            const selected = event.target.files?.[0];
            if (selected) accept(selected);
            event.target.value = ""; // re-selecting the same file must re-fire
          }}
        />
      </div>

      {localError ? (
        <p className="text-sm text-destructive" role="alert">
          {localError}
        </p>
      ) : null}
    </div>
  );
}
