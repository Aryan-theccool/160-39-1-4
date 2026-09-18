"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  FileUp,
  LayoutDashboard,
  Library,
  Scale,
  Search,
  ShieldCheck,
} from "lucide-react";

import { ApiStatus } from "@/components/api-status";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/", label: "Home", icon: Search },
  { href: "/search", label: "Search", icon: Search },
  { href: "/upload", label: "Tender Analysis", icon: FileUp },
  { href: "/compliance", label: "Compliance", icon: ShieldCheck },
  { href: "/standards", label: "Standards", icon: Library },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
];

export function SiteNav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4 sm:px-6">
        <Link href="/" className="flex shrink-0 items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-tricolor-saffron to-tricolor-green text-white shadow-sm">
            <Scale className="h-5 w-5" />
          </span>
          <span className="hidden flex-col leading-none sm:flex">
            <span className="text-sm font-bold tracking-tight">BIS Standards AI</span>
            <span className="text-[11px] text-muted-foreground">
              Indian Standards, retrieved and cited
            </span>
          </span>
        </Link>

        <nav className="flex flex-1 items-center gap-1 overflow-x-auto">
          {LINKS.map((link) => {
            const active =
              link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "flex items-center gap-1.5 whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  active
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                <link.icon className="h-4 w-4" />
                <span className={cn(link.href === "/search" && "hidden lg:inline")}>
                  {link.label}
                </span>
              </Link>
            );
          })}
        </nav>

        <div className="hidden shrink-0 md:block">
          <ApiStatus />
        </div>
      </div>
      <div className="tricolor-bar h-[3px] w-full" />
    </header>
  );
}
