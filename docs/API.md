# API

FastAPI, JSON, no authentication. OpenAPI is generated at `/api/openapi.json`
with interactive docs at `/api/docs`. Base path `/api`.

## Submission

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/submissions/text` | `{text, title?}` | submission accepted |
| POST | `/api/submissions/url` | `{url, note?}` | submission accepted |
| POST | `/api/submissions/image` | multipart: `file`, `caption?`, `is_screenshot?` | submission accepted |
| POST | `/api/submissions/video` | multipart: `file`, `caption?` | submission accepted |

All four validate, store, create a `Verification`, enqueue a job, and return
immediately — the request never waits on the pipeline:

```json
{
  "submission_public_id": "sub_9f3k2mQ7xR",
  "verification_public_id": "vfy_7gK2mP8dLw",
  "status": "QUEUED",
  "poll_url": "/api/verifications/vfy_7gK2mP8dLw/status"
}
```

`202 Accepted`. Uploads reject on size, MIME/signature mismatch, or media limits
before any processing.

## Reading a verification

| Method | Path | Returns |
|---|---|---|
| GET | `/api/verifications/{public_id}` | Full report |
| GET | `/api/verifications/{public_id}/status` | Live stage + progress (poll target) |
| GET | `/api/verifications/{public_id}/claims` | Claims with per-claim verdicts |
| GET | `/api/verifications/{public_id}/evidence` | Evidence, filterable by relationship |
| GET | `/api/verifications/{public_id}/timeline` | Stage history with durations |

`status` is the cheap endpoint the progress UI polls, reading real
`VerificationStage` rows:

```json
{
  "status": "RUNNING",
  "current_stage": "RETRIEVING_EVIDENCE",
  "stage_index": 6,
  "stage_count": 12,
  "stages": [
    {"name": "NORMALIZING", "status": "COMPLETED", "duration_ms": 41},
    {"name": "EXTRACTING_CLAIMS", "status": "COMPLETED", "duration_ms": 2180},
    {"name": "RETRIEVING_EVIDENCE", "status": "RUNNING", "duration_ms": null}
  ],
  "degraded": false
}
```

The full report carries the verdict, confidence band, summary, claims with their
evidence, sources checked, media analysis, degradation notes, methodology, and
version stamps. It never contains a numeric truth percentage.

## Discovery

| Method | Path | Query | Returns |
|---|---|---|---|
| GET | `/api/recent` | `limit`, `cursor`, `verdict?`, `status?` | Recent public verifications |
| GET | `/api/search` | `q`, `limit`, `cursor`, `verdict?`, `language?` | Search public verifications |
| GET | `/api/health` | — | Liveness + dependency readiness |

Listings are cursor-paginated on opaque cursors. `/api/health` reports per-
dependency status (PostgreSQL, Redis, MinIO, Ollama, embeddings, OCR, FFmpeg),
distinguishing *required* dependencies (unhealthy) from *optional* ones (degraded
but serving).

## Conventions

Identifiers are always opaque public ids; serial database ids never appear.
Timestamps are ISO-8601 UTC. Enums are stable uppercase strings shared with the
frontend's Zod schemas.

Errors use a consistent envelope:

```json
{"error": {"code": "UNSUPPORTED_MEDIA_TYPE", "message": "...", "details": {}}}
```

Meaningful codes: `400` validation, `404` unknown public id, `413` too large,
`415` unsupported type, `422` semantic validation, `429` rate limited (with
`Retry-After`), `502` upstream fetch failure, `503` required dependency down.

A processing failure returns a `FAILED` verification with a stated reason — it is
never rendered as a substantive verdict.

## Rate limits

Per client fingerprint in Redis, separate budgets per operation (video uploads
scarcest, status polling most generous), all configurable. `429` responses carry
`Retry-After` and the frontend backs off rather than hammering.
