# Verification rules

## The LLM does not decide verdicts

`app/verification/scoring.py` is deterministic: same inputs -> same verdict, no
model call. The LLM contributes *labeled evidence relationships*, never a verdict.
Every scoring change needs a test and a `SCORING_VERSION` bump. Document the
formula in `docs/SCORING.md`.

## Verdicts

`VERIFIED, LIKELY_TRUE, PARTLY_TRUE, MISLEADING, UNVERIFIED, LIKELY_FALSE, FALSE,
SATIRE, OPINION`

- `UNVERIFIED` is the correct answer when evidence is insufficient. It is not a
  failure, and it is not `FALSE`.
- Absence of evidence is not evidence of falsehood.
- N copies of one syndicated article are **one** evidence origin, not N.
- Media integrity and claim context are separate judgements. An authentic image
  with a false caption is `MISLEADING`, and the report must say the image itself
  showed no manipulation signals.
- A technical failure (Ollama down, fetch timeout) produces `FAILED` or
  `UNVERIFIED` with a stated reason — never `FALSE`.

## Atomic claims

Never verify a whole article as one blob. Decompose into independently checkable
claims, each carrying its own entities, dates, numbers, and locations, and each
tagged with a `ClaimOrigin` (`USER_CAPTION`, `VIDEO_TRANSCRIPT`, `ON_SCREEN_TEXT`,
`ARTICLE_TEXT`, `SOCIAL_POST_TEXT`, `OCR_TEXT`). Origin matters: an authentic
video with a false user caption must not contaminate the transcript's claims.

## Evidence

A retrieved document is not evidence. Evidence is the specific passage relevant to
a specific claim, labeled `SUPPORTS | CONTRADICTS | NEUTRAL | INSUFFICIENT`.
Store only the excerpt needed to justify the verdict, plus metadata and a link —
we do not republish full copyrighted articles.

Contradicting evidence is always shown, even when the overall verdict is positive.

## Sources

Never hardcode `if domain == "reuters.com": trust`. Source type is one weighted
feature among many. Primary-source proximity raises relevance for a given claim
type; it is never a truth oracle.

## Confidence

The UI shows `LOW | MEDIUM | HIGH`. Never render false precision like "98.7% true".
The numeric score exists for debugging and future calibration only.
