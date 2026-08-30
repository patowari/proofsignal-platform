/**
 * API client.
 *
 * Every response is validated against a Zod schema before it reaches a
 * component. A shape mismatch becomes a typed error we can render, rather than
 * an `undefined` crash somewhere deep in the tree.
 */

import { z } from "zod";
import {
  ApiErrorSchema,
  RecentListSchema,
  ReadinessSchema,
  SubmissionAcceptedSchema,
  VerificationReportSchema,
  VerificationStatusResponseSchema,
  type RecentList,
  type Readiness,
  type SubmissionAccepted,
  type VerificationReport,
  type VerificationStatusResponse,
} from "./schemas";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8123";

/** An error carrying the backend's own code, so the UI can respond specifically. */
export class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
    public readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** Rate limiting is worth distinguishing: the user should wait, not retry now. */
  get isRateLimited(): boolean {
    return this.status === 429;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }
}

/** A response that did not match its schema. Surfaced, never silently coerced. */
export class SchemaError extends Error {
  constructor(
    message: string,
    public readonly issues: unknown,
  ) {
    super(message);
    this.name = "SchemaError";
  }
}

async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch (cause) {
    throw new ApiError(
      "NETWORK_ERROR",
      "Could not reach the verification service. It may be offline.",
      0,
      { cause: String(cause) },
    );
  }

  const raw: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const parsed = ApiErrorSchema.safeParse(raw);
    if (parsed.success) {
      throw new ApiError(
        parsed.data.error.code,
        parsed.data.error.message,
        response.status,
        parsed.data.error.details,
      );
    }
    throw new ApiError(
      "UNKNOWN_ERROR",
      `The request failed (HTTP ${response.status}).`,
      response.status,
    );
  }

  const result = schema.safeParse(raw);
  if (!result.success) {
    throw new SchemaError(
      "The verification service returned data in an unexpected format.",
      result.error.issues,
    );
  }
  return result.data;
}

// ---- Submissions ----------------------------------------------------------

export function submitText(
  text: string,
  title?: string,
): Promise<SubmissionAccepted> {
  return request("/api/submissions/text", SubmissionAcceptedSchema, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, title: title || undefined }),
  });
}

export function submitUrl(
  url: string,
  note?: string,
): Promise<SubmissionAccepted> {
  return request("/api/submissions/url", SubmissionAcceptedSchema, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, note: note || undefined }),
  });
}

export function submitImage(
  file: File,
  caption?: string,
  isScreenshot = false,
): Promise<SubmissionAccepted> {
  const form = new FormData();
  form.append("file", file);
  if (caption) form.append("caption", caption);
  form.append("is_screenshot", String(isScreenshot));

  return request("/api/submissions/image", SubmissionAcceptedSchema, {
    method: "POST",
    body: form,
  });
}

export function submitVideo(
  file: File,
  caption?: string,
): Promise<SubmissionAccepted> {
  const form = new FormData();
  form.append("file", file);
  if (caption) form.append("caption", caption);

  return request("/api/submissions/video", SubmissionAcceptedSchema, {
    method: "POST",
    body: form,
  });
}

// ---- Reading --------------------------------------------------------------

export function getStatus(
  publicId: string,
): Promise<VerificationStatusResponse> {
  return request(
    `/api/verifications/${encodeURIComponent(publicId)}/status`,
    VerificationStatusResponseSchema,
    { cache: "no-store" },
  );
}

export function getVerification(
  publicId: string,
): Promise<VerificationReport> {
  return request(
    `/api/verifications/${encodeURIComponent(publicId)}`,
    VerificationReportSchema,
    { cache: "no-store" },
  );
}

export function getRecent(limit = 20): Promise<RecentList> {
  return request(`/api/recent?limit=${limit}`, RecentListSchema, {
    cache: "no-store",
  });
}

export function getReadiness(): Promise<Readiness> {
  return request("/api/ready", ReadinessSchema, { cache: "no-store" });
}
