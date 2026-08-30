import { ArrowUpRight, FileVideo, Image as ImageIcon, Link2, Loader2, Type } from "lucide-react";
import Link from "next/link";
import type { RecentVerification, SubmissionType } from "@/lib/api/schemas";
import { formatRelative } from "@/lib/utils";
import { VerdictBadge } from "./verdict-display";

const TYPE_ICONS: Record<SubmissionType, typeof Type> = {
  TEXT: Type,
  ARTICLE_URL: Link2,
  SOCIAL_URL: Link2,
  IMAGE: ImageIcon,
  SCREENSHOT: ImageIcon,
  IMAGE_WITH_CAPTION: ImageIcon,
  VIDEO: FileVideo,
  VIDEO_WITH_CAPTION: FileVideo,
};

const TYPE_LABELS: Record<SubmissionType, string> = {
  TEXT: "Text",
  ARTICLE_URL: "Article",
  SOCIAL_URL: "Social post",
  IMAGE: "Image",
  SCREENSHOT: "Screenshot",
  IMAGE_WITH_CAPTION: "Image",
  VIDEO: "Video",
  VIDEO_WITH_CAPTION: "Video",
};

export function RecentList({
  heading,
  description,
  items,
  emptyMessage,
}: {
  heading: string;
  description?: string;
  items: RecentVerification[];
  emptyMessage?: string;
}) {
  return (
    <section aria-labelledby={`heading-${heading.replace(/\s+/g, "-").toLowerCase()}`}>
      <div className="flex items-baseline justify-between gap-4 border-b border-rule pb-3">
        <h2
          id={`heading-${heading.replace(/\s+/g, "-").toLowerCase()}`}
          className="font-serif text-xl font-semibold"
        >
          {heading}
        </h2>
        {description ? (
          <p className="hidden text-sm text-muted sm:block">{description}</p>
        ) : null}
      </div>

      {items.length === 0 ? (
        <p className="py-8 text-sm text-muted">
          {emptyMessage ?? "Nothing here yet."}
        </p>
      ) : (
        <ul className="mt-4 grid gap-3">
          {items.map((item) => (
            <li key={item.public_id}>
              <VerificationRow item={item} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function VerificationRow({ item }: { item: RecentVerification }) {
  const Icon = TYPE_ICONS[item.content_type] ?? Type;
  const isRunning = item.status === "QUEUED" || item.status === "RUNNING";
  const summary = item.title || item.excerpt || "Untitled submission";

  return (
    <Link
      href={`/verify/${item.public_id}`}
      className="group flex items-start gap-4 rounded-xl border border-rule bg-white p-4 transition-all hover:-translate-y-0.5 hover:border-[var(--green)] hover:shadow-[0_8px_24px_rgba(0,75,56,.08)]"
    >
      <Icon
        className="mt-0.5 h-5 w-5 shrink-0 text-[var(--green)]"
        aria-hidden="true"
      />

      <div className="min-w-0 flex-1">
        <p className="line-clamp-2 text-sm leading-relaxed group-hover:underline">
          {summary}
        </p>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
          <span>{TYPE_LABELS[item.content_type]}</span>
          <span aria-hidden="true">·</span>
          <time dateTime={item.created_at}>
            {formatRelative(item.created_at)}
          </time>
        </div>
      </div>

      <div className="shrink-0">
        {isRunning ? (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-rule px-2.5 py-1 text-xs text-muted">
            <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
            Checking
          </span>
        ) : item.status === "FAILED" ? (
          // A processing failure is shown as a failure, never as a verdict
          // about the claim.
          <span className="inline-flex items-center rounded-full border border-rule px-2.5 py-1 text-xs text-muted">
            Could not check
          </span>
        ) : (
          <VerdictBadge verdict={item.overall_verdict} size="small" />
        )}
        <ArrowUpRight className="ml-auto mt-2 hidden h-4 w-4 text-muted transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 sm:block" aria-hidden="true" />
      </div>
    </Link>
  );
}
