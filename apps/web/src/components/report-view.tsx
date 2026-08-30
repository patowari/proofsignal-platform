"use client";

/**
 * Verification report.
 *
 * Visual priority, in order: verdict, claims, evidence, explanation.
 * Contradicting evidence is always shown, whatever the overall verdict --
 * hiding it would defeat the point of the product.
 */

import {
  CircleHelp,
  ExternalLink,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import type {
  Claim,
  Evidence,
  MediaAnalysis,
  VerificationReport,
} from "@/lib/api/schemas";
import {
  degradationCopy,
  originCopy,
  relationshipCopy,
  type Locale,
} from "@/lib/i18n";
import { cn, formatDate, hostFromUrl } from "@/lib/utils";
import { claimTypeLabel } from "@/lib/verdict";
import { useLocale } from "./locale-provider";
import { ShareButton } from "./share-button";
import { VerdictBadge, VerdictBanner } from "./verdict-display";

export function ReportView({ report }: { report: VerificationReport }) {
  const { locale, t } = useLocale();
  const unresolved = report.claims.filter(
    (c) => !c.verdict || c.verdict === "UNVERIFIED",
  );
  const hasEvidence = report.total_evidence > 0;

  return (
    <article className="space-y-10 sm:space-y-12">
      {/* 1. VERDICT */}
      <VerdictBanner
        verdict={report.overall_verdict}
        confidence={report.confidence_band}
      />

      {report.summary ? (
        <section aria-labelledby="summary-heading">
          <h2 id="summary-heading" className="sr-only">
            Summary
          </h2>
          <p className="font-serif text-lg leading-relaxed sm:text-xl">
            {report.summary}
          </p>
        </section>
      ) : null}

      {report.degradation_reasons.length > 0 ? (
        <LimitationsPanel reasons={report.degradation_reasons} />
      ) : null}

      <OriginalSubmission report={report} />

      {/* 2. CLAIMS */}
      {report.claims.length > 0 ? (
        <section aria-labelledby="claims-heading">
          <SectionHeading
            id="claims-heading"
            title={t("claimsWeChecked")}
            description={
            locale === "bn"
              ? `${report.claims.length}টি দাবি আলাদাভাবে যাচাই করা হয়েছে।`
              : `${report.claims.length} ${
                  report.claims.length === 1 ? "claim" : "claims"
                } extracted from this submission, each checked separately.`
          }
          />
          <ol className="mt-5 space-y-4">
            {report.claims.map((claim, index) => (
              <li key={`${claim.sequence}-${index}`}>
                <ClaimCard claim={claim} index={index + 1} locale={locale} />
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {/* 3. EVIDENCE */}
      <section aria-labelledby="evidence-heading">
        <SectionHeading
          id="evidence-heading"
          title={t("evidence")}
          description={
            hasEvidence
              ? `${report.independent_origins} independent ${
                  report.independent_origins === 1 ? "source" : "sources"
                } behind ${report.total_evidence} ${
                  report.total_evidence === 1 ? "item" : "items"
                }.`
              : undefined
          }
        />
        {hasEvidence ? (
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <EvidenceTally
              tone="support"
              count={report.supporting_evidence}
              label={t("supporting")}
            />
            <EvidenceTally
              tone="contradict"
              count={report.contradicting_evidence}
              label={t("contradicting")}
            />
          </div>
        ) : (
          <NoEvidencePanel />
        )}
      </section>

      {/* 4. WHAT REMAINS UNKNOWN */}
      {unresolved.length > 0 ? (
        <section aria-labelledby="unknown-heading">
          <SectionHeading
            id="unknown-heading"
            title={t("whatRemainsUnknown")}
            description={t("unknownSubtitle")}
          />
          <ul className="mt-5 space-y-3">
            {unresolved.map((claim, index) => (
              <li
                key={`unresolved-${index}`}
                className="flex gap-3 rounded-lg border border-rule bg-surface p-4"
              >
                <CircleHelp
                  className="mt-0.5 h-4 w-4 shrink-0 text-muted"
                  aria-hidden="true"
                />
                <p className="text-sm leading-relaxed">{claim.claim_text}</p>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-sm text-muted">
            {t("unverifiedNotFalse")}
          </p>
        </section>
      ) : null}

      {report.media_analyses.length > 0 ? (
        <MediaAnalysisSection analyses={report.media_analyses} />
      ) : null}

      <MethodologySection report={report} />

      <div className="flex flex-wrap items-center gap-3 border-t border-rule pt-6">
        <ShareButton publicId={report.public_id} />
      </div>
    </article>
  );
}

function SectionHeading({
  id,
  title,
  description,
}: {
  id: string;
  title: string;
  description?: string;
}) {
  return (
    <div className="border-b border-rule pb-3">
      <h2 id={id} className="font-serif text-2xl font-semibold">
        {title}
      </h2>
      {description ? (
        <p className="mt-1 text-sm text-muted">{description}</p>
      ) : null}
    </div>
  );
}

function ClaimCard({
  claim,
  index,
  locale,
}: {
  claim: Claim;
  index: number;
  locale: Locale;
}) {
  const { t } = useLocale();
  const supporting = claim.evidence.filter((e) => e.relationship === "SUPPORTS");
  const contradicting = claim.evidence.filter(
    (e) => e.relationship === "CONTRADICTS",
  );

  return (
    <div className="rounded-xl border border-rule bg-surface p-5 shadow-[0_4px_16px_rgba(0,0,0,.025)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-xs text-muted">
            <span className="font-medium">
              {t("claimLabel")} {index}
            </span>
            <span aria-hidden="true">·</span>
            <span>{claimTypeLabel(claim.claim_type)}</span>
            {/* Origin matters: an authentic file can carry a false caption. */}
            {claim.origin !== "USER_TEXT" ? (
              <>
                <span aria-hidden="true">·</span>
                <span>{originCopy(claim.origin, locale)}</span>
              </>
            ) : null}
          </div>
          <p
            className="mt-2 leading-relaxed"
            lang={claim.language}
            dir="auto"
          >
            {claim.claim_text}
          </p>
        </div>
        <VerdictBadge verdict={claim.verdict} size="small" />
      </div>

      {claim.evidence.length > 0 ? (
        <div className="mt-5 space-y-4 border-t border-rule pt-4">
          {supporting.length > 0 ? (
            <EvidenceGroup
              title={t("supportingEvidence")}
              items={supporting}
              tone="support"
              locale={locale}
            />
          ) : null}
          {/* Always rendered when present, even under a positive verdict. */}
          {contradicting.length > 0 ? (
            <EvidenceGroup
              title={t("contradictingEvidence")}
              items={contradicting}
              tone="contradict"
              locale={locale}
            />
          ) : null}
        </div>
      ) : (
        <p className="mt-4 border-t border-rule pt-4 text-sm text-muted">
          {t("noEvidenceForClaim")}
        </p>
      )}

      {claim.independent_origins > 0 && claim.evidence.length > claim.independent_origins ? (
        <p className="mt-3 text-xs text-muted">
          {claim.evidence.length} items trace back to{" "}
          {claim.independent_origins} independent{" "}
          {claim.independent_origins === 1 ? "source" : "sources"}. Republished
          copies are counted once.
        </p>
      ) : null}
    </div>
  );
}

function EvidenceGroup({
  title,
  items,
  tone,
  locale,
}: {
  title: string;
  items: Evidence[];
  tone: "support" | "contradict";
  locale: Locale;
}) {
  const Icon = tone === "support" ? ThumbsUp : ThumbsDown;
  return (
    <div>
      <h4 className="flex items-center gap-2 text-sm font-medium">
        <Icon
          className={cn(
            "h-3.5 w-3.5",
            tone === "support"
              ? "text-emerald-600 dark:text-emerald-400"
              : "text-rose-600 dark:text-rose-400",
          )}
          aria-hidden="true"
        />
        {title}
      </h4>
      <ul className="mt-2.5 space-y-3">
        {items.map((item, index) => (
          <li key={index}>
            <EvidenceItem evidence={item} locale={locale} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function EvidenceItem({ evidence, locale }: { evidence: Evidence; locale: Locale }) {
  const { t } = useLocale();
  const host = hostFromUrl(evidence.document_url) ?? evidence.source_domain;

  return (
    <div className="border-l-2 border-rule pl-4">
      <blockquote className="text-sm leading-relaxed" dir="auto">
        {evidence.evidence_text}
      </blockquote>
      <div className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-muted">
        <span className="font-medium">
          {relationshipCopy(evidence.relationship, locale)}
        </span>
        {host ? (
          <>
            <span aria-hidden="true">·</span>
            <span>{evidence.source_name ?? host}</span>
          </>
        ) : null}
        {evidence.published_at ? (
          <>
            <span aria-hidden="true">·</span>
            <time dateTime={evidence.published_at}>
              {formatDate(evidence.published_at)}
            </time>
          </>
        ) : null}
        {evidence.document_url ? (
          <>
            <span aria-hidden="true">·</span>
            <a
              href={evidence.document_url}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="inline-flex items-center gap-1 underline"
            >
              {t("sourceLink")}
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </a>
          </>
        ) : null}
      </div>
    </div>
  );
}

function EvidenceTally({
  tone,
  count,
  label,
}: {
  tone: "support" | "contradict";
  count: number;
  label: string;
}) {
  const Icon = tone === "support" ? ThumbsUp : ThumbsDown;
  return (
    <div className="rounded-lg border border-rule bg-surface p-5">
      <div className="flex items-center gap-2 text-sm text-muted">
        <Icon className="h-4 w-4" aria-hidden="true" />
        {label}
      </div>
      <p className="mt-2 font-serif text-3xl font-semibold tabular-nums">
        {count}
      </p>
    </div>
  );
}

function NoEvidencePanel() {
  const { t } = useLocale();
  return (
    <div className="mt-5 rounded-lg border border-rule bg-surface p-5">
      <p className="text-sm leading-relaxed">
        {t("noEvidenceFound")}
      </p>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        {t("noEvidenceExplain")}
      </p>
    </div>
  );
}

function LimitationsPanel({ reasons }: { reasons: string[] }) {
  const { locale, t } = useLocale();
  return (
    <section
      aria-labelledby="limitations-heading"
      className="rounded-lg border border-amber-300 bg-amber-50 p-5 dark:border-amber-900 dark:bg-amber-950/30"
    >
      <h2 id="limitations-heading" className="text-sm font-semibold">
        {t("limitationsHeading")}
      </h2>
      <ul className="mt-2.5 space-y-1.5 text-sm leading-relaxed opacity-90">
        {reasons.map((reason) => (
          <li key={reason}>{degradationCopy(reason, locale)}</li>
        ))}
      </ul>
    </section>
  );
}

function OriginalSubmission({ report }: { report: VerificationReport }) {
  const { t } = useLocale();
  const { submission } = report;
  return (
    <section aria-labelledby="submission-heading">
      <SectionHeading
        id="submission-heading"
        title={t("whatWasSubmitted")}
      />
      <div className="mt-5 rounded-lg border border-rule bg-surface p-5">
        {submission.title ? (
          <h3 className="font-medium">{submission.title}</h3>
        ) : null}
        {submission.text ? (
          <p
            className="mt-2 whitespace-pre-wrap text-sm leading-relaxed"
            lang={submission.detected_language ?? undefined}
            dir="auto"
          >
            {submission.text}
          </p>
        ) : null}
        {submission.submitted_url ? (
          <div className="scroll-x mt-2">
            <a
              href={submission.submitted_url}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="inline-flex items-center gap-1 break-all text-sm underline"
            >
              {submission.submitted_url}
              <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
            </a>
          </div>
        ) : null}
        {submission.caption ? (
          <div className="mt-3 border-t border-rule pt-3">
            <p className="text-xs font-medium text-muted">
              {t("captionSuppliedWith")}
            </p>
            <p className="mt-1 text-sm leading-relaxed" dir="auto">
              {submission.caption}
            </p>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function MediaAnalysisSection({ analyses }: { analyses: MediaAnalysis[] }) {
  const { locale, t } = useLocale();

  return (
    <section aria-labelledby="media-heading">
      <SectionHeading
        id="media-heading"
        title={locale === "bn" ? "ফাইল বিশ্লেষণ" : "File analysis"}
        description={
          locale === "bn"
            ? "ফাইলটি নিজে কী বলছে, আর দাবিটি সত্য কি না — দুটি আলাদা প্রশ্ন।"
            : "What the file itself shows, assessed separately from whether the claim is true."
        }
      />
      <div className="mt-5 space-y-4">
        {analyses.map((analysis, index) => {
          const meta = (analysis as unknown as {
            metadata_findings?: Record<string, unknown> | null;
          }).metadata_findings;
          const assessment = String(meta?.ai_generation_assessment ?? "undetermined");
          const generator = meta?.generator ? String(meta.generator) : null;

          return (
            <div key={index} className="rounded-lg border border-rule bg-surface p-5">
              {/* The question everyone asks first, answered honestly. */}
              <AiGenerationPanel
                assessment={assessment}
                generator={generator}
                locale={locale}
              />

              <div className="mt-5 grid gap-5 border-t border-rule pt-5 sm:grid-cols-2">
                <div>
                  <h3 className="text-sm font-semibold">
                    {locale === "bn" ? "ফাইল থেকে যা জানা গেল" : "What the file shows"}
                  </h3>
                  {analysis.manipulation_signals.length > 0 ? (
                    <ul className="mt-2.5 space-y-3">
                      {analysis.manipulation_signals.map((signal, i) => (
                        <li key={i} className="text-sm">
                          <p>{String(signal.description ?? signal.type ?? "")}</p>
                          {signal.caveat ? (
                            // The caveat is the point: a signal without its
                            // limits is how a hint becomes a false conclusion.
                            <p className="mt-1 text-xs leading-relaxed text-muted">
                              {String(signal.caveat)}
                            </p>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-2 text-sm text-muted">
                      {locale === "bn"
                        ? "ফাইলটি থেকে উল্লেখযোগ্য কোনো তথ্য পাওয়া যায়নি।"
                        : "No readable metadata was found in this file."}
                    </p>
                  )}
                </div>

                <div>
                  <h3 className="text-sm font-semibold">
                    {locale === "bn" ? "ছবির ভেতরের লেখা" : "Text in the image"}
                  </h3>
                  {analysis.ocr_status === "UNAVAILABLE" ? (
                    // Our gap, never presented as a finding about their file.
                    <p className="mt-2 text-sm text-muted">
                      {locale === "bn"
                        ? `ছবির লেখা পড়া যায়নি (${analysis.ocr_unavailable_reason ?? "OCR চালু নেই"})। এর মানে ছবিতে কোনো লেখা নেই, তা নয়।`
                        : `We could not read text from this image (${analysis.ocr_unavailable_reason ?? "no OCR engine available"}). This does not mean the image contains no text.`}
                    </p>
                  ) : analysis.ocr_text ? (
                    <blockquote
                      className="mt-2 border-l-2 border-rule pl-3 text-sm leading-relaxed"
                      dir="auto"
                    >
                      {analysis.ocr_text.slice(0, 400)}
                    </blockquote>
                  ) : (
                    <p className="mt-2 text-sm text-muted">
                      {locale === "bn"
                        ? "ছবিতে পড়ার মতো কোনো লেখা পাওয়া যায়নি।"
                        : "No readable text was found in this image."}
                    </p>
                  )}
                </div>
              </div>

              <div className="mt-5 border-t border-rule pt-5">
                <h3 className="text-sm font-semibold">
                  {locale === "bn" ? "এই ছবি আগে কোথাও ছিল কি না" : "Where this file came from"}
                </h3>
                {analysis.predates_claimed_event ? (
                  <p className="mt-2 text-sm">
                    {locale === "bn"
                      ? "এই ফাইলটি দাবি করা ঘটনার আগের বলে মনে হচ্ছে।"
                      : "This file appears to predate the event it is said to show."}
                  </p>
                ) : analysis.corpus_matches.length > 0 ? (
                  <p className="mt-2 text-sm">
                    {locale === "bn"
                      ? `আমাদের সংগ্রহে ${analysis.corpus_matches.length}টি মিল পাওয়া গেছে।`
                      : `Found ${analysis.corpus_matches.length} similar ${analysis.corpus_matches.length === 1 ? "item" : "items"} in our indexed sources.`}
                  </p>
                ) : (
                  <p className="mt-2 text-sm text-muted">
                    {locale === "bn"
                      ? "আমাদের সংগ্রহে এই ছবির কোনো কপি পাওয়া যায়নি। আমরা ছবি দিয়ে পুরো ইন্টারনেট খুঁজতে পারি না, তাই ছবিটি কোথা থেকে এসেছে তা এতে প্রমাণ হয় না।"
                      : "We found no matching copy in our indexed sources. We cannot search the wider web by image, so this does not establish where the file originated."}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

/**
 * The AI-generation question, answered honestly.
 *
 * We deliberately do not output a yes/no. No reliable general detector exists,
 * and a confident wrong answer causes real harm in both directions -- calling a
 * genuine photograph synthetic, or clearing a fabrication. So we report the
 * provenance evidence we actually have, and say plainly when we have none.
 */
function AiGenerationPanel({
  assessment,
  generator,
  locale,
}: {
  assessment: string;
  generator: string | null;
  locale: Locale;
}) {
  if (assessment === "declared_generator" && generator) {
    return (
      <div className="rounded-md border border-amber-300 bg-amber-50 p-4 dark:border-amber-900 dark:bg-amber-950/30">
        <p className="text-sm font-semibold">
          {locale === "bn"
            ? `ফাইলের তথ্যে ${generator}-এর নাম রয়েছে`
            : `The file's metadata names ${generator}`}
        </p>
        <p className="mt-1.5 text-sm leading-relaxed opacity-90">
          {locale === "bn"
            ? "এটি শক্ত ইঙ্গিত যে ছবিটি এআই দিয়ে তৈরি বা সম্পাদিত। তবে মেটাডেটা বদলানো যায়, তাই এটি চূড়ান্ত প্রমাণ নয়।"
            : "This is strong evidence the image was produced or processed by that tool. Metadata can be edited, so it is not proof."}
        </p>
      </div>
    );
  }

  if (assessment === "provenance_present") {
    return (
      <div className="rounded-md border border-rule p-4">
        <p className="text-sm font-semibold">
          {locale === "bn"
            ? "ফাইলটিতে Content Credentials (C2PA) তথ্য আছে"
            : "This file carries Content Credentials (C2PA)"}
        </p>
        <p className="mt-1.5 text-sm leading-relaxed text-muted">
          {locale === "bn"
            ? "ক্যামেরা ও এআই — দুই ধরনের সরঞ্জামই এই তথ্য যুক্ত করে। আমরা এর স্বাক্ষর যাচাই করিনি।"
            : "Both cameras and AI generators attach these. We detected the manifest but did not validate its signature."}
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-rule p-4">
      <p className="text-sm font-semibold">
        {locale === "bn"
          ? "ছবিটি এআই দিয়ে তৈরি কি না, আমরা বলতে পারছি না"
          : "We cannot tell whether this image is AI-generated"}
      </p>
      <p className="mt-1.5 text-sm leading-relaxed text-muted">
        {locale === "bn"
          ? "এআই-তৈরি ছবি নির্ভরযোগ্যভাবে শনাক্ত করার কোনো পদ্ধতি এখনো নেই — প্রচলিত টুলগুলো প্রায়ই ভুল করে, বিশেষ করে ছবি একবার শেয়ার বা সংকুচিত হলে। ভুল উত্তর দেওয়ার চেয়ে আমরা বরং জানাই যে আমরা নিশ্চিত নই, এবং ফাইল থেকে যা যা পেয়েছি তা নিচে দেখাই।"
          : "There is no reliable way to detect AI-generated images. Published tools are frequently wrong, especially once an image has been shared, resized, or recompressed. Rather than give you an answer we cannot stand behind, we report what the file itself reveals below."}
      </p>
    </div>
  );
}

function MethodologySection({ report }: { report: VerificationReport }) {
  const { t } = useLocale();
  return (
    <section aria-labelledby="method-heading">
      <SectionHeading id="method-heading" title={t("howChecked")} />
      <div className="mt-5 space-y-4 text-sm leading-relaxed text-muted">
        <p>
          {t("methodBody")}
        </p>
        <p>
          {t("methodDedup")}
        </p>
        <dl className="grid gap-x-6 gap-y-2 border-t border-rule pt-4 sm:grid-cols-2">
          <div className="flex justify-between gap-4">
            <dt>{t("checkedOn")}</dt>
            <dd className="tabular-nums">{formatDate(report.created_at)}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt>{t("scoringVersion")}</dt>
            <dd className="tabular-nums">{report.scoring_version}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt>{t("pipelineVersion")}</dt>
            <dd className="tabular-nums">{report.pipeline_version}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt>{t("retrievalVersion")}</dt>
            <dd className="tabular-nums">{report.retrieval_version}</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
