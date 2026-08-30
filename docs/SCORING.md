# Scoring

`SCORING_VERSION = "1.0.0"`

Implemented in `backend/app/verification/scoring.py`. The function is **pure**:
signals in, verdict out. No I/O, no model calls, no clock reads (the evaluation
time is passed in). Same inputs always produce the same verdict, which is what
makes the result reproducible and testable.

> **This formula is not scientifically calibrated.** It is explainable and
> testable, and it is a starting point. The weights are engineering judgement,
> chosen to behave sensibly on the fixture corpus. They will need calibration
> against labeled data. We do not claim accuracy we have not measured.

## Why the LLM is excluded

If a model picked the verdict, the verdict would be unreproducible, unauditable,
and steerable by any webpage we retrieved. Instead the model produces *labeled
evidence* — this passage supports, this one contradicts — and arithmetic we can
inspect turns those labels into a conclusion.

## Stage 1 — evidence weight

Each evidence item `e` gets a weight from four factors:

```
weight(e) = relevance(e) * source_factor(e) * temporal_factor(e) * directness(e)
```

- `relevance` ∈ [0,1] — retrieval/reranker score for this passage against this claim.
- `source_factor` ∈ [0.5, 1.3] — from source type. Not a truth oracle: it modulates
  how much a passage counts, and is capped so no single source type can dominate.

  | Source type | Factor |
  |---|---|
  | `OFFICIAL_GOVERNMENT`, `PRIMARY_DOCUMENT` | 1.30 |
  | `SCIENTIFIC_SOURCE` | 1.25 |
  | `OFFICIAL_COMPANY` | 1.20 |
  | `NEWS_AGENCY` | 1.15 |
  | `NEWS_ORGANIZATION` | 1.00 |
  | `SPECIALIST_PUBLICATION` | 1.00 |
  | `BLOG` | 0.70 |
  | `SOCIAL_MEDIA` | 0.60 |
  | `USER_PROVIDED` | 0.55 |
  | `UNKNOWN` | 0.50 |

  A `PRIMARY_SOURCE_MATCH` bonus (+0.15, applied before the cap) is added when the
  source is the natural primary authority for the claim type — a seismological
  agency for an earthquake magnitude, a company newsroom for its own announcement.

- `temporal_factor` ∈ [0.4, 1.0] — 1.0 when the document's publication window
  covers the claimed event date; decaying when the document predates the claimed
  event (it cannot report a later event) or long postdates it without referencing it.
- `directness` ∈ [0.5, 1.0] — whether the passage addresses the claim's specific
  assertion or merely its topic.

## Stage 2 — independence clustering

Evidence is grouped into origin clusters (canonical URL, content hash, SimHash,
embedding similarity, syndication markers — see `docs/RETRIEVAL.md`). Within a
cluster of size `n`, only the strongest item counts at full weight; the rest
contribute with heavy damping:

```
cluster_weight = max(w_i) + 0.15 * sum(other w_i)
```

This is the rule that stops fifty syndicated reprints of one wire story from
reading as fifty confirmations. `independent_origins` = number of distinct
clusters, and it gates the strongest verdicts.

## Stage 3 — claim scores

```
support_score       = sum(cluster_weight for SUPPORTS clusters)
contradiction_score = sum(cluster_weight for CONTRADICTS clusters)
coverage_score      = min(1.0, independent_origins / TARGET_ORIGINS)   # TARGET_ORIGINS = 3
```

`NEUTRAL` and `INSUFFICIENT` items add no support or contradiction; they still
count toward "sources checked" and are shown in the report.

### Context penalties

Applied to the *supported* reading of a claim, because these are the cases where
every individual fact checks out but the claim as framed is still wrong:

| Penalty | Value | Trigger |
|---|---|---|
| `NUMERIC_MISMATCH` | 0.45 | A claim number contradicts a well-supported evidence number beyond tolerance |
| `DATE_MISMATCH` | 0.35 | Claimed event date conflicts with established date |
| `LOCATION_MISMATCH` | 0.35 | Claimed location conflicts with established location |
| `ENTITY_MISMATCH` | 0.30 | Central actor differs from the one in evidence |
| `STALE_MEDIA` | 0.40 | Media demonstrably predates the claimed event |
| `EXAGGERATION` | 0.25 | Evidence supports a materially weaker version of the claim |

