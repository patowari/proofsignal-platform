/**
 * API contract.
 *
 * Every response is parsed through these schemas before use, so a backend shape
 * change surfaces as a clear error state rather than a crash on `undefined`
 * three components deep.
 *
 * These mirror `backend/app/core/enums.py`. Changing one without the other is a
 * breaking change.
 */

import { z } from "zod";

// ---------------------------------------------------------------------------
// Enums - one source of truth, never restated per file
// ---------------------------------------------------------------------------

export const VerdictSchema = z.enum([
  "VERIFIED",
  "LIKELY_TRUE",
  "PARTLY_TRUE",
  "MISLEADING",
  "UNVERIFIED",
  "LIKELY_FALSE",
  "FALSE",
  "SATIRE",
  "OPINION",
]);
export type Verdict = z.infer<typeof VerdictSchema>;

export const ConfidenceBandSchema = z.enum(["LOW", "MEDIUM", "HIGH"]);
export type ConfidenceBand = z.infer<typeof ConfidenceBandSchema>;

export const VerificationStatusSchema = z.enum([
  "QUEUED",
  "RUNNING",
  "COMPLETED",
  "FAILED",
]);
export type VerificationStatus = z.infer<typeof VerificationStatusSchema>;

export const PipelineStageSchema = z.enum([
  "QUEUED",
  "NORMALIZING",
  "EXTRACTING_CONTENT",
  "DETECTING_LANGUAGE",
  "EXTRACTING_CLAIMS",
  "GENERATING_QUERIES",
  "RETRIEVING_EVIDENCE",
  "FETCHING_DOCUMENTS",
  "EXTRACTING_EVIDENCE",
  "CLASSIFYING_EVIDENCE",
  "ANALYZING_MEDIA",
  "SCORING",
  "GENERATING_REPORT",
  "COMPLETED",
  "FAILED",
]);
export type PipelineStage = z.infer<typeof PipelineStageSchema>;

export const StageStatusSchema = z.enum([
  "PENDING",
  "RUNNING",
  "COMPLETED",
  "SKIPPED",
  "DEGRADED",
  "FAILED",
]);
export type StageStatus = z.infer<typeof StageStatusSchema>;

export const SubmissionTypeSchema = z.enum([
  "TEXT",
  "ARTICLE_URL",
  "SOCIAL_URL",
  "IMAGE",
  "SCREENSHOT",
  "IMAGE_WITH_CAPTION",
  "VIDEO",
  "VIDEO_WITH_CAPTION",
]);
export type SubmissionType = z.infer<typeof SubmissionTypeSchema>;

export const EvidenceRelationshipSchema = z.enum([
  "SUPPORTS",
  "CONTRADICTS",
  "NEUTRAL",
  "INSUFFICIENT",
]);
export type EvidenceRelationship = z.infer<typeof EvidenceRelationshipSchema>;

export const ClaimTypeSchema = z.enum([
  "EVENT",
  "STATISTIC",
  "QUOTE",
  "ATTRIBUTION",
  "CAUSAL",
  "EXISTENCE",
  "IDENTITY",
  "LOCATION",
  "TEMPORAL",
  "PREDICTION",
  "OPINION",
  "OTHER",
]);
export type ClaimType = z.infer<typeof ClaimTypeSchema>;

export const ClaimOriginSchema = z.enum([
  "USER_TEXT",
  "USER_CAPTION",
  "ARTICLE_TEXT",
  "SOCIAL_POST_TEXT",
  "VIDEO_TRANSCRIPT",
  "ON_SCREEN_TEXT",
  "OCR_TEXT",
]);
export type ClaimOrigin = z.infer<typeof ClaimOriginSchema>;

export const SourceTypeSchema = z.enum([
  "OFFICIAL_GOVERNMENT",
  "OFFICIAL_COMPANY",
  "PRIMARY_DOCUMENT",
  "SCIENTIFIC_SOURCE",
  "NEWS_AGENCY",
  "NEWS_ORGANIZATION",
  "SPECIALIST_PUBLICATION",
  "BLOG",
  "SOCIAL_MEDIA",
  "USER_PROVIDED",
  "UNKNOWN",
]);
export type SourceType = z.infer<typeof SourceTypeSchema>;

export const AnalysisAvailabilitySchema = z.enum([
  "COMPLETED",
  "UNAVAILABLE",
  "FAILED",
  "SKIPPED",
]);

// ---------------------------------------------------------------------------
// Responses
// ---------------------------------------------------------------------------

export const SubmissionAcceptedSchema = z.object({
  submission_public_id: z.string(),
  verification_public_id: z.string(),
  status: VerificationStatusSchema,
  poll_url: z.string(),
});
export type SubmissionAccepted = z.infer<typeof SubmissionAcceptedSchema>;

export const StageSchema = z.object({
  stage: PipelineStageSchema,
  label: z.string(),
  status: StageStatusSchema,
  sequence: z.number(),
  started_at: z.string().nullable().optional(),
  finished_at: z.string().nullable().optional(),
  duration_ms: z.number().nullable().optional(),
  error_type: z.string().nullable().optional(),
});
export type Stage = z.infer<typeof StageSchema>;

export const VerificationStatusResponseSchema = z.object({
  public_id: z.string(),
  status: VerificationStatusSchema,
  current_stage: PipelineStageSchema,
  current_stage_label: z.string(),
  stage_index: z.number(),
  stage_count: z.number(),
  stages: z.array(StageSchema),
  degraded: z.boolean().default(false),
  degradation_reasons: z.array(z.string()).default([]),
  error_code: z.string().nullable().optional(),
  error_message: z.string().nullable().optional(),
  created_at: z.string(),
  completed_at: z.string().nullable().optional(),
});
export type VerificationStatusResponse = z.infer<
  typeof VerificationStatusResponseSchema
