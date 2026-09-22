import type { Metadata } from "next";
import localFont from "next/font/local";
import Link from "next/link";

import { SiteNav } from "@/components/site-nav";
import "./globals.css";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: {
    default: "BIS Standards AI",
    template: "%s · BIS Standards AI",
  },
  description:
    "Search 197 Indian Standards, analyse tender PDFs, and check product compliance against BIS Quality Control Orders — with citations for every answer.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en-IN">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <div className="flex min-h-screen flex-col">
          <SiteNav />
          <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6">{children}</main>
          <footer className="mt-12 border-t">
            <div className="tricolor-bar h-[3px] w-full" />
            <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-6 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
              <p>
                BIS Standards AI · Smart India Hackathon PS 26108 · built on{" "}
                <a
                  href="https://archive.org/details/gov.in.is"
                  target="_blank"
                  rel="noreferrer noopener"
                  className="underline hover:text-foreground"
                >
                  archive.org&apos;s CC0 Indian Standards collection
                </a>
              </p>
              <nav className="flex gap-4">
                <Link href="/standards" className="hover:text-foreground hover:underline">
                  Standards
                </Link>
                <Link href="/dashboard" className="hover:text-foreground hover:underline">
                  Dashboard
                </Link>
                <a
                  href="/docs"
                  target="_blank"
                  rel="noreferrer noopener"
                  className="hover:text-foreground hover:underline"
                >
                  API docs
                </a>
              </nav>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
