"use client";

/**
 * The verification page.
 *
 * One URL for the whole lifecycle: it shows live progress while the worker
 * runs, then becomes the report. The link a user copies mid-check stays valid
 * and resolves to the finished result.
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { getVerification } from "@/lib/api/client";
import type {
  VerificationReport,
  VerificationStatusResponse,
} from "@/lib/api/schemas";
import { ProgressView } from "./progress-view";
import { ReportView } from "./report-view";

export function VerificationPage({
  publicId,
  initialReport,
  initialStatus,
  unreachable,
}: {
  publicId: string;
  initialReport: VerificationReport | null;
  initialStatus?: VerificationStatusResponse;
  unreachable: boolean;
}) {
  const queryClient = useQueryClient();
  const [finished, setFinished] = useState(
    initialReport?.status === "COMPLETED" || initialReport?.status === "FAILED",
  );

  const { data: report } = useQuery({
    queryKey: ["verification", publicId],
    queryFn: () => getVerification(publicId),
    initialData: initialReport ?? undefined,
    // Only fetch the full report once there is something to report; while the
    // check runs, the cheap status endpoint drives the UI.
    enabled: finished,
  });

  if (unreachable && !initialReport) {
    return (
      <div
        role="alert"
        className="rounded-lg border border-red-300 bg-red-50 p-6 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/50 dark:text-red-100"
      >
        <h1 className="font-serif text-xl font-semibold">
          Cannot reach the verification service
        </h1>
        <p className="mt-2 opacity-90">
          This result exists but we could not load it. Try reloading in a
          moment.
        </p>
      </div>
    );
  }

  const isRunning =
    !finished && (!report || report.status === "QUEUED" || report.status === "RUNNING");

  if (isRunning) {
    return (
      <ProgressView
        publicId={publicId}
        initialStatus={initialStatus}
        onComplete={() => {
          // Pull the full report once, then swap views.
          void queryClient.invalidateQueries({
            queryKey: ["verification", publicId],
          });
          setFinished(true);
        }}
      />
    );
  }

  if (!report) {
    return <ReportSkeleton />;
  }

  if (report.status === "FAILED") {
    return <FailedReport report={report} />;
  }

  return <ReportView report={report} />;
}

/**
 * A failed check.
 *
 * Deliberately never renders a verdict: our inability to check something says
 * nothing about whether the claim is true.
 */
function FailedReport({ report }: { report: VerificationReport }) {
  return (
    <div className="space-y-8">
      <section className="rounded-lg border border-rule bg-surface p-6 sm:p-8">
        <p className="text-xs font-medium uppercase tracking-widest text-muted">
          No result
        </p>
        <h1 className="mt-1 font-serif text-3xl font-semibold">
          We could not complete this check
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted">
          Something went wrong on our side before we reached a conclusion. This
          is not a judgement about the submission — it does not mean the claim
          is false or true.
        </p>
      </section>

      {report.error_message ? (
        <section className="rounded-lg border border-rule bg-surface p-5">
          <h2 className="text-sm font-semibold">What happened</h2>
          <p className="mt-2 text-sm leading-relaxed">{report.error_message}</p>
        </section>
      ) : null}

      {report.submission.text || report.submission.submitted_url ? (
        <section>
          <h2 className="border-b border-rule pb-3 font-serif text-xl font-semibold">
            What was submitted
          </h2>
          <div className="mt-4 rounded-lg border border-rule bg-surface p-5">
            {report.submission.text ? (
              <p className="whitespace-pre-wrap text-sm leading-relaxed" dir="auto">
                {report.submission.text}
              </p>
            ) : null}
            {report.submission.submitted_url ? (
              <div className="scroll-x">
                <span className="break-all text-sm">
                  {report.submission.submitted_url}
                </span>
              </div>
            ) : null}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function ReportSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading report">
      <div className="h-40 animate-pulse rounded-lg bg-black/5 dark:bg-white/5" />
      <div className="h-6 w-3/4 animate-pulse rounded bg-black/5 dark:bg-white/5" />
      <div className="h-32 animate-pulse rounded-lg bg-black/5 dark:bg-white/5" />
    </div>
  );
}
