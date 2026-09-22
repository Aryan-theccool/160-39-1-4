"use client";

import { ExternalLink, Quote } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { MatchMeter } from "@/components/match-meter";
import type { SearchResult } from "@/lib/api";
import { foundByLabel, matchStrength, truncate } from "@/lib/format";

export function StandardCard({
  result,
  results,
  rank,
}: {
  result: SearchResult;
  results: SearchResult[];
  rank: number;
}) {
  const strength = matchStrength(result, results);

  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardHeader className="gap-2 pb-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground">
                {rank}
              </span>
              <Link
                href={`/standards?q=${encodeURIComponent(result.designation)}`}
                className="font-mono text-base font-semibold tracking-tight hover:text-tricolor-saffron hover:underline"
              >
                {result.designation}
              </Link>
            </div>
            <p className="text-sm font-medium leading-snug">{result.title}</p>
          </div>
          <MatchMeter value={strength} />
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{result.division || "Unclassified"}</Badge>
          {result.year ? <Badge variant="muted">{result.year}</Badge> : null}
          {result.is_current ? (
            <Badge variant="success">Current</Badge>
          ) : (
            <Badge variant="warning">Superseded</Badge>
          )}
          <span className="text-xs text-muted-foreground">
            found by {foundByLabel(result.found_by)}
          </span>
        </div>

        {result.text ? (
          <div className="flex gap-2 rounded-md border-l-2 border-tricolor-saffron bg-muted/40 px-3 py-2">
            <Quote className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <p className="text-sm leading-relaxed text-muted-foreground">
              {truncate(result.text, 260)}
            </p>
          </div>
        ) : null}

        {result.archive_url ? (
          <a
            href={result.archive_url}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground hover:underline"
          >
            Read the full standard on archive.org
            <ExternalLink className="h-3 w-3" />
          </a>
        ) : null}
      </CardContent>
    </Card>
  );
}
