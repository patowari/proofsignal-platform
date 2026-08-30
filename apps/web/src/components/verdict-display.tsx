/**
 * Verdict presentation components.
 *
 * Accessibility rule throughout: a verdict is never communicated by color
 * alone. Every element pairs color with an icon and explicit text, so it reads
 * correctly in greyscale and to a screen reader.
 */

import {
  CheckCircle2,
  CircleCheckBig,
  CircleHelp,
  CircleSlash,
  MessageCircle,
  Smile,
  TriangleAlert,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import type { ConfidenceBand, Verdict } from "@/lib/api/schemas";
import { cn } from "@/lib/utils";
import {
  CONFIDENCE_LABEL,
  CONFIDENCE_MEANING,
  CONFIDENCE_STEPS,
  verdictPresentation,
} from "@/lib/verdict";

const ICONS: Record<string, LucideIcon> = {
  "check-circle": CheckCircle2,
  "circle-check-big": CircleCheckBig,
  "circle-slash": CircleSlash,
  "triangle-alert": TriangleAlert,
  "circle-help": CircleHelp,
  "x-circle": XCircle,
  smile: Smile,
  "message-circle": MessageCircle,
};

export function VerdictBanner({
  verdict,
  confidence,
  className,
}: {
  verdict: Verdict | null | undefined;
  confidence?: ConfidenceBand | null;
  className?: string;
}) {
  const presentation = verdictPresentation(verdict);
  const Icon = ICONS[presentation.icon] ?? CircleHelp;

  return (
    <section
      aria-labelledby="verdict-heading"
      className={cn("rounded-lg border p-6 sm:p-8", presentation.banner, className)}
    >
      <div className="flex items-start gap-4">
        <Icon className="mt-1 h-8 w-8 shrink-0" aria-hidden="true" />
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-widest opacity-70">
            Overall verdict
          </p>
          <h2
            id="verdict-heading"
            className="mt-1 font-serif text-3xl font-semibold sm:text-4xl"
          >
            {presentation.label}
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed opacity-90">
            {presentation.meaning}
          </p>
          {confidence ? (
            <div className="mt-5">
              <ConfidenceMeter band={confidence} />
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

/**
 * Confidence as a three-step meter.
 *
 * Deliberately not a percentage: the underlying score is uncalibrated, and
 * rendering "82%" would imply a precision we have not earned.
 */
export function ConfidenceMeter({
  band,
  className,
}: {
  band: ConfidenceBand;
  className?: string;
}) {
  const filled = CONFIDENCE_STEPS[band];

  return (
    <div className={className}>
      <div className="flex items-center gap-2">
        <div
          className="flex gap-1"
          role="img"
          aria-label={`${CONFIDENCE_LABEL[band]}: ${filled} of 3`}
        >
          {[1, 2, 3].map((step) => (
            <span
              key={step}
              className={cn(
                "h-1.5 w-8 rounded-full",
                step <= filled ? "bg-current opacity-80" : "bg-current opacity-20",
              )}
            />
          ))}
        </div>
        <span className="text-sm font-medium">{CONFIDENCE_LABEL[band]}</span>
      </div>
      <p className="mt-1.5 text-xs opacity-75">{CONFIDENCE_MEANING[band]}</p>
    </div>
  );
}

export function VerdictBadge({
  verdict,
  size = "default",
  className,
}: {
  verdict: Verdict | null | undefined;
  size?: "default" | "small";
  className?: string;
}) {
  const presentation = verdictPresentation(verdict);
  const Icon = ICONS[presentation.icon] ?? CircleHelp;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border font-medium",
        size === "small" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm",
        presentation.badge,
        className,
      )}
    >
      <Icon
        className={size === "small" ? "h-3 w-3" : "h-3.5 w-3.5"}
        aria-hidden="true"
      />
      {presentation.label}
    </span>
  );
}
