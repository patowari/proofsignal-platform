/**
 * Verdict presentation.
 *
 * One source of truth for how a verdict looks and reads, so the label,
 * explanation, and styling cannot drift apart across components.
 *
 * Accessibility rule: a verdict is never communicated by color alone. Every
 * presentation pairs color with an icon and explicit text.
 */

import type { ConfidenceBand, Verdict } from "./api/schemas";

export interface VerdictPresentation {
  /** Human label, e.g. "Likely true". */
  label: string;
  /** One line on what this verdict means, shown under the label. */
  meaning: string;
  /** Lucide icon name, paired with color so meaning never depends on hue. */
  icon: "check-circle" | "circle-check-big" | "circle-slash" | "triangle-alert" | "circle-help" | "x-circle" | "smile" | "message-circle";
  /** Tailwind classes for the verdict banner. */
  banner: string;
  /** Tailwind classes for a compact badge. */
  badge: string;
  /** Accent used for rules and markers. */
  accent: string;
}

export const VERDICT_PRESENTATION: Record<Verdict, VerdictPresentation> = {
  VERIFIED: {
    label: "Verified",
    meaning:
      "Strong, independent evidence establishes this claim.",
    icon: "circle-check-big",
    banner:
      "bg-emerald-50 border-emerald-200 text-emerald-950 dark:bg-emerald-950/40 dark:border-emerald-900 dark:text-emerald-50",
    badge:
      "bg-emerald-100 text-emerald-900 border-emerald-300 dark:bg-emerald-950 dark:text-emerald-100 dark:border-emerald-800",
    accent: "text-emerald-700 dark:text-emerald-400",
  },
  LIKELY_TRUE: {
    label: "Likely true",
    meaning:
      "The evidence supports this claim, but sourcing is thin or has minor gaps.",
    icon: "check-circle",
    banner:
      "bg-teal-50 border-teal-200 text-teal-950 dark:bg-teal-950/40 dark:border-teal-900 dark:text-teal-50",
    badge:
      "bg-teal-100 text-teal-900 border-teal-300 dark:bg-teal-950 dark:text-teal-100 dark:border-teal-800",
    accent: "text-teal-700 dark:text-teal-400",
  },
  PARTLY_TRUE: {
    label: "Partly true",
    meaning:
      "The core of this claim holds up, but specific details are wrong or overstated.",
    icon: "circle-slash",
    banner:
      "bg-amber-50 border-amber-200 text-amber-950 dark:bg-amber-950/40 dark:border-amber-900 dark:text-amber-50",
    badge:
      "bg-amber-100 text-amber-900 border-amber-300 dark:bg-amber-950 dark:text-amber-100 dark:border-amber-800",
    accent: "text-amber-700 dark:text-amber-400",
  },
  MISLEADING: {
    label: "Misleading",
    meaning:
      "The underlying facts are real, but the framing, timing, or context creates a false impression.",
    icon: "triangle-alert",
    banner:
      "bg-orange-50 border-orange-200 text-orange-950 dark:bg-orange-950/40 dark:border-orange-900 dark:text-orange-50",
    badge:
      "bg-orange-100 text-orange-900 border-orange-300 dark:bg-orange-950 dark:text-orange-100 dark:border-orange-800",
    accent: "text-orange-700 dark:text-orange-400",
  },
  UNVERIFIED: {
    label: "Unverified",
    // The single most important piece of copy in the product.
    meaning:
      "We could not find enough evidence to reach a conclusion. This does not mean the claim is false.",
    icon: "circle-help",
    banner:
      "bg-slate-50 border-slate-300 text-slate-900 dark:bg-slate-900/60 dark:border-slate-700 dark:text-slate-100",
    badge:
      "bg-slate-100 text-slate-800 border-slate-300 dark:bg-slate-900 dark:text-slate-200 dark:border-slate-700",
    accent: "text-slate-600 dark:text-slate-400",
  },
  LIKELY_FALSE: {
    label: "Likely false",
    meaning:
      "Meaningful evidence contradicts this claim, though not conclusively.",
    icon: "x-circle",
    banner:
      "bg-rose-50 border-rose-200 text-rose-950 dark:bg-rose-950/40 dark:border-rose-900 dark:text-rose-50",
    badge:
      "bg-rose-100 text-rose-900 border-rose-300 dark:bg-rose-950 dark:text-rose-100 dark:border-rose-800",
    accent: "text-rose-700 dark:text-rose-400",
  },
  FALSE: {
    label: "False",
    meaning:
      "Strong, independent evidence directly contradicts this claim.",
    icon: "x-circle",
    banner:
      "bg-red-50 border-red-300 text-red-950 dark:bg-red-950/50 dark:border-red-900 dark:text-red-50",
    badge:
      "bg-red-100 text-red-900 border-red-300 dark:bg-red-950 dark:text-red-100 dark:border-red-800",
    accent: "text-red-700 dark:text-red-400",
  },
  SATIRE: {
    label: "Satire",
    meaning:
      "This originates from satire or parody. It is not a sincere factual assertion.",
    icon: "smile",
    banner:
      "bg-violet-50 border-violet-200 text-violet-950 dark:bg-violet-950/40 dark:border-violet-900 dark:text-violet-50",
    badge:
      "bg-violet-100 text-violet-900 border-violet-300 dark:bg-violet-950 dark:text-violet-100 dark:border-violet-800",
    accent: "text-violet-700 dark:text-violet-400",
  },
  OPINION: {
    label: "Opinion",
    meaning:
      "This is a value judgement or prediction, not a factual claim that evidence can settle.",
    icon: "message-circle",
    banner:
      "bg-sky-50 border-sky-200 text-sky-950 dark:bg-sky-950/40 dark:border-sky-900 dark:text-sky-50",
    badge:
      "bg-sky-100 text-sky-900 border-sky-300 dark:bg-sky-950 dark:text-sky-100 dark:border-sky-800",
    accent: "text-sky-700 dark:text-sky-400",
  },
};

