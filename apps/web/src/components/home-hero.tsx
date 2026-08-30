"use client";

import Link from "next/link";
import { Composer } from "./composer";
import { useLocale } from "./locale-provider";

/**
 * Homepage hero and composer.
 *
 * A client component so the copy follows the selected language; the page
 * itself stays a server component and keeps fetching recent verifications
 * on the server.
 */
export function HomeHero() {
  const { t } = useLocale();
  const [asideLine1, asideLine2] = t("asideTagline").split("\n");

  return (
    <>
      <section className="hero-grid">
        <div>
          <p className="section-kicker">{t("heroKicker")}</p>
          <h1 className="mt-3 font-serif text-5xl font-semibold leading-[1.05] tracking-tight sm:text-6xl">
            {t("heroLine1")}
            <br />
            <em className="not-italic text-[var(--green)]">{t("heroLine2")}</em>
          </h1>
          <p className="mt-5 max-w-xl text-base leading-relaxed text-muted">
            {t("heroPitch")}
          </p>
          <div className="mt-7 flex flex-wrap gap-x-6 gap-y-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--green)]">
            <span>{t("badgeSources")}</span>
            <span>{t("badgeVerdicts")}</span>
            <span>{t("badgeNoAccount")}</span>
          </div>
        </div>

        <aside className="hero-note" aria-label={t("heroKicker")}>
          <p className="brand-bangla text-3xl font-bold leading-tight">
            {asideLine1}
            <br />
            {asideLine2}
          </p>
          <div className="my-5 h-px bg-white/25" />
          <p className="text-sm leading-relaxed text-white/75">
            {t("asideBody")}
          </p>
        </aside>
      </section>

      <section
        className="mx-auto mt-12 max-w-4xl"
        aria-label={t("whatToVerify")}
      >
        <div className="mb-3 flex items-end justify-between gap-4">
          <div>
            <p className="section-kicker">{t("startCheck")}</p>
            <h2 className="mt-1 font-serif text-2xl font-semibold">
              {t("whatToVerify")}
            </h2>
          </div>
          <span className="hidden text-xs text-muted sm:block">
            {t("privacyHint")}
          </span>
        </div>
        <Composer />
      </section>

      <section className="mx-auto mt-5 max-w-4xl">
        <p className="text-center text-xs leading-relaxed text-muted">
          {t("honestyNote")}{" "}
          <Link href="/method" className="underline">
            {t("readMethod")}
          </Link>
          .
        </p>
      </section>
    </>
  );
}
