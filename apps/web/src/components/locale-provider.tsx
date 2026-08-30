"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { Locale } from "@/lib/i18n";
import { STRINGS, type StringKey } from "@/lib/i18n";

interface LocaleContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: StringKey) => string;
}

const LocaleContext = createContext<LocaleContextValue>({
  locale: "en",
  setLocale: () => {},
  t: (key) => STRINGS[key].en,
});

const STORAGE_KEY = "verifier.locale";

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  // Always start at "en" so server and client render identically; the stored
  // preference is applied after mount. Reading localStorage during render
  // would produce a hydration mismatch.
  const [locale, setLocaleState] = useState<Locale>("en");

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored === "bn" || stored === "en") {
        setLocaleState(stored);
        return;
      }
      // No stored choice: follow the browser, since a Bangla speaker should not
      // have to find the switch first.
      if (navigator.language?.toLowerCase().startsWith("bn")) {
        setLocaleState("bn");
      }
    } catch {
      // Private mode or blocked storage: English is a safe default.
    }
  }, []);

  useEffect(() => {
    // Keep the document language accurate for screen readers and for font
    // fallback on Bengali text.
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Preference simply will not persist; the session still works.
    }
  }, []);

  const t = useCallback((key: StringKey) => STRINGS[key][locale], [locale]);

  return (
    <LocaleContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </LocaleContext.Provider>
  );
}

export function useLocale() {
  return useContext(LocaleContext);
}
