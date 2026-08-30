import type { Metadata } from "next";
import { Inter, Source_Serif_4 } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { QueryProvider } from "@/components/query-provider";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

// Serif headlines carry the editorial character; the body stays in a neutral sans.
const sourceSerif = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-source-serif",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Evidence-Backed Verification",
  description:
    "Submit a claim, article, image, or video and see what the available evidence establishes — with sources you can check yourself.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${sourceSerif.variable}`}>
      <body className="min-h-screen flex flex-col">
        <QueryProvider>
          {/* Skip link: the first stop for keyboard and screen-reader users. */}
          <a
            href="#main"
            className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded focus:bg-surface focus:px-4 focus:py-2 focus:shadow-lg focus:ring-2"
          >
            Skip to main content
          </a>

          <div className="flag-frame" aria-hidden="true"><span /></div>
          <header className="site-header sticky top-0 z-40 border-b border-rule">
            <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-4 sm:py-5">
              <Link
                href="/"
                className="brand-mark group flex items-center gap-3"
              >
                <span className="brand-seal" aria-hidden="true">✓</span>
                <span>
                  <span className="block font-serif text-lg font-semibold leading-none tracking-tight">Evidence Check</span>
                  <span className="brand-bangla mt-1 block text-[11px] font-semibold tracking-[0.14em]">তথ্য যাচাই · বাংলাদেশ</span>
                </span>
              </Link>
              <nav aria-label="Main">
                <ul className="flex items-center gap-0.5 text-sm font-medium sm:gap-2">
                  <li>
                    <Link href="/recent" className="nav-link">
                      Recent
                    </Link>
                  </li>
                  <li>
                    <Link href="/method" className="nav-link">
                      Method
                    </Link>
                  </li>
                </ul>
              </nav>
            </div>
          </header>

          <main id="main" className="flex-1">
            {children}
          </main>

          <footer className="site-footer mt-16 border-t border-rule">
            <div className="mx-auto grid max-w-6xl gap-6 px-5 py-10 text-sm text-muted sm:grid-cols-[1fr_auto]">
              <div>
                <p className="max-w-2xl">
                  We report what the available evidence establishes. Coverage is
                  limited to our indexed sources — we do not search the whole web,
                  and we do not perform reverse image search.{" "}
                  <Link href="/method" className="underline">
                    How this works
                  </Link>
                  .
                </p>
                <p className="mt-3">
                  Results can be wrong and can change as new evidence appears.
                </p>
              </div>
              <p className="brand-bangla self-start text-right text-xs font-semibold text-[var(--green)]">
                সত্য যাচাই করুন · সূত্র দেখুন
              </p>
            </div>
          </footer>
        </QueryProvider>
      </body>
    </html>
  );
}