Numeric tolerance: exact for counts of people and money; 5% relative for
measurements; magnitude compared at 0.1 absolute. `$50bn` vs `$5bn` is an
order-of-magnitude mismatch, not a rounding difference — a hard contradiction.

## Stage 4 — claim verdict

Let `S = support_score`, `C = contradiction_score`, `P = max(applied penalties)`,
`O = independent_origins`.

```
net = (S - C) / max(S + C, 1e-9)      # ∈ [-1, 1]
```

Decision order (first match wins):

1. `S + C < MIN_EVIDENCE (0.8)` or `O == 0`      -> **UNVERIFIED**
2. Claim type is `OPINION`/prediction              -> **OPINION**
3. Source context flagged satirical                -> **SATIRE**
4. `net >= 0.6` and `P >= 0.35`                    -> **MISLEADING**
5. `net >= 0.6` and `0 < P < 0.35`                 -> **PARTLY_TRUE**
6. `net >= 0.75` and `O >= 3` and `S >= 2.0`       -> **VERIFIED**
7. `net >= 0.5`                                    -> **LIKELY_TRUE**
8. `net <= -0.75` and `O >= 2` and `C >= 1.5`      -> **FALSE**
9. `net <= -0.4`                                   -> **LIKELY_FALSE**
10. `-0.4 < net < 0.5` with both sides present     -> **PARTLY_TRUE**
11. otherwise                                      -> **UNVERIFIED**

Rule 4 is the heart of misinformation detection: strong support **plus** a large
context penalty is exactly the authentic-photo-wrong-caption case, and it must
not resolve to `VERIFIED`.

## Stage 5 — overall verdict

Claims carry `importance ∈ [0,1]`. The overall verdict is driven by the most
important claims rather than by counting minor ones:

1. If any claim with `importance >= 0.7` is `FALSE` -> overall **FALSE**.
2. Else if any such claim is `MISLEADING` -> overall **MISLEADING**.
3. Else if any is `LIKELY_FALSE` -> overall **LIKELY_FALSE**.
4. Else if any is `PARTLY_TRUE`, or verdicts are mixed -> overall **PARTLY_TRUE**.
5. Else if all important claims are `VERIFIED` -> overall **VERIFIED**.
6. Else if all are `VERIFIED`/`LIKELY_TRUE` -> overall **LIKELY_TRUE**.
7. Else if a majority by importance are `UNVERIFIED` -> overall **UNVERIFIED**.
8. `SATIRE`/`OPINION` propagate when they cover the dominant claim.

A single false load-bearing claim makes the whole item false, even alongside
several true incidental ones — this is how real misinformation is built.

## Stage 6 — confidence band

Confidence is about *how much we know*, not how extreme the verdict is:

```
confidence_raw = 0.40 * coverage_score
               + 0.25 * min(1.0, total_weight / 4.0)
               + 0.20 * agreement          # 1 - (minority side / total)
               + 0.15 * best_source_factor_normalized
```

```
>= 0.70 -> HIGH        0.40..0.70 -> MEDIUM        < 0.40 -> LOW
```

Hard caps: a degraded run (missing provider, failed retrieval) is capped at
`MEDIUM`. `UNVERIFIED` from absent evidence is always `LOW`. The numeric value is
never shown to users — the UI displays only the band.

## What is stored

Every verification persists the full breakdown: each evidence weight and its four
factors, cluster assignments, per-claim `S`/`C`/`coverage`/`net`, penalties with
triggers, the matched decision rule number, and the confidence components. A
result must be explainable after the fact, and a scoring change must be diffable
against stored history.

## Changing this file

Any change to weights, thresholds, or rules requires: a `SCORING_VERSION` bump,
updated tests in `tests/test_scoring.py`, and a note in `docs/ROADMAP.md`.
Existing verifications keep their original version — we never retroactively
restate a past verdict under new rules.
