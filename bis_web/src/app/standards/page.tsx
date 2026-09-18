"use client";

import { Download, ExternalLink, Library, RotateCcw, Search as SearchIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { ErrorBanner } from "@/components/error-banner";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { listStandards, STANDARDS_PAGE_LIMIT, type StandardSummary } from "@/lib/api";
import { formatNumber, statusLabel } from "@/lib/format";
import { useDebounced, useAsync } from "@/hooks/use-api";

const ALL = "__all__";

/**
 * The corpus is 197 standards, so the whole list is fetched once and filtered
 * in the browser: typing filters instantly, with no request per keystroke and
 * no pagination to click through. The API caps `limit` at 500, which leaves
 * room for the corpus to grow ~2.5x before this needs revisiting.
 */
export default function StandardsPage() {
  const [query, setQuery] = React.useState("");
  const [division, setDivision] = React.useState(ALL);
  const [year, setYear] = React.useState(ALL);
  const [currency, setCurrency] = React.useState(ALL);
  const [compulsory, setCompulsory] = React.useState(ALL);

  const debouncedQuery = useDebounced(query, 200);

  const { data, error, loading } = useAsync(
    () => listStandards({ limit: STANDARDS_PAGE_LIMIT }),
    [],
  );

  const rows = React.useMemo(() => data?.standards ?? [], [data]);

  const years = React.useMemo(() => {
    const set = new Set(rows.map((row) => row.year).filter((value) => value > 0));
    return [...set].sort((a, b) => b - a);
  }, [rows]);

  const filtered = React.useMemo(() => {
    const needle = debouncedQuery.trim().toLowerCase();
    return rows.filter((row) => {
      if (division !== ALL && row.division !== division) return false;
      if (year !== ALL && String(row.year) !== year) return false;
      if (currency === "current" && !row.is_current) return false;
      if (currency === "superseded" && row.is_current) return false;
      if (compulsory === "yes" && !row.is_compulsory) return false;
      if (compulsory === "no" && row.is_compulsory) return false;
      if (!needle) return true;
      return (
        row.designation.toLowerCase().includes(needle) ||
        row.title.toLowerCase().includes(needle) ||
        row.committee.toLowerCase().includes(needle)
      );
    });
  }, [rows, debouncedQuery, division, year, currency, compulsory]);

  const anyFilter =
    query !== "" || division !== ALL || year !== ALL || currency !== ALL || compulsory !== ALL;

  function reset() {
    setQuery("");
    setDivision(ALL);
    setYear(ALL);
    setCurrency(ALL);
    setCompulsory(ALL);
  }

  function exportCsv() {
    const header = ["designation", "title", "division", "committee", "year", "status", "compulsory"];
    const lines = filtered.map((row) =>
      [
        row.designation,
        row.title,
        row.division,
        row.committee,
        row.year,
        row.is_current ? "current" : "superseded",
        row.is_compulsory ? "yes" : "no",
      ]
        .map((cell) => `"${String(cell).replace(/"/g, '""')}"`)
        .join(","),
    );
    const blob = new Blob([[header.join(","), ...lines].join("\n")], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "bis-standards.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Library}
        title="Standards browser"
        description={
          data
            ? `All ${formatNumber(data.total)} indexed Indian Standards, filterable by division, committee, year and currency.`
            : "The full indexed corpus."
        }
      >
        <Button variant="outline" size="sm" onClick={exportCsv} disabled={filtered.length === 0}>
          <Download className="h-4 w-4" />
          Export {filtered.length} rows
        </Button>
      </PageHeader>

      <Card>
        <CardContent className="grid gap-4 p-4 md:grid-cols-2 lg:grid-cols-5">
          <div className="space-y-1.5 lg:col-span-2">
            <Label htmlFor="filter-q">Search</Label>
            <div className="relative">
              <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="filter-q"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="IS number, title or committee"
                className="pl-9"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="filter-division">Division</Label>
            <Select value={division} onValueChange={setDivision}>
              <SelectTrigger id="filter-division">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All divisions</SelectItem>
                {(data?.facets.divisions ?? []).map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="filter-year">Year</Label>
            <Select value={year} onValueChange={setYear}>
              <SelectTrigger id="filter-year">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>Any year</SelectItem>
                {years.map((option) => (
                  <SelectItem key={option} value={String(option)}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="filter-currency">Edition</Label>
            <Select value={currency} onValueChange={setCurrency}>
              <SelectTrigger id="filter-currency">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>Any edition</SelectItem>
                <SelectItem value="current">Current only</SelectItem>
                <SelectItem value="superseded">Superseded only</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="filter-compulsory">QCO mandatory</Label>
            <Select value={compulsory} onValueChange={setCompulsory}>
              <SelectTrigger id="filter-compulsory">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>Any</SelectItem>
                <SelectItem value="yes">Mandatory only</SelectItem>
                <SelectItem value="no">Not mandatory</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-end">
            <Button variant="ghost" onClick={reset} disabled={!anyFilter} className="w-full lg:w-auto">
              <RotateCcw className="h-4 w-4" />
              Reset filters
            </Button>
          </div>
        </CardContent>
      </Card>

      {error ? <ErrorBanner error={error} /> : null}

      {loading ? (
        <Skeleton className="h-96 w-full" />
      ) : error ? null : filtered.length === 0 ? (
        <EmptyState
          icon={Library}
          title={anyFilter ? "No standards match these filters" : "The corpus is empty"}
          hint={
            anyFilter
              ? "Loosen a filter, or clear them all."
              : "The API reported no standards. Check /health — the dataset may not be loaded."
          }
          action={
            anyFilter ? (
              <Button variant="outline" onClick={reset}>
                Clear all filters
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>
              Showing {formatNumber(filtered.length)} of {formatNumber(rows.length)} standards
            </span>
          </div>

          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[150px]">Standard</TableHead>
                    <TableHead>Title</TableHead>
                    <TableHead className="hidden w-[190px] lg:table-cell">Division</TableHead>
                    <TableHead className="hidden w-[110px] md:table-cell">Committee</TableHead>
                    <TableHead className="w-[90px]">Year</TableHead>
                    <TableHead className="w-[150px]">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((row: StandardSummary) => (
                    <TableRow key={row.canonical}>
                      <TableCell className="font-mono text-sm font-medium">
                        <Link
                          href={`/search?q=${encodeURIComponent(row.designation)}`}
                          className="hover:text-tricolor-saffron hover:underline"
                        >
                          {row.designation}
                        </Link>
                      </TableCell>
                      <TableCell className="max-w-[420px]">
                        <span className="line-clamp-2 text-sm" title={row.title}>
                          {row.title}
                        </span>
                        <span className="mt-0.5 flex gap-1.5">
                          {row.is_compulsory ? (
                            <Badge variant="default" className="mt-1 text-[10px]">
                              QCO mandatory
                            </Badge>
                          ) : null}
                        </span>
                      </TableCell>
                      <TableCell className="hidden text-sm text-muted-foreground lg:table-cell">
                        {row.division || "—"}
                      </TableCell>
                      <TableCell className="hidden font-mono text-xs text-muted-foreground md:table-cell">
                        {row.committee || "—"}
                      </TableCell>
                      <TableCell className="text-sm">{row.year || "—"}</TableCell>
                      <TableCell>
                        {row.is_current ? (
                          <Badge variant="success">Current</Badge>
                        ) : (
                          <Link href={`/standards?q=${encodeURIComponent(row.superseded_by)}`}>
                            <Badge variant="warning" title={statusLabel(row)}>
                              Superseded
                            </Badge>
                          </Link>
                        )}
                        {row.archive_url ? (
                          <a
                            href={row.archive_url}
                            target="_blank"
                            rel="noreferrer noopener"
                            className="mt-1 flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground hover:underline"
                          >
                            source <ExternalLink className="h-2.5 w-2.5" />
                          </a>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
