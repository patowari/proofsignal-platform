# Roadmap

## V1 phases

| Phase | Scope | Status |
|---|---|---|
| 0 | Discovery: repo, runtimes, tooling | Done |
| 1 | Architecture docs, CLAUDE.md, rules | Done |
| 2 | Infrastructure: FastAPI, Next.js, Postgres+pgvector, Redis, MinIO, Compose, migrations, health, logging | In progress |
| 3 | Anonymous submission: text, URL, image, video; validation, storage, rate limiting, composer UI | Pending |
| 4 | Job system: verification records, stages, Redis queue, worker, status endpoint, progress UI, retries | Pending |
| 5 | Claim extraction: language detection, EN/BN, atomic claims, entities/dates/numbers, Ollama provider | Pending |
| 6 | Evidence corpus: RSS ingestion, GDELT, safe fetch, extraction, FTS, embeddings, hybrid retrieval | Pending |
| 7 | Evidence analysis: passage extraction, NLI classification, clustering, temporal and numeric analysis | Pending |
| 8 | Deterministic verdict: scoring engine, claim and overall verdicts, confidence, breakdown | Pending |
| 9 | Report UI: full verification page, evidence hierarchy, responsive, accessible | Pending |
| 10 | Image and screenshot verification | Pending |
| 11 | Video verification | Pending |
| 12 | Social link resolution | Pending |
| 13 | Hardening: security, retrieval, scoring, upload, SSRF, injection, performance, accessibility reviews | Pending |

## Known V1 limitations

These are product facts we state openly, not bugs:

- **No internet-wide search.** Retrieval covers our indexed corpus, GDELT, and
  submitted URLs. Coverage is reported and bounds confidence.
- **No reverse image search.** Image matching is limited to our own corpus,
  perceptual hashes, and embeddings. Unknown origins are reported as unknown.
- **Scoring is uncalibrated.** The formula is explainable and tested, not
  validated against labeled data. Weights are engineering judgement.
- **Cross-language support is EN + BN only**, and depends on multilingual
  embedding quality.
- **No claim-level caching across submissions** — identical claims are re-verified.
- **Polling, not push.** Progress is polled; SSE/WebSocket is deferred.
- **Local models are modest.** Ollama-class models are weaker at claim extraction
  than frontier models; the deterministic scoring layer is what keeps output
  trustworthy despite that.

## After V1

**Accuracy.** Build a labeled evaluation set and calibrate scoring weights against
it; publish measured accuracy per verdict class instead of asserting quality.
Benchmark NLI vs LLM classification per claim type on fixtures.

**Coverage.** More feeds and languages; a proper primary-source registry; a
reverse-image provider if a responsible free option exists; claim-level caching
and cross-verification claim linking.

**Product.** SSE/WebSocket progress; automatic re-verification when new evidence
appears on a previously `UNVERIFIED` claim (the revision model already supports
this); embeddable report widgets; a public API.

**Platform.** Accounts and saved history — the schema is future-compatible but no
auth code exists in V1 and none should be added speculatively. Moderation tooling
for public listings. Horizontal worker scaling and a separate media-processing
queue.

## Scoring changelog

| Version | Change |
|---|---|
| 1.0.0 | Initial formula: weighted evidence, cluster damping, context penalties, importance-weighted overall verdict, confidence bands. Uncalibrated. |
