"use client";

/**
 * Live progress.
 *
 * Every step shown is a real VerificationStage row from the backend. There is
 * no timer and no simulated sequence: if the worker stalls, this stops moving,
 * which is the honest behavior.
 */

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  AlertCircle,
  Check,
  CircleDashed,
  Loader2,
  MinusCircle,
} from "lucide-react";
import type { Stage, VerificationStatusResponse } from "@/lib/api/schemas";
import { getStatus } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { degradationLabel } from "@/lib/verdict";

export function ProgressView({
  publicId,
  initialStatus,
  onComplete,
}: {
  publicId: string;
  initialStatus?: VerificationStatusResponse;
  onComplete?: () => void;
}) {
  const [waitingLong, setWaitingLong] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setWaitingLong(true), 12_000);
    return () => window.clearTimeout(timer);
  }, []);

  const { data, error } = useQuery({
    queryKey: ["verification-status", publicId],
    queryFn: () => getStatus(publicId),
    initialData: initialStatus,
    // Poll while work is outstanding, then stop. Polling a finished
    // verification is pure waste.
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "COMPLETED" || status === "FAILED") {
        onComplete?.();
        return false;
      }
      return 1500;
    },
    refetchIntervalInBackground: false,
  });

  if (error) {
    return (
      <div
        role="alert"
        className="rounded-lg border border-red-300 bg-red-50 p-5 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/50 dark:text-red-100"
      >
        <p className="font-medium">Lost contact with the verification service.</p>
        <p className="mt-1 opacity-90">
          The check may still be running. Reload this page to try again.
        </p>
      </div>
    );
  }

  if (!data) {
    return <ProgressSkeleton />;
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-baseline justify-between gap-4">
          <h2 className="font-serif text-xl font-semibold">
            {data.status === "FAILED"
              ? "This check could not be completed"
              : "Checking this submission"}
          </h2>
          <span className="text-sm tabular-nums text-muted">
            {data.stage_index} of {data.stage_count}
          </span>
        </div>
        <p className="mt-1 text-sm text-muted">
          {data.status === "FAILED"
            ? "We stopped before reaching a result. Details below."
            : data.status === "QUEUED"
              ? "Your check is queued and will begin as soon as the verification worker is available."
              : "Each step below reflects real progress on our side."}
        </p>
      </div>

      {waitingLong && data.status === "QUEUED" ? (
        <div
          className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950"
          role="status"
        >
          <p className="font-semibold">This is taking longer than expected.</p>
          <p className="mt-1 leading-relaxed">
            The verification worker may be offline. You can leave this page
            open; checking will continue automatically when it reconnects.
          </p>
        </div>
      ) : null}

      <ol className="space-y-0.5">
        {data.stages.map((stage) => (
          <StageRow key={stage.stage} stage={stage} />
        ))}
        {/* Stages not yet started have no row server-side; show what remains. */}
        {data.status !== "FAILED" && data.stages.length < data.stage_count
          ? Array.from({ length: data.stage_count - data.stages.length }).map(
              (_, index) => (
                <li
                  key={`pending-${index}`}
                  className="flex items-center gap-3 py-2 text-sm text-muted"
                >
                  <CircleDashed className="h-4 w-4 shrink-0 opacity-40" aria-hidden="true" />
                  <span className="opacity-50">Waiting…</span>
                </li>
              ),
            )
          : null}
      </ol>

      {data.status === "FAILED" && data.error_message ? (
        <div
          role="alert"
          className="rounded-lg border border-rule bg-surface p-5"
        >
          <h3 className="text-sm font-semibold">What went wrong</h3>
          <p className="mt-2 text-sm leading-relaxed">{data.error_message}</p>
          <p className="mt-3 text-xs text-muted">
            This is a problem on our side, not a judgement about your
            submission. It does not mean the claim is false.
          </p>
        </div>
      ) : null}

      {data.degradation_reasons.length > 0 ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-5 text-sm dark:border-amber-900 dark:bg-amber-950/30">
          <h3 className="font-semibold">Limitations in this run</h3>
          <ul className="mt-2 space-y-1.5">
            {data.degradation_reasons.map((reason) => (
              <li key={reason} className="leading-relaxed opacity-90">
                {degradationLabel(reason)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function StageRow({ stage }: { stage: Stage }) {
  const { icon, tone, note } = stagePresentation(stage);

  return (
    <li className="flex items-center gap-3 py-2 text-sm">
      <span className="shrink-0">{icon}</span>
      <span className={cn("flex-1", tone)}>{stage.label}</span>
      {note ? <span className="text-xs text-muted">{note}</span> : null}
      {stage.duration_ms != null && stage.status === "COMPLETED" ? (
        <span className="shrink-0 text-xs tabular-nums text-muted">
          {stage.duration_ms < 1000
            ? `${stage.duration_ms}ms`
            : `${(stage.duration_ms / 1000).toFixed(1)}s`}
        </span>
      ) : null}
    </li>
  );
}

function stagePresentation(stage: Stage): {
  icon: React.ReactNode;
  tone: string;
  note?: string;
} {
  switch (stage.status) {
    case "COMPLETED":
      return {
        icon: <Check className="h-4 w-4 text-emerald-600 dark:text-emerald-400" aria-label="Completed" />,
        tone: "",
      };
    case "RUNNING":
      return {
        icon: <Loader2 className="h-4 w-4 animate-spin" aria-label="In progress" />,
        tone: "font-medium",
      };
    case "DEGRADED":
      // Distinguished from success: the step ran but could not do its full job.
      return {
        icon: <MinusCircle className="h-4 w-4 text-amber-600 dark:text-amber-400" aria-label="Completed with limitations" />,
        tone: "",
        note: "limited",
      };
    case "SKIPPED":
      return {
        icon: <MinusCircle className="h-4 w-4 opacity-40" aria-label="Skipped" />,
        tone: "text-muted",
        note: "not needed",
      };
    case "FAILED":
      return {
        icon: <AlertCircle className="h-4 w-4 text-red-600 dark:text-red-400" aria-label="Failed" />,
        tone: "text-red-700 dark:text-red-400",
      };
    default:
      return {
        icon: <CircleDashed className="h-4 w-4 opacity-40" aria-label="Pending" />,
        tone: "text-muted opacity-60",
      };
  }
}

function ProgressSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading progress">
      <div className="h-6 w-48 animate-pulse rounded bg-black/5 dark:bg-white/5" />
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="h-5 w-full animate-pulse rounded bg-black/5 dark:bg-white/5"
        />
      ))}
    </div>
  );
}
