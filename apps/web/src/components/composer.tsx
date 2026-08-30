"use client";

/**
 * Submission composer.
 *
 * One control, four entry methods. No account required, and the UI says so.
 */

import { ArrowRight, FileVideo, Image as ImageIcon, Link2, Loader2, ShieldCheck, Type, Upload, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import {
  ApiError,
  submitImage,
  submitText,
  submitUrl,
  submitVideo,
} from "@/lib/api/client";
import { cn, formatBytes } from "@/lib/utils";
import { useLocale } from "./locale-provider";

type Mode = "text" | "url" | "image" | "video";

const MODES: { id: Mode; labelKey: "tabText" | "tabLink" | "tabImage" | "tabVideo"; icon: typeof Type }[] = [
  { id: "text", labelKey: "tabText", icon: Type },
  { id: "url", labelKey: "tabLink", icon: Link2 },
  { id: "image", labelKey: "tabImage", icon: ImageIcon },
  { id: "video", labelKey: "tabVideo", icon: FileVideo },
];

// Mirrors the backend caps. The server is authoritative; these exist to fail
// fast and explain the limit before a long upload.
const MAX_IMAGE_BYTES = 15 * 1024 * 1024;
const MAX_VIDEO_BYTES = 200 * 1024 * 1024;

const PLACEHOLDERS: Record<Mode, string> = {
  text: "Paste a claim, headline, article, or social post you want checked…",
  url: "https://example.com/news/article",
  image: "",
  video: "",
};

export function Composer() {
  const { t } = useLocale();
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("text");
  const [text, setText] = useState("");
  const [caption, setCaption] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [isScreenshot, setIsScreenshot] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isMedia = mode === "image" || mode === "video";
  const maxBytes = mode === "video" ? MAX_VIDEO_BYTES : MAX_IMAGE_BYTES;
  const isReady = isMedia
    ? Boolean(file) && caption.trim().length >= 10
    : text.trim().length >= 10;

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
    setFile(null);
  }

  function handleFile(selected: File | null) {
    setError(null);
    if (!selected) {
      setFile(null);
      return;
    }
    if (selected.size > maxBytes) {
      setError(
        `That file is ${formatBytes(selected.size)}. The limit is ${formatBytes(maxBytes)}.`,
      );
      setFile(null);
      return;
    }
    setFile(selected);
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    if (isMedia && !file) {
      setError(`Choose ${mode === "video" ? "a video" : "an image"} to verify.`);
      return;
    }
    if (isMedia && caption.trim().length < 10) {
      setError(
        "Add a short caption describing the factual claim in this file (at least 10 characters).",
      );
      return;
    }
    if (!isMedia && text.trim().length < 10) {
      setError(
        mode === "url"
          ? t("errorNeedUrl")
          : t("errorTooShort"),
      );
      return;
    }

    setSubmitting(true);
    try {
      const result =
        mode === "text"
          ? await submitText(text.trim())
          : mode === "url"
            ? await submitUrl(text.trim())
            : mode === "image"
              ? await submitImage(file!, caption.trim(), isScreenshot)
              : await submitVideo(file!, caption.trim());

      router.push(`/verify/${result.verification_public_id}`);
    } catch (caught) {
      // Show the backend's own message: it explains the specific reason (an
      // unreachable URL, a file whose contents do not match its type).
      if (caught instanceof ApiError) {
        setError(
          caught.isRateLimited
            ? t("errorRateLimited")
            : caught.message,
        );
      } else {
        setError(t("errorGeneric"));
      }
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div className="composer-shell overflow-hidden rounded-xl border border-rule bg-surface">
        {/* Mode selector */}
        <div
          role="tablist"
          aria-label="What do you want to verify?"
          className="grid grid-cols-4 border-b border-rule"
        >
          {MODES.map(({ id, labelKey, icon: Icon }) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={mode === id}
              aria-controls="composer-panel"
              onClick={() => switchMode(id)}
              className={cn(
                "flex min-h-12 items-center justify-center gap-1.5 px-2 py-3 text-xs font-semibold transition-colors sm:gap-2 sm:px-5 sm:text-sm",
                mode === id
                  ? "-mb-px border-b-2 border-[var(--red)] bg-[var(--red-soft)] text-[var(--red)]"
                  : "text-muted hover:text-current",
              )}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {t(labelKey)}
            </button>
          ))}
        </div>

        <div id="composer-panel" role="tabpanel" className="p-4 sm:p-5">
          {!isMedia ? (
            <>
              <label htmlFor="composer-input" className="mb-2 block text-sm font-semibold">
                {mode === "url" ? "Link to verify" : "Text to verify"}
              </label>
              {mode === "url" ? (
                <input
                  id="composer-input"
                  type="url"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder={PLACEHOLDERS[mode]}
                  className="min-h-12 w-full rounded-lg border border-rule bg-white px-4 text-base outline-none transition-colors placeholder:text-muted focus:border-[var(--green)]"
                  autoComplete="url"
                  spellCheck={false}
                />
              ) : (
                <textarea
                  id="composer-input"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder={PLACEHOLDERS[mode]}
                  rows={5}
                  maxLength={50_000}
                  className="min-h-36 w-full resize-y rounded-lg border border-rule bg-white p-4 text-base leading-relaxed outline-none transition-colors placeholder:text-muted focus:border-[var(--green)]"
                />
              )}
              <div className="mt-2 flex items-center justify-between gap-3 text-xs text-muted">
                <span>
                  {mode === "url" ? t("pasteFullUrl") : t("bothLanguages")}
                </span>
                {mode === "text" ? <span className="tabular-nums">{text.length.toLocaleString()} / 50,000</span> : null}
              </div>
            </>
          ) : (
            <MediaPicker
              mode={mode}
              file={file}
              maxBytes={maxBytes}
              inputRef={fileInputRef}
              onSelect={handleFile}
              caption={caption}
              onCaption={setCaption}
              isScreenshot={isScreenshot}
              onScreenshot={setIsScreenshot}
            />
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-rule px-4 py-3 sm:px-5">
          <p className="flex items-center gap-1.5 text-xs text-muted">
            <ShieldCheck className="h-3.5 w-3.5 text-[var(--green)]" aria-hidden="true" />
            {mode === "text" || mode === "url"
              ? t("noAccountNeeded")
              : `${formatBytes(maxBytes)} — ${t("noAccountNeeded")}`}
          </p>
          <button
            type="submit"
            disabled={submitting || !isReady}
            className="verify-button inline-flex items-center gap-2 rounded-md px-6 py-2.5 text-sm font-semibold text-white transition-all disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                {t("verifying")}
              </>
            ) : (
              <><span>{t("checkThisClaim")}</span><ArrowRight className="h-4 w-4" aria-hidden="true" /></>
            )}
          </button>
        </div>
      </div>

      {error ? (
        <p
          role="alert"
          aria-live="polite"
          className="mt-3 rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/50 dark:text-red-100"
        >
          {error}
        </p>
      ) : null}
    </form>
  );
}

