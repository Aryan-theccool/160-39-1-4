"use client";

import { FileSearch, Info } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { AnswerPanel } from "@/components/answer-panel";
import { ErrorBanner } from "@/components/error-banner";
import { PageHeader } from "@/components/page-header";
import { StandardCard } from "@/components/standard-card";
import { UploadDropzone } from "@/components/upload-dropzone";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ApiError,
  recommendPdf,
  search as searchApi,
  type PdfRecommendResponse,
  type SearchResponse,
} from "@/lib/api";

export default function UploadPage() {
  const [file, setFile] = React.useState<File | null>(null);
  const [analysis, setAnalysis] = React.useState<PdfRecommendResponse | null>(null);
  const [error, setError] = React.useState<ApiError | null>(null);
  const [busy, setBusy] = React.useState(false);

  /**
   * A designation found in the PDF is not automatically a designation the
   * corpus holds. Searching each one turns "this tender cites IS 9999" into
   * either a standard card or an honest "not in the dataset", which is exactly
   * the distinction a tender reviewer needs.
   */
  const [lookups, setLookups] = React.useState<Record<string, SearchResponse | null>>({});

  async function analyse(selected: File) {
    setFile(selected);
    setBusy(true);
    setError(null);
    setAnalysis(null);
    setLookups({});

    try {
      const result = await recommendPdf(selected, { top_k: 5 });
      setAnalysis(result);

      const detected = result.detected_designations ?? [];
      if (detected.length > 0) {
        // Sequential rather than parallel: this is a handful of requests against
        // a service that rate-limits per client, and getting throttled halfway
        // through would leave the panel half-filled with no explanation.
        const found: Record<string, SearchResponse | null> = {};
        for (const designation of detected) {
          try {
            found[designation] = await searchApi({ q: designation, limit: 2 });
          } catch {
            found[designation] = null;
          }
        }
        setLookups(found);
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, "unknown_error", String(caught)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={FileSearch}
        title="Tender analysis"
        description="Upload a tender document or specification sheet. Every Indian Standard it cites is extracted, then looked up in the corpus so you can see what you would actually have to comply with."
      />

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">1. Upload the document</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <UploadDropzone
            file={file}
            busy={busy}
            onFile={analyse}
            onClear={() => {
              setFile(null);
              setAnalysis(null);
              setError(null);
              setLookups({});
            }}
          />
          <p className="text-xs text-muted-foreground">
            <Info className="mr-1 inline h-3 w-3" />
            A scanned document has no text layer, so nothing can be read from it and
            the API says so rather than returning an empty result.
          </p>
        </CardContent>
      </Card>

      {error ? <ErrorBanner error={error} /> : null}

      {busy ? (
        <div className="space-y-3">
          <Skeleton className="h-48 w-full" />
          <p className="text-center text-sm text-muted-foreground">
            Extracting text and retrieving relevant standards…
          </p>
        </div>
      ) : null}

      {analysis ? (
        <div className="space-y-6">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">2. What was read from the file</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-4">
                <Stat label="Pages" value={String(analysis.source_document.pages || "—")} />
                <Stat label="Characters read" value={analysis.source_document.chars.toLocaleString("en-IN")} />
                <Stat label="Extractor" value={analysis.source_document.extractor} />
                <Stat label="Time" value={`${Math.round(analysis.took_ms)} ms`} />
              </div>

              {analysis.source_document.warnings.length > 0 ? (
                <Alert variant="warning">
                  <Info className="h-4 w-4" />
                  <AlertDescription>
                    <ul className="list-disc space-y-0.5 pl-4">
                      {analysis.source_document.warnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  </AlertDescription>
                </Alert>
              ) : null}

              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Indian Standards cited in this document (
                  {analysis.detected_designations?.length ?? 0})
                </p>
                {(analysis.detected_designations?.length ?? 0) === 0 ? (
                  <Alert>
                    <Info className="h-4 w-4" />
                    <AlertTitle>No IS codes found</AlertTitle>
                    <AlertDescription>
                      The document was read successfully but does not name any standard in
                      a recognisable form. The answer below is based on its contents
                      rather than on specific codes.
                    </AlertDescription>
                  </Alert>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {analysis.detected_designations!.map((designation) => {
                      const hit = lookups[designation];
                      const matched = hit?.results?.[0];
                      const inCorpus = Boolean(
                        matched &&
                          matched.designation.replace(/\s/g, "").startsWith(
                            designation.replace(/\s/g, ""),
                          ),
                      );
                      return (
                        <Link
                          key={designation}
                          href={`/standards?q=${encodeURIComponent(designation)}`}
                          title={inCorpus ? matched!.title : "Not found in the indexed corpus"}
                        >
                          <Badge
                            variant={inCorpus ? "success" : "outline"}
                            className="gap-1 font-mono"
                          >
                            {designation}
                            {!inCorpus ? (
                              <span className="font-sans opacity-70">· not indexed</span>
                            ) : null}
                          </Badge>
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          <div className="space-y-3">
            <h2 className="text-lg font-semibold">3. Answer and sources</h2>
            <AnswerPanel answer={analysis} />
          </div>

          {(analysis.detected_designations?.length ?? 0) > 0 ? (
            <div className="space-y-3">
              <h2 className="text-lg font-semibold">
                4. Closest indexed standards for each cited code
              </h2>
              {analysis.detected_designations!.map((designation) => {
                const hit = lookups[designation];
                if (!hit || hit.results.length === 0) {
                  return (
                    <Card key={designation}>
                      <CardContent className="flex flex-wrap items-center gap-3 p-4">
                        <Badge variant="outline" className="font-mono">
                          {designation}
                        </Badge>
                        <p className="text-sm text-muted-foreground">
                          Not present in the indexed corpus. It may exist and simply not
                          be in this dataset — the corpus is a subset of BIS&apos;s catalogue.
                        </p>
                      </CardContent>
                    </Card>
                  );
                }
                return (
                  <StandardCard
                    key={designation}
                    result={hit.results[0]}
                    results={hit.results}
                    rank={1}
                  />
                );
              })}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-muted/30 px-3 py-2">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="truncate text-sm font-semibold capitalize">{value}</p>
    </div>
  );
}
