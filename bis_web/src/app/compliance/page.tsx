"use client";

import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Info,
  ListChecks,
  Plus,
  ShieldCheck,
  X,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { ErrorBanner } from "@/components/error-banner";
import { PageHeader } from "@/components/page-header";
import { ScoreGauge } from "@/components/score-gauge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  complianceCheck,
  gapReportUrl,
  type ComplianceResult,
} from "@/lib/api";
import { formatMs, gradeStyle } from "@/lib/format";

const EXAMPLES = [
  "33 grade ordinary Portland cement",
  "household electrical appliance",
  "unplasticized PVC pipes for potable water",
];

export default function CompliancePage() {
  const [product, setProduct] = React.useState("");
  const [standards, setStandards] = React.useState<string[]>([]);
  const [draft, setDraft] = React.useState("");
  const [report, setReport] = React.useState<ComplianceResult | null>(null);
  const [error, setError] = React.useState<ApiError | null>(null);
  const [busy, setBusy] = React.useState(false);

  function addStandard() {
    const value = draft.trim();
    if (!value) return;
    // De-duplicate case-insensitively: "is 269" and "IS 269" are the same input
    // to the API, and letting both through produces a confusing double row.
    if (!standards.some((existing) => existing.toLowerCase() === value.toLowerCase())) {
      setStandards((prev) => [...prev, value]);
    }
    setDraft("");
  }

  async function check() {
    if (!product.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setReport(
        await complianceCheck({
          product_description: product.trim(),
          standards: standards.length > 0 ? standards : undefined,
        }),
      );
    } catch (caught) {
      setReport(null);
      setError(caught instanceof ApiError ? caught : new ApiError(0, "unknown_error", String(caught)));
    } finally {
      setBusy(false);
    }
  }

  const style = report ? gradeStyle(report.grade) : null;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={ShieldCheck}
        title="Compliance check"
        description="Score a product against the BIS Quality Control Order mandatory list. Provide the standards you hold, or leave them out and let the retriever propose what applies."
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
        {/* ---- input ---- */}
        <Card className="h-fit">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Product and standards</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="product">Product description</Label>
              <Textarea
                id="product"
                value={product}
                onChange={(event) => setProduct(event.target.value)}
                placeholder="e.g. 33 grade ordinary Portland cement"
                rows={2}
              />
              <div className="flex flex-wrap gap-2">
                {EXAMPLES.map((example) => (
                  <button
                    key={example}
                    type="button"
                    onClick={() => setProduct(example)}
                    className="rounded-full border bg-muted/50 px-2.5 py-0.5 text-xs text-muted-foreground hover:border-tricolor-saffron hover:text-foreground"
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="standard">Standards you hold (optional)</Label>
              <div className="flex gap-2">
                <Input
                  id="standard"
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      addStandard();
                    }
                  }}
                  placeholder="IS 269:1989"
                  className="font-mono"
                />
                <Button type="button" variant="outline" size="icon" onClick={addStandard} aria-label="Add standard">
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
              {standards.length > 0 ? (
                <div className="flex flex-wrap gap-2 pt-1">
                  {standards.map((standard) => (
                    <Badge key={standard} variant="muted" className="gap-1 font-mono">
                      {standard}
                      <button
                        type="button"
                        onClick={() => setStandards((prev) => prev.filter((s) => s !== standard))}
                        aria-label={`Remove ${standard}`}
                        className="ml-0.5 rounded-full hover:text-destructive"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Leave empty and the retriever will propose standards for the product
                  description. Those proposals are marked as such, never as fact.
                </p>
              )}
            </div>

            <Button onClick={check} disabled={busy || !product.trim()} className="w-full">
              {busy ? "Checking…" : "Check compliance"}
            </Button>
          </CardContent>
        </Card>

        {/* ---- result ---- */}
        <div className="space-y-4">
          {error ? <ErrorBanner error={error} /> : null}

          {busy ? <Skeleton className="h-80 w-full" /> : null}

          {!busy && !report && !error ? (
            <Card className="border-dashed bg-muted/20">
              <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
                <ShieldCheck className="h-8 w-8 text-muted-foreground/60" />
                <p className="font-medium">No check run yet</p>
                <p className="max-w-sm text-sm text-muted-foreground">
                  Enter a product description and press <strong>Check compliance</strong> to
                  score it against the mandatory list.
                </p>
              </CardContent>
            </Card>
          ) : null}

          {!busy && report ? (
            <>
              <Card>
                <CardContent className="grid gap-6 p-6 sm:grid-cols-[auto_1fr] sm:items-center">
                  <ScoreGauge
                    score={report.compliance_score}
                    color={style!.ring}
                    label={report.grade}
                    sublabel={`${report.sector} sector · ${report.qco_size} QCO entries`}
                  />
                  <div className="space-y-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge className={style!.badge}>{report.grade}</Badge>
                      <Badge variant="muted">{report.compliance_status}</Badge>
                      <span className="text-xs text-muted-foreground">
                        computed in {formatMs(report.took_ms)}
                      </span>
                    </div>

                    <div className="grid grid-cols-3 gap-2 text-center">
                      <Counter
                        label="Mandatory met"
                        value={report.mandatory_present.length}
                        tone="good"
                      />
                      <Counter
                        label="Mandatory missing"
                        value={report.mandatory_missing.length}
                        tone={report.mandatory_missing.length > 0 ? "bad" : "plain"}
                      />
                      <Counter
                        label="Superseded used"
                        value={report.superseded_used.length}
                        tone={report.superseded_used.length > 0 ? "warn" : "plain"}
                      />
                    </div>

                    {/* The score is only meaningful with its weights shown. */}
                    <p className="text-xs text-muted-foreground">
                      Score ={" "}
                      {Object.entries(report.weights)
                        .map(([key, weight]) => `${key} ${Math.round(weight * 100)}%`)
                        .join(" + ")}
                      {report.weights_redistributed
                        ? " (re-weighted: no mandatory standard could be identified for this product)"
                        : ""}
                    </p>
                  </div>
                </CardContent>
              </Card>

              {report.grade_capped_by ? (
                <Alert variant="warning">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertTitle>Grade capped</AlertTitle>
                  <AlertDescription>{report.grade_capped_by}</AlertDescription>
                </Alert>
              ) : null}

              {report.action_items.length > 0 ? (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <ListChecks className="h-4 w-4 text-tricolor-saffron" />
                      Action items
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ol className="space-y-2">
                      {report.action_items.map((item, index) => (
                        <li key={item} className="flex gap-3 text-sm">
                          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold">
                            {index + 1}
                          </span>
                          <span className="leading-relaxed">{item}</span>
                        </li>
                      ))}
                    </ol>
                  </CardContent>
                </Card>
              ) : null}

              <div className="grid gap-4 sm:grid-cols-2">
                <StatusList
                  title="Mandatory standards met"
                  icon={CheckCircle2}
                  tone="good"
                  items={report.mandatory_present}
                  empty="None identified for this product."
                />
                <StatusList
                  title="Mandatory standards missing"
                  icon={XCircle}
                  tone="bad"
                  items={report.mandatory_missing}
                  empty="Nothing missing."
                />
              </div>

              {report.superseded_used.length > 0 ? (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <AlertTriangle className="h-4 w-4 text-amber-500" />
                      Superseded editions in use
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {report.superseded_used.map((row) => (
                      <div
                        key={row.used}
                        className="flex flex-wrap items-center gap-2 rounded-md border bg-amber-50/60 px-3 py-2 text-sm"
                      >
                        <span className="font-mono line-through decoration-amber-500">
                          {row.used}
                        </span>
                        <span className="text-muted-foreground">→ replace with</span>
                        <span className="font-mono font-semibold text-emerald-700">
                          {row.replace_with}
                        </span>
                        {!row.replacement_in_dataset ? (
                          <Badge variant="outline">replacement not in corpus</Badge>
                        ) : null}
                      </div>
                    ))}
                  </CardContent>
                </Card>
              ) : null}

              {(report.mandatory_candidates.length > 0 || report.sector_candidates.length > 0) ? (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Info className="h-4 w-4 text-muted-foreground" />
                      Possible matches — <span className="font-normal">not asserted</span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3 text-sm">
                    {report.mandatory_candidates.length > 0 ? (
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          Mandatory standards that may apply
                        </p>
                        <div className="mt-1 flex flex-wrap gap-2">
                          {report.mandatory_candidates.map((item) => (
                            <Badge key={item} variant="outline" className="font-mono">
                              {item}
                            </Badge>
                          ))}
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Several mandatory standards matched the description equally
                          well, so none is claimed as required.
                        </p>
                      </div>
                    ) : null}
                    {report.sector_candidates.length > 0 ? (
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          Commonly required in the {report.sector} sector
                        </p>
                        <div className="mt-1 flex flex-wrap gap-2">
                          {report.sector_candidates.map((item) => (
                            <Badge key={item} variant="muted" className="font-mono">
                              {item}
                            </Badge>
                          ))}
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Informational. These are not counted as missing, because a
                          sector list is not a requirement for a specific product.
                        </p>
                      </div>
                    ) : null}
                  </CardContent>
                </Card>
              ) : null}

              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Sources checked</CardTitle>
                </CardHeader>
                <CardContent className="space-y-1.5">
                  {report.standards.map((row) => (
                    <div
                      key={row.input}
                      className="flex flex-wrap items-center gap-2 text-sm"
                    >
                      <span className="font-mono">{row.designation}</span>
                      <span className="min-w-0 flex-1 truncate text-muted-foreground">
                        {row.title}
                      </span>
                      {!row.found_in_dataset ? (
                        <Badge variant="outline">not in dataset</Badge>
                      ) : null}
                      {row.is_mandatory ? <Badge variant="default">QCO</Badge> : null}
                      {row.is_current ? (
                        <Badge variant="success">current</Badge>
                      ) : (
                        <Badge variant="warning">superseded</Badge>
                      )}
                    </div>
                  ))}
                </CardContent>
              </Card>

              {report.limitations.length > 0 ? (
                <Alert>
                  <Info className="h-4 w-4" />
                  <AlertTitle>Limitations</AlertTitle>
                  <AlertDescription>
                    <ul className="list-disc space-y-0.5 pl-4">
                      {report.limitations.map((limitation) => (
                        <li key={limitation}>{limitation}</li>
                      ))}
                    </ul>
                  </AlertDescription>
                </Alert>
              ) : null}

              <div className="flex flex-wrap gap-3">
                <Button asChild variant="outline">
                  <a
                    href={gapReportUrl(
                      report.product_description,
                      standards.length > 0 ? standards : report.standards.map((s) => s.designation),
                    )}
                    target="_blank"
                    rel="noreferrer noopener"
                  >
                    Open the printable gap report
                    <ExternalLink className="h-4 w-4" />
                  </a>
                </Button>
                <Button asChild variant="ghost">
                  <Link href="/standards">Browse the standards in this report</Link>
                </Button>
              </div>

              <Separator />
              <p className="text-xs text-muted-foreground">
                The mandatory list comes from the API&apos;s QCO tier{" "}
                <code className="font-mono">{report.qco_source}</code>
                {report.qco_verified ? " (verified against the scraped list)" : " — unverified"}
                . {report.qco_verified
                  ? ""
                  : "An unverified list cannot prove compliance, so a full score is not reachable on this tier."}
              </p>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function Counter({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "good" | "bad" | "warn" | "plain";
}) {
  const styles = {
    good: "border-emerald-200 bg-emerald-50 text-emerald-800",
    bad: "border-red-200 bg-red-50 text-red-800",
    warn: "border-amber-200 bg-amber-50 text-amber-800",
    plain: "border-border bg-muted/40 text-foreground",
  }[tone];

  return (
    <div className={`rounded-lg border px-2 py-2 ${styles}`}>
      <p className="text-xl font-bold leading-none">{value}</p>
      <p className="mt-1 text-[11px] leading-tight opacity-80">{label}</p>
    </div>
  );
}

function StatusList({
  title,
  icon: Icon,
  tone,
  items,
  empty,
}: {
  title: string;
  icon: React.ElementType;
  tone: "good" | "bad";
  items: string[];
  empty: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Icon
            className={`h-4 w-4 ${tone === "good" ? "text-emerald-600" : "text-red-600"}`}
          />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{empty}</p>
        ) : (
          <ul className="space-y-1">
            {items.map((item) => (
              <li key={item} className="font-mono text-sm">
                {item}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
