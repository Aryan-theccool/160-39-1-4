"use client";

import { Activity, BarChart3, Database, Layers, ShieldCheck } from "lucide-react";
import * as React from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { health, listStandards, STANDARDS_PAGE_LIMIT, type Health, type StandardsPage } from "@/lib/api";
import { byDecade, countBy, formatNumber } from "@/lib/format";
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
    () => listStandards({ limit: STANDARDS_PAGE_LIMIT }),
    [],
  );

  // Memoised so the five derived aggregates below are not recomputed on
  // every render by a fresh `?? []` array identity.
  const rows = React.useMemo(
    () => standardsState.data?.standards ?? [],
    [standardsState.data],
  );

  const byDivision = React.useMemo(() => countBy(rows, (row) => row.division), [rows]);
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
        description="What is actually in the indexed dataset — and what the service is running on. Figures come from the API, not from a hardcoded count."
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
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              icon={Database}
              label="Standards indexed"
              value={formatNumber(service!.corpus.standards)}
              sub={`${formatNumber(service!.corpus.chunks)} text chunks`}
            />
            <StatCard
              icon={Layers}
              label="Divisions"
              value={formatNumber(service!.corpus.divisions)}
              sub={
                service!.corpus.year_range?.length === 2
                  ? `${service!.corpus.year_range[0]}–${service!.corpus.year_range[1]}`
                  : "—"
              }
            />
            <StatCard
              icon={ShieldCheck}
              label="QCO mandatory"
              value={formatNumber(service!.corpus.compulsory)}
              sub={`list tier: ${service!.qco.source}${service!.qco.verified ? "" : " (unverified)"}`}
            />
            <StatCard
              icon={Activity}
              label="Service"
              value={service!.status}
              sub={`started in ${Math.round(service!.startup_ms)} ms`}
              tone={service!.status === "ok" ? "good" : service!.status === "degraded" ? "warn" : "bad"}
            />
          </div>

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
                <ChartCard title="Standards by division" hint={`${byDivision.length} divisions`}>
                  <ResponsiveContainer width="100%" height={Math.max(280, byDivision.length * 38)}>
                    <BarChart
                      data={byDivision}
                      layout="vertical"
                      margin={{ left: 8, right: 24, top: 4, bottom: 4 }}
                    >
                      <CartesianGrid horizontal={false} strokeDasharray="3 3" />
                      <XAxis type="number" allowDecimals={false} fontSize={12} />
                      <YAxis
                        type="category"
                        dataKey="label"
                        width={150}
                        fontSize={12}
                        interval={0}
                      />
                      <ChartTooltip
                        formatter={(value) => [`${value} standards`, "Count"] as [string, string]}
                        cursor={{ fill: "hsl(var(--muted))" }}
                      />
                      <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                        {byDivision.map((entry, index) => (
                          <Cell key={entry.label} fill={PALETTE[index % PALETTE.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>

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
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  sub?: string;
  tone?: "plain" | "good" | "warn" | "bad";
}) {
  const toneClass = {
    plain: "text-foreground",
    good: "text-emerald-700",
    warn: "text-amber-700",
    bad: "text-red-700",
  }[tone];

  return (
    <Card>
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
