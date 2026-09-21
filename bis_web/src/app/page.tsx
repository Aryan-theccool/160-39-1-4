'use client';

import { useRef } from 'react';
import {
  ArrowRight,
  FileUp,
  Library,
  LayoutDashboard,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';

import { SearchBar } from '@/components/search-bar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

gsap.registerPlugin(useGSAP);

const FEATURES = [
  {
    href: '/search',
    icon: Zap,
    title: 'Hybrid search',
    body: 'Keyword, TF-IDF and semantic retrieval fused into one ranking, with the clauses that matched quoted back.',
  },
  {
    href: '/upload',
    icon: FileUp,
    title: 'Tender analysis',
    body: 'Drop a tender PDF; every IS code it cites is extracted and checked against the corpus.',
  },
  {
    href: '/compliance',
    icon: ShieldCheck,
    title: 'Compliance check',
    body: 'Score a product against the mandatory Quality Control Order list, with a printable gap report.',
  },
  {
    href: '/standards',
    icon: Library,
    title: 'Browse the corpus',
    body: 'Every indexed standard, filterable by division, committee, year and currency.',
  },
  {
    href: '/dashboard',
    icon: LayoutDashboard,
    title: 'Corpus dashboard',
    body: 'What is actually in the dataset: standards by division, by decade, and by status.',
  },
];

export default function HomePage() {
  const router = useRouter();
  const heroRef = useRef<HTMLDivElement>(null);
  const cardsRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const searchBarRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    // Animate title in
    if (titleRef.current) {
      gsap.from(titleRef.current, {
        opacity: 0,
        y: 30,
        duration: 0.8,
        ease: 'power3.out',
      });
    }

    // Animate description
    const description = heroRef.current?.querySelector('p');
    if (description) {
      gsap.from(description, {
        opacity: 0,
        y: 20,
        duration: 0.8,
        delay: 0.2,
        ease: 'power3.out',
      });
    }

    // Animate search bar
    if (searchBarRef.current) {
      gsap.from(searchBarRef.current, {
        opacity: 0,
        scale: 0.95,
        duration: 0.8,
        delay: 0.4,
        ease: 'back.out',
      });
    }

    // Animate cards in stagger
    const cards = cardsRef.current?.querySelectorAll('[data-card]');
    if (cards) {
      gsap.from(cards, {
        opacity: 0,
        y: 50,
        duration: 0.8,
        stagger: 0.1,
        delay: 0.6,
        ease: 'power3.out',
      });
    }

    // Add hover animation
    const cardElements = cardsRef.current?.querySelectorAll('a > div, [data-card]');
    cardElements?.forEach((card) => {
      card.addEventListener('mouseenter', () => {
        gsap.to(card, {
          y: -8,
          boxShadow: '0 20px 40px rgba(0,0,0,0.2)',
          duration: 0.3,
          ease: 'power2.out',
        });
      });

      card.addEventListener('mouseleave', () => {
        gsap.to(card, {
          y: 0,
          boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
          duration: 0.3,
          ease: 'power2.out',
        });
      });
    });
  }, { scope: heroRef });

  return (
    <div className="space-y-12">
      {/* Hero: the search bar is the page. */}
      <section ref={heroRef} className="space-y-6 pt-6 text-center sm:pt-12">
        <div className="space-y-4">
          <Badge variant="outline" className="mx-auto border-tricolor-saffron/40 bg-accent">
            Smart India Hackathon • PS 26108
          </Badge>
          <h1 ref={titleRef} className="text-3xl font-bold tracking-tight sm:text-5xl">
            Find the <span className="tricolor-text">Indian Standard</span> your product
            must meet
          </h1>
          <p className="mx-auto max-w-2xl text-base text-muted-foreground sm:text-lg">
            Search the BIS corpus in plain language, upload a tender to see which codes
            it demands, and check a product against the mandatory certification list.
            Every answer names its sources.
          </p>
        </div>
        <div ref={searchBarRef} className="mx-auto max-w-3xl">
          <SearchBar
            size="hero"
            showExamples
            onSubmit={(query) => router.push(`/search?q=${encodeURIComponent(query)}`)}
          />
        </div>
      </section>

      {/* What the app does, as navigation. */}
      <section ref={cardsRef} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((feature) => (
          <Link key={feature.href} href={feature.href} className="group" data-card="">
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
        <Card data-card="" className="border-dashed bg-muted/30">
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