>;

export const EvidenceSchema = z.object({
  relationship: EvidenceRelationshipSchema,
  evidence_text: z.string(),
  source_name: z.string().nullable().optional(),
  source_domain: z.string().nullable().optional(),
  source_type: SourceTypeSchema.default("UNKNOWN"),
  document_title: z.string().nullable().optional(),
  document_url: z.string().nullable().optional(),
  published_at: z.string().nullable().optional(),
  relevance_score: z.number().default(0),
  /** Shared cluster id means these are copies of one origin, not independent corroboration. */
  cluster_id: z.number().nullable().optional(),
});
export type Evidence = z.infer<typeof EvidenceSchema>;

export const ClaimSchema = z.object({
  claim_text: z.string(),
  normalized_claim: z.string().nullable().optional(),
  language: z.string().default("en"),
  claim_type: ClaimTypeSchema,
  origin: ClaimOriginSchema,
  importance: z.number(),
  sequence: z.number(),
  verdict: VerdictSchema.nullable().optional(),
  confidence_band: ConfidenceBandSchema.nullable().optional(),
  evidence: z.array(EvidenceSchema).default([]),
  supporting_count: z.number().default(0),
  contradicting_count: z.number().default(0),
  independent_origins: z.number().default(0),
});
export type Claim = z.infer<typeof ClaimSchema>;

export const MediaAnalysisSchema = z.object({
  kind: z.string(),
  manipulation_signals: z.array(z.record(z.string(), z.unknown())).default([]),
  metadata_captured_at: z.string().nullable().optional(),
  earliest_known_appearance: z.string().nullable().optional(),
  predates_claimed_event: z.boolean().nullable().optional(),
  ocr_status: AnalysisAvailabilitySchema.default("SKIPPED"),
  ocr_text: z.string().nullable().optional(),
  ocr_unavailable_reason: z.string().nullable().optional(),
  corpus_matches: z.array(z.record(z.string(), z.unknown())).default([]),
  analysis_availability: z.record(z.string(), z.unknown()).default({}),
});
export type MediaAnalysis = z.infer<typeof MediaAnalysisSchema>;

export const SubmissionSchema = z.object({
  public_id: z.string(),
  content_type: SubmissionTypeSchema,
  title: z.string().nullable().optional(),
  text: z.string().nullable().optional(),
  caption: z.string().nullable().optional(),
  submitted_url: z.string().nullable().optional(),
  detected_language: z.string().nullable().optional(),
  created_at: z.string(),
});
export type Submission = z.infer<typeof SubmissionSchema>;

export const SourceCheckedSchema = z.object({
  domain: z.string().nullable().optional(),
  name: z.string().nullable().optional(),
  source_type: SourceTypeSchema.default("UNKNOWN"),
  documents_found: z.number().default(0),
});

export const VerificationReportSchema = z.object({
  public_id: z.string(),
  status: VerificationStatusSchema,
  submission: SubmissionSchema,
  overall_verdict: VerdictSchema.nullable().optional(),
  confidence_band: ConfidenceBandSchema.nullable().optional(),
  summary: z.string().nullable().optional(),
  claims: z.array(ClaimSchema).default([]),
  media_analyses: z.array(MediaAnalysisSchema).default([]),
  sources_checked: z.array(SourceCheckedSchema).default([]),
  total_evidence: z.number().default(0),
  supporting_evidence: z.number().default(0),
  contradicting_evidence: z.number().default(0),
  independent_origins: z.number().default(0),
  unresolved_claims: z.number().default(0),
  degraded: z.boolean().default(false),
  degradation_reasons: z.array(z.string()).default([]),
  error_code: z.string().nullable().optional(),
  error_message: z.string().nullable().optional(),
  pipeline_version: z.string(),
  scoring_version: z.string(),
  retrieval_version: z.string(),
  /** Debug only. Never rendered: the UI shows the band, never a percentage. */
  confidence_score: z.number().nullable().optional(),
  score_breakdown: z.record(z.string(), z.unknown()).nullable().optional(),
  stages: z.array(StageSchema).default([]),
  created_at: z.string(),
  completed_at: z.string().nullable().optional(),
});
export type VerificationReport = z.infer<typeof VerificationReportSchema>;

export const RecentVerificationSchema = z.object({
  public_id: z.string(),
  status: VerificationStatusSchema,
  content_type: SubmissionTypeSchema,
  title: z.string().nullable().optional(),
  excerpt: z.string().nullable().optional(),
  overall_verdict: VerdictSchema.nullable().optional(),
  confidence_band: ConfidenceBandSchema.nullable().optional(),
  created_at: z.string(),
  completed_at: z.string().nullable().optional(),
});
export type RecentVerification = z.infer<typeof RecentVerificationSchema>;

export const RecentListSchema = z.object({
  items: z.array(RecentVerificationSchema),
  next_cursor: z.string().nullable().optional(),
  total: z.number().nullable().optional(),
});
export type RecentList = z.infer<typeof RecentListSchema>;

export const HealthSchema = z.object({
  status: z.string(),
  version: z.string(),
  environment: z.string(),
});

export const DependencyStatusSchema = z.object({
  name: z.string(),
  status: z.string(),
  required: z.boolean(),
  detail: z.string().nullable().optional(),
});

export const ReadinessSchema = z.object({
  status: z.string(),
  dependencies: z.array(DependencyStatusSchema),
  degraded_capabilities: z.array(z.string()).default([]),
});
export type Readiness = z.infer<typeof ReadinessSchema>;

export const ApiErrorSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.record(z.string(), z.unknown()).default({}),
  }),
});
export type ApiErrorBody = z.infer<typeof ApiErrorSchema>;
