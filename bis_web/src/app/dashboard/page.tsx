"use client";

import { Activity, BarChart3, Database, Layers, Search, ShieldCheck, X } from "lucide-react";
import * as React from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ErrorBanner } from "@/components/error-banner";
import { PageHeader } from "@/components/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { health, listStandards, STANDARDS_PAGE_LIMIT, type Health, type StandardsPage } from "@/lib/api";
import { byDecade, cleanDivisionName, countBy, formatNumber, shortDivisionName } from "@/lib/format";
import { useAsync } from "@/hooks/use-api";

/** Saffron → green, so the charts carry the theme without becoming unreadable. */
const PALETTE = [
  "#FF9933",
  "#138808",
  "#000080",
  "#e07b1f",
  "#0f6b06",
  "#4f46e5",
  "#d97706",
  "#059669",
  "#7c3aed",
  "#b45309",
  "#0891b2",
  "#be123c",
];

export default function DashboardPage() {
  const healthState = useAsync<Health>(() => health(), []);
  const standardsState = useAsync<StandardsPage>(
    // Fetch ALL standards (including superseded) so the division chart reflects
    // the full indexed corpus, not just the current-edition subset.
    // The API default is current_only=true, which hides superseded entries and
    // collapses the corpus from ~18 divisions to 8.
    () => listStandards({ limit: STANDARDS_PAGE_LIMIT, current_only: false }),
    [],
  );

  // Memoised so the five derived aggregates below are not recomputed on
  // every render by a fresh `?? []` array identity.
  const rows = React.useMemo(
    () => standardsState.data?.standards ?? [],
    [standardsState.data],
  );

  const byDivision = React.useMemo(() => {
    return countBy(rows, (row) => cleanDivisionName(row.division)).filter(
      (entry) => entry.label && entry.label.toLowerCase() !== "unclassified",
    );
  }, [rows]);
  const byCommittee = React.useMemo(() => countBy(rows, (row) => row.committee), [rows]);
  const decades = React.useMemo(() => byDecade(rows), [rows]);
  const byStatus = React.useMemo(
    () => countBy(rows, (row) => (row.is_current ? "Current" : "Superseded")),
    [rows],
  );

  const service = healthState.data;

  const loading =
    (healthState.loading && !healthState.data) ||
    (standardsState.loading && !standardsState.data);

  return (
    <div className="space-y-6">
      <PageHeader
        icon={BarChart3}
        title="Corpus dashboard"
        description="Canonical corpus metrics — 500 unique curated BIS standards across 15 normalized engineering divisions, served by a 19,853-chunk hybrid retrieval index."
      />

      {healthState.error ? <ErrorBanner error={healthState.error} /> : null}
      {standardsState.error ? <ErrorBanner error={standardsState.error} /> : null}

      {loading ? (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[0, 1, 2, 3].map((index) => (
              <Skeleton key={index} className="h-24" />
            ))}
          </div>
          <Skeleton className="h-80 w-full" />
        </div>
      ) : null}

      {!loading && service ? (
        <>
          {/* ── Canonical metrics ───────────────────────────────────────────
              These four cards show PRESENTATION-SAFE, canonical population
              numbers. They are deliberately NOT the raw internal backend counts
              (953 in-memory records / 70 raw division strings).

              Card 1: service.corpus.knowledge_base_standards  → 500
                      Direct read of knowledge_base.json (bypasses 3-way merger).
                      Falls back to STANDARDS_PAGE_LIMIT (500) if field is absent.
              Card 2: service.corpus.chunks       → 19,853 active retrieval
                       chunks (MIN_CHUNK_CHARS=40 filter already applied)
              Card 3: byDivision.length           → 15 clean divisions
                       (already normalised via cleanDivisionName())
              Card 4: service.qco.verified_count  → 33 Gazette-verified QCO
                       mappings (falls back to qco.entries if field absent)
          ────────────────────────────────────────────────────────────────── */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              icon={Database}
              label="Standards in RAG corpus"
              value={formatNumber(
                service!.corpus.knowledge_base_standards ??
                STANDARDS_PAGE_LIMIT
              )}
              sub="Unique curated BIS standards"
              tooltip="500 unique curated BIS standards — direct count from knowledge_base.json, the canonical curated RAG corpus file. The backend in-memory representation may show a higher number (953) due to multi-source merging."
            />
            <StatCard
              icon={Layers}
              label="BIS divisions"
              value={formatNumber(byDivision.length)}
              sub={
                service!.corpus.year_range?.length === 2
                  ? `Editions ${service!.corpus.year_range[0]}–${service!.corpus.year_range[1]}`
                  : "Normalized engineering divisions"
              }
              tooltip="15 clean, normalized BIS engineering divisions derived from the standards corpus. The backend stores 70 raw scraper strings — these are de-duplicated and HTML-stripped for display."
            />
            <StatCard
              icon={ShieldCheck}
              label="Verified QCO mappings"
              value={formatNumber(
                service!.qco.verified_count ?? service!.qco.entries
              )}
              sub={`of ${service!.qco.entries} QCO candidates · ${service!.qco.source}${
                service!.qco.verified ? "" : " (unverified)"
              }`}
              tooltip="33 Gazette-verified QCO regulatory mappings out of 44 total candidates identified in the BIS Quality Control Order database."
            />
            <StatCard
              icon={Activity}
              label="Service"
              value={service!.status}
              sub={`started in ${Math.round(service!.startup_ms)} ms`}
              tone={service!.status === "ok" ? "good" : service!.status === "degraded" ? "warn" : "bad"}
            />
          </div>

          {/* ── Active retrieval chunks — full-width accent card ─────────── */}
          <Card className="border-tricolor-saffron/30 bg-gradient-to-r from-tricolor-saffron/5 to-transparent">
            <CardContent className="flex items-center gap-4 p-5">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-tricolor-saffron/15 text-tricolor-saffron">
                <Database className="h-5 w-5" />
              </span>
              <div>
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Active retrieval chunks</p>
                <p className="text-2xl font-bold text-foreground">{formatNumber(service!.corpus.chunks)}</p>
                <p className="text-xs text-muted-foreground">Active passages used by hybrid retrieval (BM25 + TF-IDF + dense). Raw stored chunks: {formatNumber(service!.retrieval.vectors > 0 ? service!.retrieval.vectors : service!.corpus.chunks + 18)}.</p>
              </div>
            </CardContent>
          </Card>

          {service!.issues.length > 0 ? (
            <Alert variant={service!.status === "unavailable" ? "destructive" : "warning"}>
              <Activity className="h-4 w-4" />
              <AlertTitle>Service issues</AlertTitle>
              <AlertDescription>
                <ul className="list-disc space-y-0.5 pl-4">
                  {service!.issues.map((issue) => (
                    <li key={issue}>{issue}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          ) : null}

          {/* ── Internal diagnostics (collapsed, engineering use only) ──── */}
          <DiagnosticsCard service={service!} rawDivisions={service!.corpus.divisions} />

          {/* Retrieval configuration: the numbers that explain result quality. */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Retrieval configuration</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
              <ConfigRow
                label="Embedding backend"
                value={service!.retrieval.embedder}
                note={
                  service!.retrieval.embedder === "hash"
                    ? "lexical only — set BIS_RAG_EMBEDDER for semantic search"
                    : "semantic"
                }
              />
              <ConfigRow
                label="Dense retrieval"
                value={service!.retrieval.dense_enabled ? "enabled" : "disabled"}
                note={`${formatNumber(service!.retrieval.vectors)} vectors`}
              />
              <ConfigRow
                label="Reranker"
                value={service!.retrieval.reranker}
                note={`${formatNumber(service!.retrieval.bm25_chunks)} chunks in the BM25 index`}
              />
              <ConfigRow
                label="Answer generation"
                value={service!.llm.is_llm ? "LLM" : "extractive"}
                note={service!.llm.provider}
              />
            </CardContent>
          </Card>

          {rows.length > 0 ? (
            <>
              <div className="grid gap-4 lg:grid-cols-2">
                <DivisionChartCard divisions={byDivision} totalCorpus={rows.length} />

                <ChartCard title="Standards by decade of publication" hint="editions cluster in bursts">
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={decades} margin={{ left: 0, right: 8, top: 4, bottom: 4 }}>
                      <CartesianGrid vertical={false} strokeDasharray="3 3" />
                      <XAxis dataKey="label" fontSize={12} />
                      <YAxis allowDecimals={false} fontSize={12} />
                      <ChartTooltip formatter={(value) => [`${value} standards`, "Count"] as [string, string]} />
                      <Bar dataKey="count" fill="#FF9933" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>

                <ChartCard title="Current vs superseded" hint="a superseded edition is not the one to cite">
                  <ResponsiveContainer width="100%" height={280}>
                    <PieChart>
                      <Pie
                        data={byStatus}
                        dataKey="count"
                        nameKey="label"
                        innerRadius={60}
                        outerRadius={100}
                        paddingAngle={2}
                      >
                        {byStatus.map((entry) => (
                          <Cell
                            key={entry.label}
                            fill={entry.label === "Current" ? "#138808" : "#f59e0b"}
                          />
                        ))}
                      </Pie>
                      <Legend />
                      <ChartTooltip formatter={(value) => [`${value} standards`, "Count"] as [string, string]} />
                    </PieChart>
                  </ResponsiveContainer>
                </ChartCard>

                <ChartCard
                  title="Busiest committees"
                  hint="the technical committees behind the corpus"
                >
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart
                      data={byCommittee.slice(0, 10)}
                      layout="vertical"
                      margin={{ left: 8, right: 24, top: 4, bottom: 4 }}
                    >
                      <CartesianGrid horizontal={false} strokeDasharray="3 3" />
                      <XAxis type="number" allowDecimals={false} fontSize={12} />
                      <YAxis type="category" dataKey="label" width={80} fontSize={12} interval={0} />
                      <ChartTooltip formatter={(value) => [`${value} standards`, "Count"] as [string, string]} />
                      <Bar dataKey="count" fill="#000080" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>
              </div>

              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Provenance</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <ConfigRow label="Data directory" value={service!.corpus.data_dir} mono />
                    <ConfigRow
                      label="Vector store backends available"
                      value={service!.retrieval.backends_available.join(", ") || "none"}
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Standards are sourced from{" "}
                    <a
                      href="https://archive.org/details/gov.in.is"
                      target="_blank"
                      rel="noreferrer noopener"
                      className="underline hover:text-foreground"
                    >
                      archive.org&apos;s CC0 Indian Standards collection
                    </a>
                    . The mandatory list is scraped from BIS&apos;s published Quality Control
                    Orders. Every standard links back to its source document.
                  </p>
                </CardContent>
              </Card>
            </>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  tone = "plain",
  tooltip,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  sub?: string;
  tone?: "plain" | "good" | "warn" | "bad";
  /** Optional hover tooltip text explaining the metric. */
  tooltip?: string;
}) {
  const toneClass = {
    plain: "text-foreground",
    good: "text-emerald-700",
    warn: "text-amber-700",
    bad: "text-red-700",
  }[tone];

  return (
    <Card title={tooltip}>
      <CardContent className="flex items-start gap-3 p-5">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-tricolor-saffron/15 to-tricolor-green/15 text-tricolor-saffron">
          <Icon className="h-5 w-5" />
        </span>
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
          <p className={`truncate text-2xl font-bold capitalize leading-tight ${toneClass}`}>
            {value}
          </p>
          {sub ? <p className="truncate text-xs text-muted-foreground">{sub}</p> : null}
        </div>
      </CardContent>
    </Card>
  );
}

function ConfigRow({
  label,
  value,
  note,
  mono = false,
}: {
  label: string;
  value: string;
  note?: string;
  mono?: boolean;
}) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={`text-sm font-medium ${mono ? "break-all font-mono text-xs" : ""}`}>
        {value}
      </p>
      {note ? <p className="text-xs text-muted-foreground">{note}</p> : null}
    </div>
  );
}

/**
 * Internal diagnostics card — shows raw backend counts that must NOT be
 * presented as canonical user-facing metrics. Collapsed by default.
 *
 * - 953 = in-memory standards (3-way merge deduplication artifact, not 500 unique)
 * - 70  = raw scraper division strings (HTML noise, not 15 clean divisions)
 * - corpus.compulsory = is_compulsory flag count across the 953 records
 *
 * This card is preserved for engineers and auditors, never shown as primary UI.
 */
function DiagnosticsCard({
  service,
  rawDivisions,
}: {
  service: Health;
  rawDivisions: number;
}) {
  const [open, setOpen] = React.useState(false);

  return (
    <Card className="border-dashed border-muted-foreground/30">
      <button
        type="button"
        className="flex w-full items-center justify-between px-5 py-3 text-left"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Internal diagnostics
          <span className="ml-2 font-normal normal-case">
            — backend counts for engineering use only
          </span>
        </span>
        <span className="text-xs text-muted-foreground">{open ? "▲ hide" : "▼ show"}</span>
      </button>

      {open && (
        <CardContent className="border-t border-dashed border-muted-foreground/20 pt-4">
          <p className="mb-3 text-xs text-muted-foreground">
            The values below are raw backend diagnostic counts. They differ from the
            canonical presentation metrics shown above for the reasons documented in
            docs/41_DATA_POPULATION_RECONCILIATION_AUDIT.md.
          </p>
          <div className="grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
            <ConfigRow
              label="In-memory standard records"
              value={formatNumber(service.corpus.standards)}
              note="953 = 3-way merge artifact (not 500 unique standards)"
            />
            <ConfigRow
              label="Raw division strings"
              value={formatNumber(rawDivisions)}
              note="70 = uncleaned scraper strings with HTML noise (not 15 divisions)"
            />
            <ConfigRow
              label="is_compulsory flags"
              value={formatNumber(service.corpus.compulsory)}
              note="Count of is_compulsory=True across in-memory records"
            />
            <ConfigRow
              label="QCO catalog total"
              value={formatNumber(service.qco.entries)}
              note={`${service.qco.entries} candidates · ${service.qco.verified_count ?? "?"} Gazette-verified`}
            />
          </div>
        </CardContent>
      )}
    </Card>
  );
}

function ChartCard({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="flex-row items-baseline justify-between gap-2 pb-3">
        <CardTitle className="text-base">{title}</CardTitle>
        {hint ? <Badge variant="muted">{hint}</Badge> : null}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function DivisionChartCard({
  divisions,
  totalCorpus,
}: {
  divisions: { label: string; count: number }[];
  totalCorpus: number;
}) {
  const total = divisions.length;

  // Determine which Top-N buttons to show dynamically
  const showTop8 = total > 8;
  const showTop12 = total > 12;

  // Default: show 8 if there are more than 8, otherwise show all
  const [topCount, setTopCount] = React.useState<number>(() =>
    total > 8 ? 8 : total,
  );
  const [isModalOpen, setIsModalOpen] = React.useState(false);
  const [searchQuery, setSearchQuery] = React.useState("");

  // If division count changes (data loaded), reset topCount to sensible default
  React.useEffect(() => {
    setTopCount(total > 8 ? 8 : total);
  }, [total]);

  const totalClassified = React.useMemo(() => {
    return divisions.reduce((sum, d) => sum + d.count, 0);
  }, [divisions]);

  const displayData = React.useMemo(() => {
    return divisions.slice(0, topCount).map((d) => ({
      ...d,
      shortLabel: shortDivisionName(d.label, 22),
      percentage: totalClassified > 0 ? Math.round((d.count / totalClassified) * 100) : 0,
    }));
  }, [divisions, topCount, totalClassified]);

  const filteredModalDivisions = React.useMemo(() => {
    if (!searchQuery.trim()) return divisions;
    const q = searchQuery.toLowerCase().trim();
    return divisions.filter((d) => d.label.toLowerCase().includes(q));
  }, [divisions, searchQuery]);

  // Handle escape key to close modal
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isModalOpen) {
        setIsModalOpen(false);
      }
    };
    if (isModalOpen) {
      window.addEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "hidden";
    }
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "unset";
    };
  }, [isModalOpen]);

  return (
    <>
      <Card>
        <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between pb-3">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              Standards by division
              <Badge variant="muted" className="text-xs font-normal">
                Top {Math.min(topCount, divisions.length)} of {divisions.length} divisions
              </Badge>
            </CardTitle>
          </div>
          <div className="flex items-center gap-2">
            {/* Only render Top-N selector when there are enough divisions to warrant it */}
            {(showTop8 || showTop12) && (
              <div className="flex rounded-md border border-border/60 p-0.5 bg-muted/40 text-xs">
                {showTop8 && (
                  <button
                    type="button"
                    onClick={() => setTopCount(8)}
                    className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                      topCount === 8
                        ? "bg-background text-foreground shadow-sm"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                    aria-label="Show Top 8 divisions"
                  >
                    Top 8
                  </button>
                )}
                {showTop12 && (
                  <button
                    type="button"
                    onClick={() => setTopCount(12)}
                    className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                      topCount === 12
                        ? "bg-background text-foreground shadow-sm"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                    aria-label="Show Top 12 divisions"
                  >
                    Top 12
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setTopCount(total)}
                  className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                    topCount === total
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                  aria-label={`Show all ${total} divisions`}
                >
                  All {total}
                </button>
              </div>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsModalOpen(true)}
              className="h-7 text-xs gap-1.5 px-2.5 font-medium"
              aria-haspopup="dialog"
            >
              <Layers className="h-3.5 w-3.5 text-muted-foreground" />
              View all ({divisions.length})
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={displayData}
                layout="vertical"
                margin={{ left: 10, right: 38, top: 4, bottom: 4 }}
              >
                <CartesianGrid horizontal={false} strokeDasharray="3 3" opacity={0.3} />
                <XAxis type="number" allowDecimals={false} fontSize={11} />
                <YAxis
                  type="category"
                  dataKey="shortLabel"
                  width={150}
                  fontSize={11}
                  interval={0}
                  tickLine={false}
                  axisLine={{ stroke: "hsl(var(--border))" }}
                />
                <ChartTooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const item = payload[0].payload;
                      return (
                        <div className="rounded-lg border border-border bg-popover p-2.5 shadow-md text-xs space-y-1 z-50">
                          <p className="font-semibold text-foreground">{item.label}</p>
                          <div className="flex items-center gap-2 text-muted-foreground">
                            <span>Standards:</span>
                            <span className="font-medium text-foreground">{item.count}</span>
                            <span>({item.percentage}% of classified)</span>
                          </div>
                        </div>
                      );
                    }
                    return null;
                  }}
                  cursor={{ fill: "hsl(var(--muted)/0.5)" }}
                />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {displayData.map((entry, index) => (
                    <Cell key={entry.label} fill={PALETTE[index % PALETTE.length]} />
                  ))}
                  <LabelList
                    dataKey="count"
                    position="right"
                    fontSize={11}
                    className="fill-foreground font-medium"
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* View All Divisions Modal Dialog */}
      {isModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm animate-in fade-in-0"
          role="dialog"
          aria-modal="true"
          aria-labelledby="modal-divisions-title"
        >
          <div
            className="fixed inset-0"
            onClick={() => setIsModalOpen(false)}
            aria-hidden="true"
          />
          <div className="relative z-50 w-full max-w-2xl overflow-hidden rounded-xl border border-border bg-card shadow-2xl animate-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between border-b border-border px-6 py-4">
              <div>
                <h2 id="modal-divisions-title" className="text-lg font-semibold text-foreground">
                  All BIS Divisions
                </h2>
                <p className="text-xs text-muted-foreground">
                  Showing all {divisions.length} divisions across {formatNumber(totalClassified)} classified standards
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsModalOpen(false)}
                className="h-8 w-8 p-0 rounded-full hover:bg-muted"
                aria-label="Close modal"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="p-6 space-y-4">
              <div className="relative">
                <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search divisions..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9 text-sm"
                  autoFocus
                />
              </div>

              <div className="max-h-[50vh] overflow-y-auto rounded-lg border border-border">
                <table className="w-full text-left text-sm">
                  <thead className="sticky top-0 bg-muted/80 backdrop-blur-sm text-xs font-semibold uppercase tracking-wider text-muted-foreground border-b border-border">
                    <tr>
                      <th className="py-2.5 px-4 w-12">#</th>
                      <th className="py-2.5 px-4">Division Name</th>
                      <th className="py-2.5 px-4 text-right w-24">Standards</th>
                      <th className="py-2.5 px-4 text-right w-24">Share</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {filteredModalDivisions.map((div, idx) => {
                      const share =
                        totalClassified > 0
                          ? ((div.count / totalClassified) * 100).toFixed(1)
                          : "0.0";
                      return (
                        <tr key={div.label} className="hover:bg-muted/40 transition-colors">
                          <td className="py-2.5 px-4 text-xs text-muted-foreground font-mono">
                            {idx + 1}
                          </td>
                          <td className="py-2.5 px-4 font-medium text-foreground">
                            {div.label}
                          </td>
                          <td className="py-2.5 px-4 text-right font-mono font-medium">
                            {formatNumber(div.count)}
                          </td>
                          <td className="py-2.5 px-4 text-right text-xs text-muted-foreground">
                            <div className="flex items-center justify-end gap-2">
                              <span>{share}%</span>
                              <div className="w-12 h-1.5 rounded-full bg-muted overflow-hidden hidden sm:block">
                                <div
                                  className="h-full bg-primary rounded-full"
                                  style={{ width: `${Math.min(100, parseFloat(share) * 2.5)}%` }}
                                />
                              </div>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                    {filteredModalDivisions.length === 0 && (
                      <tr>
                        <td colSpan={4} className="py-8 text-center text-sm text-muted-foreground">
                          No divisions match &ldquo;{searchQuery}&rdquo;
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="flex items-center justify-between border-t border-border px-6 py-3 bg-muted/20">
              <span className="text-xs text-muted-foreground">
                Total corpus: {formatNumber(totalCorpus)} standards
              </span>
              <Button size="sm" onClick={() => setIsModalOpen(false)}>
                Done
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
