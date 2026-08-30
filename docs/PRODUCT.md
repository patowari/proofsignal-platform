# Product

## What this is

An evidence-backed information verification platform. Anonymous visitors submit
content they want checked — a claim, an article URL, a public social post, an
image, a screenshot, or a video — and receive a public report showing what
evidence exists and what that evidence establishes.

## What this is not

This is not an "AI Fake News Detector". We never show a mysterious

    TRUE — 98.73%

The conclusion must be traceable to evidence a reader can click through and judge
for themselves. If we cannot show why, we have not verified anything.

## The principle

> Do not ask AI what is true. Find evidence first, then evaluate what the
> evidence establishes.

An LLM's training data is not evidence. It cannot be cited, dated, or checked. So
the model is confined to two jobs — breaking content into checkable claims, and
interpreting passages we actually retrieved — and it is explicitly forbidden from
using unstated world knowledge. The verdict itself is computed deterministically.

## What a report answers

1. Here is the claim (decomposed into atomic, independently checkable parts).
2. Here is the evidence we found, with sources and dates.
3. Here is what supports it.
4. Here is what contradicts it.
5. Here is what remains unknown.

## Verdicts

| Verdict | Meaning |
|---|---|
| `VERIFIED` | Strong, independent, directly-relevant evidence establishes the claim. |
| `LIKELY_TRUE` | Good supporting evidence, but thin independence, weak sourcing, or minor gaps. |
| `PARTLY_TRUE` | Core is supported; specifics (numbers, dates, scope) are wrong or overstated. |
| `MISLEADING` | Underlying facts are real but framing, timing, or context makes the impression false. |
| `UNVERIFIED` | We could not find sufficient evidence either way. **Not a synonym for false.** |
| `LIKELY_FALSE` | Meaningful contradicting evidence; not fully conclusive. |
| `FALSE` | Strong, independent evidence directly contradicts the claim. |
| `SATIRE` | Originates from a satirical/parody context and is not a sincere assertion. |
| `OPINION` | A value judgement or prediction, not a checkable factual claim. |

### Things that are easy to get wrong

- **Absence of evidence is not evidence of absence.** A claim we cannot check is
  `UNVERIFIED`, never `FALSE`.
- **Volume is not corroboration.** Fifty sites republishing one wire story is one
  source, not fifty. We cluster syndicated copies and count origins.
- **A real image can carry a false claim.** Authentic flood photo + "Dhaka today"
  caption when the photo is three years old = `MISLEADING`, and the report says
  plainly that the image showed no manipulation signals. Integrity and context are
  reported separately.
- **A real video from the wrong year is misleading**, for the same reason.
- **Exaggerating real research is `PARTLY_TRUE` or `MISLEADING`**, not `FALSE`.
- **A screenshot is not proof.** It shows that an image exists, not that the post
  depicted is genuine.
- **A technical failure is not a verdict.** If Ollama is down or a fetch times
  out, we say so. We never convert our own breakage into `FALSE`.

## Honest limitations

We state these in the product, not just in docs:

- We do **not** have internet-wide search. Retrieval covers our indexed RSS
  corpus, GDELT, and URLs given to us. We name the sources actually checked.
- We do **not** have reverse image search. Image matching is limited to our own
  indexed corpus, perceptual hashes, and embeddings. If we cannot identify an
  original source, we say we could not — we never guess one.
- We cannot access private, deleted, paywalled, or login-gated content, and we do
  not attempt to bypass those protections. We report inaccessibility honestly and
  offer the user a way to supply the content directly.
- Results can be wrong, and can change as evidence appears. Verifications are
  versioned; history is preserved rather than overwritten.

## V1 scope

Anonymous and public. No accounts, no login, no profiles. A visitor submits,
watches real pipeline progress, reads a report, and can share its URL. Recent
public verifications are browsable and searchable.
