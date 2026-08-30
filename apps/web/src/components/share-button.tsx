"use client";

import { Check, Link2 } from "lucide-react";
import { useState } from "react";
import { useLocale } from "./locale-provider";

export function ShareButton({ publicId }: { publicId: string }) {
  const { t } = useLocale();
  const [copied, setCopied] = useState(false);

  async function copy() {
    const url = `${window.location.origin}/verify/${publicId}`;
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      // Clipboard access can be denied; selecting the URL still works.
      window.prompt("Copy this link:", url);
      return;
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <button
      type="button"
      onClick={copy}
      className="inline-flex items-center gap-2 rounded-md border border-rule px-4 py-2 text-sm font-medium transition-colors hover:bg-black/[0.03] dark:hover:bg-white/[0.05]"
    >
      {copied ? (
        <>
          <Check className="h-4 w-4" aria-hidden="true" />
          {t("linkCopied")}
        </>
      ) : (
        <>
          <Link2 className="h-4 w-4" aria-hidden="true" />
          {t("copyLink")}
        </>
      )}
    </button>
  );
}
