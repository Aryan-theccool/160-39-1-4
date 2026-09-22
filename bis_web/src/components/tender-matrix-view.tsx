"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  FileText,
  HelpCircle,
  Layers,
  Lightbulb,
  ListFilter,
  Loader2,
  Scale,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import * as React from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  TenderAnalysisResponse,
  downloadTenderReportDocx,
  downloadTenderReportPdf,
} from "@/lib/api";
import { cn } from "@/lib/utils";


interface TenderMatrixViewProps {
  analysis: TenderAnalysisResponse;
}

export function TenderMatrixView({ analysis }: TenderMatrixViewProps) {
  const [activeTab, setActiveTab] = React.useState<"matrix" | "standards" | "clauses" | "risks">("matrix");
  const [statusFilter, setStatusFilter] = React.useState<string>("ALL");
  const [downloadingDocx, setDownloadingDocx] = React.useState(false);
  const [downloadingPdf, setDownloadingPdf] = React.useState(false);
  const [exportMessage, setExportMessage] = React.useState<string | null>(null);

  const matrix = analysis.compliance_matrix;

  const handleDownloadDocx = async () => {
    try {
      setDownloadingDocx(true);
      setExportMessage(null);
      const filename = await downloadTenderReportDocx(analysis);
      setExportMessage(`Downloaded ${filename}`);
    } catch {
      setExportMessage("Failed to export Word document. Please try again.");
    } finally {
      setDownloadingDocx(false);
    }
  };

  const handleDownloadPdf = async () => {
    try {
      setDownloadingPdf(true);
      setExportMessage(null);
      const filename = await downloadTenderReportPdf(analysis);
      setExportMessage(`Downloaded ${filename}`);
    } catch {
      setExportMessage("Failed to export PDF document. Please try again.");
    } finally {
      setDownloadingPdf(false);
    }
  };

  const filteredEvaluations = React.useMemo(() => {
    if (!matrix?.requirement_evaluations) return [];
    if (statusFilter === "ALL") return matrix.requirement_evaluations;
    return matrix.requirement_evaluations.filter(
      (e) => e.status?.toUpperCase() === statusFilter.toUpperCase(),
    );
  }, [matrix, statusFilter]);

  const scorePct = matrix ? Math.round((matrix.compliance_score || 0) * 100) : 0;

  const getStatusBadge = (status: string) => {
    switch (status?.toUpperCase()) {
      case "COMPLIANT":
      case "PASS":
      case "APPLICABLE":
        return <Badge className="bg-emerald-600 hover:bg-emerald-700 text-white gap-1"><CheckCircle2 className="h-3 w-3" /> {status}</Badge>;
      case "PARTIAL":
      case "MEDIUM":
      case "CANDIDATE":
        return <Badge className="bg-amber-500 hover:bg-amber-600 text-white gap-1"><AlertTriangle className="h-3 w-3" /> {status}</Badge>;
      case "NON_COMPLIANT":
      case "FAIL":
      case "HIGH":
      case "CRITICAL":
      case "NOT_APPLICABLE":
        return <Badge variant="destructive" className="gap-1"><XCircle className="h-3 w-3" /> {status}</Badge>;
      default:
        return <Badge variant="secondary" className="gap-1"><HelpCircle className="h-3 w-3" /> {status || "UNKNOWN"}</Badge>;
    }
  };

  const getRiskBadge = (risk: string) => {
    switch (risk?.toUpperCase()) {
      case "LOW":
        return <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"><ShieldCheck className="h-3 w-3" /> LOW RISK</span>;
      case "MEDIUM":
        return <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300"><AlertTriangle className="h-3 w-3" /> MEDIUM RISK</span>;
      case "HIGH":
      case "CRITICAL":
        return <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300"><ShieldAlert className="h-3 w-3" /> {risk.toUpperCase()} RISK</span>;
      default:
        return <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300"><HelpCircle className="h-3 w-3" /> {risk || "UNKNOWN"}</span>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Executive Summary Header */}
      <Card className="border-border/60 shadow-sm bg-gradient-to-br from-card via-card to-muted/20">
        <CardHeader className="pb-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs uppercase tracking-wider font-semibold text-muted-foreground">
                  Tender Assessment
                </span>
                {matrix && getStatusBadge(matrix.overall_status)}
                {matrix && getRiskBadge(matrix.risk_level)}
              </div>
              <CardTitle className="text-xl sm:text-2xl font-bold tracking-tight">
                {matrix?.tender_title || analysis.filename || "Tender Document Analysis"}
              </CardTitle>
              {matrix?.product_type && (
                <CardDescription className="text-sm font-medium">
                  Identified Product Domain: <span className="text-foreground capitalize">{matrix.product_type}</span>
                </CardDescription>
              )}
            </div>

            {/* Export Actions */}
            <div className="flex flex-wrap items-center gap-2.5">
              <Button
                variant="outline"
                size="sm"
                className="gap-2 border-primary/20 hover:border-primary/50 text-foreground"
                disabled={downloadingDocx}
                onClick={handleDownloadDocx}
              >
                {downloadingDocx ? (
                  <Loader2 className="h-4 w-4 animate-spin text-primary" />
                ) : (
                  <FileText className="h-4 w-4 text-blue-600" />
                )}
                <span>Word (.docx)</span>
              </Button>

              <Button
                variant="default"
                size="sm"
                className="gap-2 bg-gradient-to-r from-blue-700 to-indigo-700 hover:from-blue-800 hover:to-indigo-800 text-white shadow"
                disabled={downloadingPdf}
                onClick={handleDownloadPdf}
              >
                {downloadingPdf ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Download className="h-4 w-4" />
                )}
                <span>PDF Report</span>
              </Button>
            </div>
          </div>

          {exportMessage && (
            <p className="text-xs text-muted-foreground mt-2">
              {exportMessage}
            </p>
          )}
        </CardHeader>

        <CardContent className="pt-0">
          {/* Key Metrics Strip */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 pt-2 border-t">
            <div className="p-3 rounded-lg bg-muted/40 border text-center">
              <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Compliance Score</p>
              <p className="text-xl font-bold text-foreground mt-0.5">{scorePct}%</p>
            </div>
            <div className="p-3 rounded-lg bg-muted/40 border text-center">
              <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Clauses Parsed</p>
              <p className="text-xl font-bold text-foreground mt-0.5">{analysis.clauses?.length ?? matrix?.total_clauses ?? 0}</p>
            </div>
            <div className="p-3 rounded-lg bg-muted/40 border text-center">
              <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Requirements</p>
              <p className="text-xl font-bold text-foreground mt-0.5">{analysis.requirements?.length ?? matrix?.total_requirements ?? 0}</p>
            </div>
            <div className="p-3 rounded-lg bg-muted/40 border text-center">
              <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Standards Cited</p>
              <p className="text-xl font-bold text-foreground mt-0.5">{matrix?.standards_assessed?.length ?? analysis.standards_detected?.length ?? 0}</p>
            </div>
            <div className="p-3 rounded-lg bg-muted/40 border text-center">
              <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Pages / Format</p>
              <p className="text-xl font-bold text-foreground mt-0.5">{analysis.pages || 1} <span className="text-xs font-normal text-muted-foreground">({analysis.document_type.toUpperCase()})</span></p>
            </div>
            <div className="p-3 rounded-lg bg-muted/40 border text-center">
              <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Processing Time</p>
              <p className="text-xl font-bold text-foreground mt-0.5">{Math.round(analysis.processing_time_ms)} <span className="text-xs font-normal text-muted-foreground">ms</span></p>
            </div>
          </div>

          {/* Executive Summary Narrative */}
          {matrix?.summary && (
            <div className="mt-4 p-4 rounded-xl bg-muted/30 border text-sm text-foreground/90 space-y-2">
              <p className="font-semibold text-xs uppercase tracking-wider text-muted-foreground">Executive Overview</p>
              <p className="leading-relaxed whitespace-pre-line">{matrix.summary}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Navigation Tabs */}
      <div className="flex border-b border-border space-x-1 sm:space-x-2">
        <button
          onClick={() => setActiveTab("matrix")}
          className={cn(
            "px-4 py-2.5 text-sm font-semibold border-b-2 transition-all flex items-center gap-2",
            activeTab === "matrix"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          <FileSpreadsheet className="h-4 w-4" />
          <span>Compliance Matrix</span>
          {matrix?.requirement_evaluations && (
            <span className="ml-1 px-2 py-0.5 text-xs rounded-full bg-muted font-normal">
              {matrix.requirement_evaluations.length}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab("standards")}
          className={cn(
            "px-4 py-2.5 text-sm font-semibold border-b-2 transition-all flex items-center gap-2",
            activeTab === "standards"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          <Scale className="h-4 w-4" />
          <span>Applicable Standards</span>
          {matrix?.standards_assessed && (
            <span className="ml-1 px-2 py-0.5 text-xs rounded-full bg-muted font-normal">
              {matrix.standards_assessed.length}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab("clauses")}
          className={cn(
            "px-4 py-2.5 text-sm font-semibold border-b-2 transition-all flex items-center gap-2",
            activeTab === "clauses"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          <Layers className="h-4 w-4" />
          <span>Extracted Clauses</span>
          {analysis.clauses && (
            <span className="ml-1 px-2 py-0.5 text-xs rounded-full bg-muted font-normal">
              {analysis.clauses.length}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab("risks")}
          className={cn(
            "px-4 py-2.5 text-sm font-semibold border-b-2 transition-all flex items-center gap-2",
            activeTab === "risks"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          <ShieldAlert className="h-4 w-4" />
          <span>Risks & Recommendations</span>
          {(matrix?.key_risks?.length || matrix?.recommendations?.length) ? (
            <span className="ml-1 px-2 py-0.5 text-xs rounded-full bg-rose-500/10 text-rose-600 font-semibold">
              {(matrix?.key_risks?.length || 0) + (matrix?.recommendations?.length || 0)}
            </span>
          ) : null}
        </button>
      </div>

      {/* Tab 1: Compliance Matrix Table */}
      {activeTab === "matrix" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-1.5">
              <ListFilter className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs font-medium text-muted-foreground">Filter by status:</span>
              <div className="flex gap-1">
                {["ALL", "PASS", "FAIL", "UNKNOWN"].map((status) => (
                  <button
                    key={status}
                    onClick={() => setStatusFilter(status)}
                    className={cn(
                      "px-2.5 py-1 text-xs rounded-md font-medium transition-colors",
                      statusFilter === status
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted text-muted-foreground hover:bg-muted/80",
                    )}
                  >
                    {status}
                  </button>
                ))}
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Showing {filteredEvaluations.length} of {matrix?.requirement_evaluations?.length || 0} evaluated requirements
            </p>
          </div>

          <div className="rounded-xl border bg-card overflow-hidden shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-muted/60 text-xs font-semibold text-muted-foreground uppercase border-b">
                  <tr>
                    <th className="px-4 py-3 w-16">ID</th>
                    <th className="px-4 py-3 w-44">Parameter</th>
                    <th className="px-4 py-3 w-40">Tender Spec</th>
                    <th className="px-4 py-3 w-36">Standard Ref</th>
                    <th className="px-4 py-3">Standard Requirement</th>
                    <th className="px-4 py-3 w-28 text-center">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filteredEvaluations.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground text-sm">
                        No technical requirements match the selected filter.
                      </td>
                    </tr>
                  ) : (
                    filteredEvaluations.map((ev, idx) => (
                      <tr key={ev.req_id || idx} className="hover:bg-muted/20 transition-colors">
                        <td className="px-4 py-3.5 font-mono text-xs text-muted-foreground align-top">
                          {ev.req_id}
                        </td>
                        <td className="px-4 py-3.5 font-semibold text-foreground align-top">
                          {ev.parameter}
                        </td>
                        <td className="px-4 py-3.5 font-medium text-foreground/90 align-top">
                          {ev.specified_value || "—"}
                        </td>
                        <td className="px-4 py-3.5 font-mono text-xs text-primary align-top">
                          {ev.standard_code || "—"}
                        </td>
                        <td className="px-4 py-3.5 space-y-1 align-top">
                          <p className="text-xs text-foreground/90 font-medium">
                            {ev.standard_requirement || "No confirmed standard requirement"}
                          </p>
                          {ev.reason && (
                            <p className="text-xs text-muted-foreground italic">
                              {ev.reason}
                            </p>
                          )}
                          {ev.clause_reference && (
                            <p className="text-[11px] font-mono text-muted-foreground">
                              Ref: {ev.clause_reference}
                            </p>
                          )}
                        </td>
                        <td className="px-4 py-3.5 text-center align-top">
                          {getStatusBadge(ev.status)}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Standards Assessment */}
      {activeTab === "standards" && (
        <div className="grid gap-4 sm:grid-cols-2">
          {(matrix?.standards_assessed || []).length === 0 ? (
            <div className="col-span-2 p-8 text-center border rounded-xl bg-card text-muted-foreground">
              No Indian Standards were evaluated in this document.
            </div>
          ) : (
            matrix?.standards_assessed.map((std, idx) => (
              <Card key={std.standard_code || idx} className="border bg-card shadow-sm hover:border-primary/40 transition-colors">
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="space-y-1">
                      <CardTitle className="text-base font-bold font-mono text-primary">
                        {std.standard_code}
                      </CardTitle>
                      {std.qco_evidence_state && (
                        <Badge
                          variant={
                            std.qco_evidence_state === "VERIFIED"
                              ? "success"
                              : std.qco_evidence_state === "SUPERSEDED_OR_CHANGED"
                              ? "warning"
                              : std.qco_evidence_state === "NOT_APPLICABLE"
                              ? "outline"
                              : "secondary"
                          }
                          className="text-[10px]"
                        >
                          {std.qco_evidence_state === "VERIFIED"
                            ? "✓ Verified QCO evidence"
                            : std.qco_evidence_state === "SUPERSEDED_OR_CHANGED"
                            ? "↻ Regulatory status changed"
                            : std.qco_evidence_state === "NOT_APPLICABLE"
                            ? "○ QCO not applicable"
                            : std.qco_evidence_state === "AMBIGUOUS"
                            ? "⚠ QCO applicability ambiguous"
                            : std.qco_evidence_state === "NOT_FOUND"
                            ? "⚠ No verified QCO evidence found"
                            : "⚠ Unverified QCO seed"}
                        </Badge>
                      )}
                    </div>
                    {getStatusBadge(std.status)}
                  </div>
                </CardHeader>
                <CardContent className="space-y-2.5 text-xs text-muted-foreground">
                  {std.scope_summary && (
                    <p className="text-foreground/90 font-medium">
                      <span className="font-semibold text-muted-foreground">Scope: </span>
                      {std.scope_summary}
                    </p>
                  )}
                  {std.reason && (
                    <p className="bg-muted/40 p-2.5 rounded-lg border">
                      <span className="font-semibold text-foreground">Assessment: </span>
                      {std.reason}
                    </p>
                  )}
                  {std.relevance_score > 0 && (
                    <p className="text-[11px] text-muted-foreground">
                      Relevance match: {Math.round(std.relevance_score * 100)}%
                    </p>
                  )}
                </CardContent>
              </Card>
            ))
          )}
        </div>
      )}

      {/* Tab 3: Extracted Clauses */}
      {activeTab === "clauses" && (
        <div className="space-y-3">
          {(analysis.clauses || []).length === 0 ? (
            <div className="p-8 text-center border rounded-xl bg-card text-muted-foreground">
              No specific clause blocks were detected in this document.
            </div>
          ) : (
            analysis.clauses.map((clause, idx) => (
              <Card key={clause.clause_id || idx} className="border bg-card">
                <CardContent className="p-4 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-bold px-2 py-0.5 rounded bg-muted">
                        {clause.clause_id}
                      </span>
                      <h4 className="font-semibold text-sm text-foreground">
                        {clause.heading || "Clause Specification"}
                      </h4>
                    </div>
                    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      {clause.page_number > 0 && <span>Page {clause.page_number}</span>}
                      {clause.is_mandatory && (
                        <Badge variant="outline" className="text-[10px] text-amber-600 border-amber-500/40">
                          Mandatory
                        </Badge>
                      )}
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-line bg-muted/20 p-3 rounded-lg border font-mono">
                    {clause.text}
                  </p>
                  {clause.standards_referenced?.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 pt-1">
                      <span className="text-[11px] font-semibold text-muted-foreground">Cited:</span>
                      {clause.standards_referenced.map((s) => (
                        <Badge key={s} variant="secondary" className="font-mono text-[10px]">
                          {s}
                        </Badge>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))
          )}
        </div>
      )}

      {/* Tab 4: Risks & Recommendations */}
      {activeTab === "risks" && (
        <div className="space-y-6">
          {matrix?.key_risks && matrix.key_risks.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
                <ShieldAlert className="h-5 w-5 text-rose-500" />
                Key Compliance & Procurement Risks
              </h3>
              <div className="grid gap-3">
                {matrix.key_risks.map((risk, idx) => (
                  <Alert key={idx} variant="destructive" className="border-rose-500/30 bg-rose-500/5">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertTitle className="text-xs uppercase font-bold tracking-wide">Risk Flag #{idx + 1}</AlertTitle>
                    <AlertDescription className="text-sm font-medium mt-1">
                      {risk}
                    </AlertDescription>
                  </Alert>
                ))}
              </div>
            </div>
          )}

          {matrix?.recommendations && matrix.recommendations.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
                <Lightbulb className="h-5 w-5 text-amber-500" />
                Actionable Recommendations
              </h3>
              <div className="grid gap-2.5">
                {matrix.recommendations.map((rec, idx) => (
                  <div key={idx} className="flex items-start gap-3 p-3.5 rounded-xl border bg-card text-sm">
                    <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />
                    <span className="text-foreground/90 font-medium">{rec}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {(!matrix?.key_risks?.length && !matrix?.recommendations?.length) && (
            <div className="p-8 text-center border rounded-xl bg-card text-muted-foreground">
              No specific risk alerts or recommendations were generated for this document.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