export function verdictPresentation(
  verdict: Verdict | null | undefined,
): VerdictPresentation {
  // An absent verdict reads as UNVERIFIED, never as a negative finding.
  return VERDICT_PRESENTATION[verdict ?? "UNVERIFIED"];
}

export const CONFIDENCE_LABEL: Record<ConfidenceBand, string> = {
  LOW: "Low confidence",
  MEDIUM: "Medium confidence",
  HIGH: "High confidence",
};

export const CONFIDENCE_MEANING: Record<ConfidenceBand, string> = {
  LOW: "Based on limited evidence. Treat this result with caution.",
  MEDIUM: "Based on a reasonable body of evidence, with some gaps.",
  HIGH: "Based on substantial, independent, directly relevant evidence.",
};

/** Filled segments in the confidence meter. Never rendered as a percentage. */
export const CONFIDENCE_STEPS: Record<ConfidenceBand, number> = {
  LOW: 1,
  MEDIUM: 2,
  HIGH: 3,
};

const RELATIONSHIP_LABELS: Record<string, string> = {
  SUPPORTS: "Supports",
  CONTRADICTS: "Contradicts",
  NEUTRAL: "Related, but does not settle this",
  INSUFFICIENT: "Not enough to judge",
};

export function relationshipLabel(relationship: string): string {
  return RELATIONSHIP_LABELS[relationship] ?? relationship;
}

const ORIGIN_LABELS: Record<string, string> = {
  USER_TEXT: "Submitted text",
  USER_CAPTION: "Caption supplied with the media",
  ARTICLE_TEXT: "Article body",
  SOCIAL_POST_TEXT: "Social post",
  VIDEO_TRANSCRIPT: "Video transcript",
  ON_SCREEN_TEXT: "On-screen text",
  OCR_TEXT: "Text read from the image",
};

/**
 * Where a claim came from.
 *
 * Shown because origin changes what a verdict means: an authentic video can
 * carry a false caption, and the report must keep those apart.
 */
export function originLabel(origin: string): string {
  return ORIGIN_LABELS[origin] ?? origin;
}

const CLAIM_TYPE_LABELS: Record<string, string> = {
  EVENT: "Event",
  STATISTIC: "Statistic",
  QUOTE: "Quote",
  ATTRIBUTION: "Attribution",
  CAUSAL: "Cause and effect",
  EXISTENCE: "Existence",
  IDENTITY: "Identity",
  LOCATION: "Location",
  TEMPORAL: "Timing",
  PREDICTION: "Prediction",
  OPINION: "Opinion",
  OTHER: "Claim",
};

export function claimTypeLabel(claimType: string): string {
  return CLAIM_TYPE_LABELS[claimType] ?? claimType;
}

/**
 * Turn a machine degradation reason into something a reader can act on.
 *
 * These appear in reports, so they must explain a real limitation rather than
 * leaking an internal identifier.
 */
export function degradationLabel(reason: string): string {
  const known: Record<string, string> = {
    evidence_retrieval_not_implemented:
      "Evidence retrieval is not yet available, so no sources were searched.",
    query_generation_not_implemented:
      "Search query generation is not yet available.",
    url_extraction_not_implemented:
      "We could not read the contents of the submitted link.",
    media_analysis_not_implemented:
      "Media analysis is not yet available, so the file was stored but not examined.",
    ollama_unavailable:
      "The local language model was unavailable, so claim extraction used rules only.",
    ocr_unavailable:
      "No OCR engine is installed, so text inside images could not be read.",
  };
  if (known[reason]) return known[reason];

  // Fall back to a readable form rather than showing a raw enum.
  return reason.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
