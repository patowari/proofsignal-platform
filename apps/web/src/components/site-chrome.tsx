"use client";

import Link from "next/link";
import { LanguageSwitcher } from "./language-switcher";
import { useLocale } from "./locale-provider";

/** Header, footer, and skip link, all locale-aware. */
export function SiteChrome({ children }: { children: React.ReactNode }) {
  const { t } = useLocale();

  return (
    <>
      {/* First stop for keyboard and screen-reader users. */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded focus:bg-surface focus:px-4 focus:py-2 focus:shadow-lg focus:ring-2"
      >
        {t("skipToContent")}
      </a>

      <header className="border-b border-rule">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-5 py-4">
          <Link href="/" className="font-serif text-lg font-semibold tracking-tight">
            {t("siteName")}
          </Link>
          <div className="flex items-center gap-4">
            <nav aria-label="Main">
              <ul className="flex items-center gap-5 text-sm">
                <li>
                  <Link href="/recent" className="hover:underline">
                    {t("navRecent")}
                  </Link>
                </li>
                <li>
                  <Link href="/method" className="hover:underline">
                    {t("navMethod")}
                  </Link>
                </li>
              </ul>
            </nav>
            <LanguageSwitcher />
          </div>
        </div>
      </header>

      <main id="main" className="flex-1">
        {children}
      </main>

      <footer className="mt-16 border-t border-rule">
        <div className="mx-auto max-w-5xl px-5 py-8 text-sm text-muted">
          <p className="max-w-2xl">
            {t("footerCoverage")}{" "}
            <Link href="/method" className="underline">
              {t("howThisWorks")}
            </Link>
            .
          </p>
          <p className="mt-3">{t("footerFallible")}</p>
        </div>
      </footer>
    </>
  );
}
