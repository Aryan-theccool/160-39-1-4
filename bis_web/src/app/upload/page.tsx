"use client";

import { FileSearch, FileText, Info, Send, UploadCloud } from "lucide-react";
import * as React from "react";

import { ErrorBanner } from "@/components/error-banner";
import { PageHeader } from "@/components/page-header";
import { TenderMatrixView } from "@/components/tender-matrix-view";
import { UploadDropzone } from "@/components/upload-dropzone";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  analyzeTenderFile,
  analyzeTenderText,
  type TenderAnalysisResponse,
} from "@/lib/api";
import { cn } from "@/lib/utils";

export default function UploadPage() {
  const [mode, setMode] = React.useState<"file" | "text">("file");
  const [file, setFile] = React.useState<File | null>(null);
  const [productType, setProductType] = React.useState("");
  const [tenderTitle, setTenderTitle] = React.useState("");
  const [tenderText, setTenderText] = React.useState("");
  const [analysis, setAnalysis] = React.useState<TenderAnalysisResponse | null>(null);
  const [error, setError] = React.useState<ApiError | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function handleAnalyzeFile(selected: File) {
    setFile(selected);
    setBusy(true);
    setError(null);
    setAnalysis(null);

    try {
      const result = await analyzeTenderFile(selected, {
        product_type: productType.trim() || undefined,
      });
      setAnalysis(result);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, "unknown_error", String(caught)));
    } finally {
      setBusy(false);
    }
  }

  async function handleAnalyzeText(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!tenderText.trim()) return;

    setBusy(true);
    setError(null);
    setAnalysis(null);

    try {
      const result = await analyzeTenderText({
        tender_text: tenderText.trim(),
        title: tenderTitle.trim() || "Pasted Tender Document",
        product_type: productType.trim() || undefined,
      });
      setAnalysis(result);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, "unknown_error", String(caught)));
    } finally {
      setBusy(false);
    }
  }

  const handleClear = () => {
    setFile(null);
    setTenderText("");
    setTenderTitle("");
    setProductType("");
    setAnalysis(null);
    setError(null);
  };

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <PageHeader
        icon={FileSearch}
        title="Tender Compliance Analysis"
        description="Ingest multi-format tender documents (PDF, DOCX, TXT) or paste raw specification text. The engine parses clauses, extracts technical parameters, checks BIS standards applicability, and computes a full compliance matrix."
      />

      {/* Input Options Card */}
      <Card className="border shadow-sm">
        <CardHeader className="pb-3 border-b bg-muted/20">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base">Document Ingestion & Parameters</CardTitle>
              <CardDescription className="text-xs">
                Choose between file upload or direct specification pasting
              </CardDescription>
            </div>
            {/* Mode Switcher */}
            <div className="flex bg-muted p-1 rounded-lg">
              <button
                type="button"
                onClick={() => setMode("file")}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md transition-all",
                  mode === "file"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <UploadCloud className="h-3.5 w-3.5" />
                Upload File
              </button>
              <button
                type="button"
                onClick={() => setMode("text")}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md transition-all",
                  mode === "text"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <FileText className="h-3.5 w-3.5" />
                Paste Text
              </button>
            </div>
          </div>
        </CardHeader>

        <CardContent className="space-y-4 pt-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                Product Domain (Optional)
              </label>
              <Input
                placeholder="e.g. LED Street Light, Cement, Solar Inverter"
                value={productType}
                onChange={(e) => setProductType(e.target.value)}
                className="h-9 text-sm"
              />
            </div>
            {mode === "text" && (
              <div className="space-y-1">
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                  Tender Title (Optional)
                </label>
                <Input
                  placeholder="e.g. Municipal Street Lighting Tender 2026"
                  value={tenderTitle}
                  onChange={(e) => setTenderTitle(e.target.value)}
                  className="h-9 text-sm"
                />
              </div>
            )}
          </div>

          {mode === "file" ? (
            <div className="space-y-3">
              <UploadDropzone
                file={file}
                busy={busy}
                onFile={handleAnalyzeFile}
                onClear={handleClear}
              />
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                <Info className="h-3.5 w-3.5 shrink-0" />
                Supports PDF, Microsoft Word (.docx), and plain text (.txt). Scanned PDFs must contain a readable text layer.
              </p>
            </div>
          ) : (
            <form onSubmit={handleAnalyzeText} className="space-y-3">
              <Textarea
                placeholder="Paste tender clauses, technical specifications, or BOQ requirements here... (e.g., 'Clause 4.1: The LED luminaires shall have luminous efficacy >= 130 lm/W and comply with IS 10322 (Part 5/Sec 3)...')"
                rows={7}
                value={tenderText}
                onChange={(e) => setTenderText(e.target.value)}
                className="text-sm font-mono leading-relaxed resize-y"
              />
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">
                  {tenderText.length} characters
                </span>
                <div className="flex gap-2">
                  {tenderText && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={handleClear}
                      disabled={busy}
                    >
                      Clear
                    </Button>
                  )}
                  <Button
                    type="submit"
                    size="sm"
                    className="gap-2"
                    disabled={busy || !tenderText.trim()}
                  >
                    <Send className="h-3.5 w-3.5" />
                    Analyze Tender Specifications
                  </Button>
                </div>
              </div>
            </form>
          )}
        </CardContent>
      </Card>

      {error ? <ErrorBanner error={error} /> : null}

      {busy ? (
        <div className="space-y-4 py-8">
          <Skeleton className="h-32 w-full rounded-xl" />
          <div className="space-y-2 text-center">
            <p className="text-sm font-medium text-foreground animate-pulse">
              Extracting clauses, identifying technical parameters, and evaluating BIS standards compliance…
            </p>
            <p className="text-xs text-muted-foreground">
              Checking scope bounds, QCO status, and standard requirements
            </p>
          </div>
          <Skeleton className="h-64 w-full rounded-xl" />
        </div>
      ) : null}

      {analysis ? (
        <div className="space-y-6 animate-fade-in">
          <TenderMatrixView analysis={analysis} />
        </div>
      ) : null}
    </div>
  );
}
