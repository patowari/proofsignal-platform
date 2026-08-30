"use client";

import { LOCALES } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { useLocale } from "./locale-provider";

export function LanguageSwitcher() {
  const { locale, setLocale } = useLocale();

  return (
    <div
      className="flex items-center rounded-md border border-rule text-xs"
      role="group"
      aria-label="Language / ভাষা"
    >
      {LOCALES.map(({ code, nativeLabel }) => (
        <button
          key={code}
          type="button"
          onClick={() => setLocale(code)}
          aria-pressed={locale === code}
          className={cn(
            "px-2.5 py-1 transition-colors first:rounded-l-md last:rounded-r-md",
            locale === code
              ? "bg-[var(--foreground)] text-[var(--background)]"
              : "text-muted hover:text-current",
          )}
        >
          {nativeLabel}
        </button>
      ))}
    </div>
  );
}