function MediaPicker({
  mode,
  file,
  maxBytes,
  inputRef,
  onSelect,
  caption,
  onCaption,
  isScreenshot,
  onScreenshot,
}: {
  mode: "image" | "video";
  file: File | null;
  maxBytes: number;
  inputRef: React.RefObject<HTMLInputElement | null>;
  onSelect: (file: File | null) => void;
  caption: string;
  onCaption: (value: string) => void;
  isScreenshot: boolean;
  onScreenshot: (value: boolean) => void;
}) {
  const accept =
    mode === "image"
      ? "image/jpeg,image/png,image/gif,image/webp"
      : "video/mp4,video/quicktime,video/webm,video/x-matroska";

  return (
    <div className="space-y-4">
      {file ? (
        <div className="flex items-center justify-between gap-3 rounded-md border border-rule px-4 py-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{file.name}</p>
            <p className="text-xs text-muted">{formatBytes(file.size)}</p>
          </div>
          <button
            type="button"
            onClick={() => onSelect(null)}
            className="rounded p-1 text-muted hover:text-current"
            aria-label="Remove selected file"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="flex w-full flex-col items-center gap-2 rounded-lg border-2 border-dashed border-rule bg-[var(--green-soft)]/40 px-4 py-9 text-center transition-colors hover:border-[var(--green)] hover:bg-[var(--green-soft)]"
        >
          <Upload className="h-6 w-6 text-muted" aria-hidden="true" />
          <span className="text-sm font-medium">
            Choose {mode === "video" ? "a video" : "an image"}
          </span>
          <span className="text-xs text-muted">
            {mode === "image"
              ? "JPEG, PNG, GIF, or WebP"
              : "MP4, MOV, WebM, or MKV"}{" "}
            · up to {formatBytes(maxBytes)}
          </span>
        </button>
      )}

      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="sr-only"
        onChange={(e) => onSelect(e.target.files?.[0] ?? null)}
      />

      <div>
        <label htmlFor="composer-caption" className="text-sm font-medium">
          Claim shown in this file{" "}
          <span className="font-normal text-[var(--red)]">(required)</span>
        </label>
        {/* The caption is verified as its own claim: an authentic file can carry
            a false caption, and the report keeps those separate. */}
        <p className="mt-0.5 text-xs text-muted">
          Describe what this is said to show. This gives the checker a factual
          claim it can assess immediately.
        </p>
        <input
          id="composer-caption"
          type="text"
          value={caption}
          onChange={(e) => onCaption(e.target.value)}
          placeholder="e.g. This shows flooding in Dhaka this week"
          required
          minLength={10}
          maxLength={2000}
          className="mt-2 w-full rounded-md border border-rule bg-transparent px-3 py-2 text-sm outline-none focus:border-current"
        />
      </div>

      {mode === "image" ? (
        <label className="flex items-start gap-2.5 text-sm">
          <input
            type="checkbox"
            checked={isScreenshot}
            onChange={(e) => onScreenshot(e.target.checked)}
            className="mt-0.5 h-4 w-4"
          />
          <span>
            This is a screenshot
            <span className="block text-xs text-muted">
              We read the visible text and check the claim it shows. A
              screenshot is not proof the original post is genuine.
            </span>
          </span>
        </label>
      ) : null}
    </div>
  );
}
