"use client";

import { Filter, Info, Search as SearchIcon, Sparkles } from "lucide-react";
import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { AnswerPanel } from "@/components/answer-panel";
import { ErrorBanner } from "@/components/error-banner";
import { PageHeader } from "@/components/page-header";
import { SearchBar } from "@/components/search-bar";
import { StandardCard } from "@/components/standard-card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  listStandards,
  recommend,
  search as searchApi,
  type RecommendResponse,
  type SearchResponse,
} from "@/lib/api";
import { formatMs } from "@/lib/format";
import { useAsync } from "@/hooks/use-api";

const ALL = "__all__";

function SearchPageInner() {
  const router = useRouter();
  const params = useSearchParams();
  const query = params.get("q") ?? "";

  const [division, setDivision] = React.useState(ALL);
  const [limit, setLimit] = React.useState("8");
  const [includeSuperseded, setIncludeSuperseded] = React.useState(false);
  const [tab, setTab] = React.useState("results");

  // One request for the whole corpus, purely to offer the division list. The
  // API returns facets with every page, so this doubles as the filter source.
  const facets = useAsync(() => listStandards({ limit: 1 }), []);

  const results = useAsync<SearchResponse>(
    () =>
      searchApi({
        q: query,
        limit: Number(limit),
        domain: division === ALL ? undefined : division,
        include_superseded: includeSuperseded,
        include_passages: true,
      }),
    [query, division, limit, includeSuperseded],
    { skip: !query },
  );

  // The AI answer is only fetched when its tab is opened: it is slower and
  // costs an LLM call on a configured deployment, so it should be opt-in.
  const answer = useAsync<RecommendResponse>(
    () => recommend({ query, top_k: 5 }),
    [query, tab],
    { skip: !query || tab !== "answer" },
  );

  function submit(next: string) {
    const search = new URLSearchParams(params.toString());
    search.set("q", next);
    router.push(`/search?${search.toString()}`);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={SearchIcon}
        title="Search results"
        description={
          query ? (
            <>
              Retrieved with hybrid search — keyword, TF-IDF and semantic ranking fused,
              then re-ranked. No language model is involved in this list.
            </>
          ) : (
            "Enter a product, material or IS code to search the corpus."
          )
        }
      />

      <SearchBar size="inline" initialValue={query} onSubmit={submit} busy={results.loading} />

      <Tabs value={tab} onValueChange={setTab}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <TabsList>
            <TabsTrigger value="results">
              Standards{results.data ? ` (${results.data.results.length})` : ""}
            </TabsTrigger>
            <TabsTrigger value="answer" className="gap-1.5">
              <Sparkles className="h-3.5 w-3.5" />
              AI answer
            </TabsTrigger>
          </TabsList>

          {tab === "results" ? (
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-2">
                <Label htmlFor="division" className="flex items-center gap-1 text-xs">
                  <Filter className="h-3 w-3" />
                  Division
                </Label>
                <Select value={division} onValueChange={setDivision}>
                  <SelectTrigger id="division" className="h-8 w-[190px] text-xs">
                    <SelectValue placeholder="All divisions" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL}>All divisions</SelectItem>
                    {(facets.data?.facets.divisions ?? []).map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <Select value={limit} onValueChange={setLimit}>
                <SelectTrigger className="h-8 w-[110px] text-xs" aria-label="Results per page">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {["5", "8", "15", "25"].map((option) => (
                    <SelectItem key={option} value={option}>
                      Top {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <label className="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={includeSuperseded}
                  onChange={(event) => setIncludeSuperseded(event.target.checked)}
                  className="h-3.5 w-3.5 rounded border-input accent-tricolor-saffron"
                />
                Include superseded editions
              </label>
            </div>
          ) : null}
        </div>

        <TabsContent value="results" className="space-y-4">
          {!query ? (
            <EmptyState
              icon={SearchIcon}
              title="Nothing searched yet"
              hint="Type a product, a material, or an IS number above. Try “ordinary portland cement”."
            />
          ) : results.error ? (
            <ErrorBanner error={results.error} />
          ) : results.loading ? (
            <div className="space-y-3">
              {[0, 1, 2].map((index) => (
                <Skeleton key={index} className="h-40 w-full" />
              ))}
            </div>
          ) : results.data && results.data.results.length > 0 ? (
            <>
              <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                <span>
                  {results.data.results.length} result
                  {results.data.results.length === 1 ? "" : "s"} · {formatMs(results.data.took_ms)}{" "}
                  server-side
                </span>
                <Badge variant="muted">intent: {results.data.intent}</Badge>
                <span className="hidden sm:inline">re-ranked by {results.data.reranker}</span>
              </div>

              {results.data.supersession_warnings.length > 0 ? (
                <Alert variant="warning">
                  <Info className="h-4 w-4" />
                  <AlertDescription>
                    <ul className="list-disc space-y-0.5 pl-4">
                      {results.data.supersession_warnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  </AlertDescription>
                </Alert>
              ) : null}

              <div className="space-y-3">
                {results.data.results.map((result, index) => (
                  <StandardCard
                    key={result.id}
                    result={result}
                    results={results.data!.results}
                    rank={index + 1}
                  />
                ))}
              </div>

              {/*
                Said once, plainly, rather than on every card. The percentages on
                the cards are relative to the top hit -- they are not model
                confidence, and the distinction matters.
              */}
              <p className="text-xs text-muted-foreground">
                Match strength on each card is this result&apos;s share of the top-ranked
                result&apos;s score, not a confidence value. The API returns rank scores,
                which compare only within one query.
              </p>
            </>
          ) : (
            <EmptyState
              icon={SearchIcon}
              title={`No standards matched “${query}”`}
              hint={
                <>
                  The corpus holds Indian Standards from archive.org. Try a shorter phrase,
                  or turn off the division filter
                  {division !== ALL ? ` (currently “${division}”)` : ""}.
                </>
              }
              action={
                division !== ALL ? (
                  <Button variant="outline" onClick={() => setDivision(ALL)}>
                    Clear the division filter
                  </Button>
                ) : undefined
              }
            />
          )}
        </TabsContent>

        <TabsContent value="answer" className="space-y-4">
          {tab === "answer" && answer.loading && !answer.data ? (
            <Skeleton className="h-64 w-full" />
          ) : answer.error ? (
            <ErrorBanner error={answer.error} />
          ) : answer.data ? (
            <AnswerPanel answer={answer.data} />
          ) : (
            <Skeleton className="h-64 w-full" />
          )}
        </TabsContent>
      </Tabs>

      <p className="text-xs text-muted-foreground">
        Need the raw endpoint? <code className="font-mono">GET /api/v1/search?q=…</code>{" "}
        returns this as JSON. The interactive schema is at <code className="font-mono">/docs</code>.
      </p>
    </div>
  );
}

/**
 * `useSearchParams` needs a Suspense boundary or the production build fails with
 * "useSearchParams() should be wrapped in a suspense boundary". Dev mode hides it.
 */
export default function SearchPage() {
  return (
    <React.Suspense fallback={<Skeleton className="h-72 w-full" />}>
      <SearchPageInner />
    </React.Suspense>
  );
}
