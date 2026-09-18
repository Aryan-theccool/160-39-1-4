"use client";

import {
  ArrowRight,
  FileUp,
  Library,
  LayoutDashboard,
  ShieldCheck,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { SearchBar } from "@/components/search-bar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

const FEATURES = [
  {
    href: "/search",
    icon: Zap,
    title: "Hybrid search",
    body: "Keyword, TF-IDF and semantic retrieval fused into one ranking, with the clauses that matched quoted back.",
  },
  {
    href: "/upload",
    icon: FileUp,
    title: "Tender analysis",
    body: "Drop a tender PDF; every IS code it cites is extracted and checked against the corpus.",
  },
  {
    href: "/compliance",
    icon: ShieldCheck,
    title: "Compliance check",
    body: "Score a product against the mandatory Quality Control Order list, with a printable gap report.",
  },
  {
    href: "/standards",
    icon: Library,
    title: "Browse the corpus",
    body: "Every indexed standard, filterable by division, committee, year and currency.",
  },
  {
    href: "/dashboard",
    icon: LayoutDashboard,
    title: "Corpus dashboard",
    body: "What is actually in the dataset: standards by division, by decade, and by status.",
  },
];

export default function HomePage() {
  const router = useRouter();

  return (
    <div className="space-y-12">
      {/* Hero: the search bar is the page. */}
      <section className="space-y-6 pt-6 text-center sm:pt-12">
        <div className="space-y-4">
          <Badge variant="outline" className="mx-auto border-tricolor-saffron/40 bg-accent">
            Smart India Hackathon · PS 26108
          </Badge>
          <h1 className="text-3xl font-bold tracking-tight sm:text-5xl">
            Find the <span className="tricolor-text">Indian Standard</span> your
            product must meet
          </h1>
          <p className="mx-auto max-w-2xl text-base text-muted-foreground sm:text-lg">
            Search the BIS corpus in plain language, upload a tender to see which codes
            it demands, and check a product against the mandatory certification list.
            Every answer names its sources.
          </p>
        </div>

        <div className="mx-auto max-w-3xl">
          <SearchBar
            size="hero"
            showExamples
            onSubmit={(query) => router.push(`/search?q=${encodeURIComponent(query)}`)}
          />
        </div>
      </section>

      {/* What the app does, as navigation. */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((feature) => (
          <Link key={feature.href} href={feature.href} className="group">
            <Card className="h-full transition-all group-hover:-translate-y-0.5 group-hover:shadow-md">
              <CardContent className="flex h-full flex-col gap-3 p-5">
                <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-tricolor-saffron/15 to-tricolor-green/15 text-tricolor-saffron">
                  <feature.icon className="h-5 w-5" />
                </span>
                <div className="space-y-1">
                  <p className="font-semibold">{feature.title}</p>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {feature.body}
                  </p>
                </div>
                <span className="mt-auto flex items-center gap-1 text-sm font-medium text-tricolor-saffron">
                  Open
                  <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
                </span>
              </CardContent>
            </Card>
          </Link>
        ))}

        <Card className="border-dashed bg-muted/30">
          <CardContent className="flex h-full flex-col justify-center gap-3 p-5">
            <p className="font-semibold">Not sure where to start?</p>
            <p className="text-sm text-muted-foreground">
              Upload a tender document. It is the fastest way to see what the system
              does with a real input.
            </p>
            <Button asChild variant="outline" className="mt-auto w-fit">
              <Link href="/upload">
                Analyse a PDF
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
