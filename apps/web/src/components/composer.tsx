"use client";

/**
 * Submission composer.
 *
 * One control, four entry methods. No account required, and the UI says so.
 */

import { FileVideo, Image as ImageIcon, Link2, Loader2, Type, Upload, X } from "lucide-react";
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

type Mode = "text" | "url" | "image" | "video";

const MODES: { id: Mode; label: string; icon: typeof Type }[] = [
  { id: "text", label: "Text", icon: Type },
  { id: "url", label: "Link", icon: Link2 },
  { id: "image", label: "Image", icon: ImageIcon },
  { id: "video", label: "Video", icon: FileVideo },
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
    if (!isMedia && text.trim().length < 10) {
      setError(
        mode === "url"
          ? "Enter the full link, including https://"
          : "Enter at least a sentence so we have something to check.",
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
              ? await submitImage(file!, caption || undefined, isScreenshot)
              : await submitVideo(file!, caption || undefined);

      router.push(`/verify/${result.verification_public_id}`);
    } catch (caught) {
      // Show the backend's own message: it explains the specific reason (an
      // unreachable URL, a file whose contents do not match its type).
      if (caught instanceof ApiError) {
        setError(
          caught.isRateLimited
            ? "You have made several submissions recently. Please wait a little before trying again."
            : caught.message,
        );
      } else {
        setError("Something went wrong submitting this. Please try again.");
      }
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div className="rounded-lg border border-rule bg-surface shadow-sm">
        {/* Mode selector */}
        <div
          role="tablist"
          aria-label="What do you want to verify?"
          className="flex border-b border-rule"
        >
          {MODES.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={mode === id}
              aria-controls="composer-panel"
              onClick={() => switchMode(id)}
              className={cn(
                "flex flex-1 items-center justify-center gap-2 px-3 py-3 text-sm font-medium transition-colors sm:flex-none sm:px-5",
                mode === id
                  ? "border-b-2 border-current -mb-px"
                  : "text-muted hover:text-current",
              )}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {label}
            </button>
          ))}
        </div>

        <div id="composer-panel" role="tabpanel" className="p-4 sm:p-5">
          {!isMedia ? (
            <>
              <label htmlFor="composer-input" className="sr-only">
                {mode === "url" ? "Link to verify" : "Text to verify"}
              </label>
              {mode === "url" ? (
                <input
                  id="composer-input"
                  type="url"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder={PLACEHOLDERS[mode]}
                  className="w-full bg-transparent text-base outline-none placeholder:text-muted"
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
                  className="w-full resize-y bg-transparent text-base leading-relaxed outline-none placeholder:text-muted"
                />
              )}
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
          <p className="text-xs text-muted">
            {mode === "text" || mode === "url"
              ? "No account needed. Results are public."
              : `Up to ${formatBytes(maxBytes)}. Results are public.`}
          </p>
          <button
            type="submit"
            disabled={submitting}
            className="inline-flex items-center gap-2 rounded-md bg-[var(--foreground)] px-5 py-2 text-sm font-medium text-[var(--background)] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Submitting…
              </>
            ) : (
              "Verify"
            )}
          </button>
        </div>
      </div>

      {error ? (
        <p
          role="alert"
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
          className="flex w-full flex-col items-center gap-2 rounded-md border border-dashed border-rule px-4 py-8 text-center transition-colors hover:border-current"
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
          Caption or context{" "}
          <span className="font-normal text-muted">(optional)</span>
        </label>
        {/* The caption is verified as its own claim: an authentic file can carry
            a false caption, and the report keeps those separate. */}
        <p className="mt-0.5 text-xs text-muted">
          What is this said to show? We check the caption separately from the
          file itself.
        </p>
        <input
          id="composer-caption"
          type="text"
          value={caption}
          onChange={(e) => onCaption(e.target.value)}
          placeholder="e.g. Flooding in Dhaka this week"
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
