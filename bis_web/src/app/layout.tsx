import type { Metadata } from 'next';
import { Analytics } from '@vercel/analytics/react';
import './globals.css';

export const metadata: Metadata = {
  title: 'BIS Standards AI - Find Indian Standards Instantly',
  description: 'AI-powered product to standards recommender for Indian Standards. Search 1,334+ verified standards instantly.',
  icons: {
    icon: '🏛️',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="bg-slate-950 text-white antialiased">
        <div className="relative">
          {children}
          <Analytics />
        </div>
      </body>
    </html>
  );
}
