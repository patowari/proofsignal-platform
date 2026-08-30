"""Evidence extraction and classification.

A retrieved document is not evidence. Evidence is the specific passage relevant
to a specific claim, labeled with its relationship.

Classification here is deterministic and lexical -- no model required, so it
runs on any machine and is fully testable. It is deliberately conservative:
when the signals do not clearly indicate support or contradiction, it returns
NEUTRAL rather than guessing. An over-eager classifier that labels loosely
related passages as SUPPORTS would manufacture confidence the evidence does not
justify, which is the exact failure this product exists to avoid.

An LLM/NLI classifier lands later behind the same interface; this establishes
the contract and provides the fallback for when no model is available.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.enums import EvidenceRelationship
from app.retrieval.scoring import score_against_queries, tokenize

#: Sentence boundaries for English and Bangla.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?।])\s+")

#: Explicit negation and correction language. These are what distinguish a
#: refutation from a report, in both languages we support.
_NEGATION_MARKERS_EN = (
    "denied",
    "denies",
    "false",
    "untrue",
    "no evidence",
    "not true",
    "debunked",
    "misleading",
    "rumour",
    "rumor",
    "hoax",
    "fabricated",
    "did not",
    "does not",
    "was not",
    "were not",
    "never happened",
    "incorrect",
    "inaccurate",
    "refuted",
    "contradicts",
    "no such",
    "baseless",
    "unfounded",
    "misinformation",
    "disinformation",
)

_NEGATION_MARKERS_BN = (
    "অস্বীকার",
    "গুজব",
    "ভুয়া",
    "মিথ্যা",
    "ভিত্তিহীন",
    "সত্য নয়",
    "হয়নি",
    "নয়",
    "না",
    "অসত্য",
    "বিভ্রান্তিকর",
    "প্রমাণ নেই",
    "খণ্ডন",
    "অপপ্রচার",
)

#: Affirmative reporting language. Weaker signal than negation, because most
#: news prose is affirmative by default.
_CONFIRMATION_MARKERS_EN = (
    "confirmed",
    "announced",
    "said",
    "reported",
    "according to",
    "stated",
    "verified",
    "official",
    "issued",
    "declared",
    "approved",
)

_CONFIRMATION_MARKERS_BN = (
    "নিশ্চিত",
    "ঘোষণা",
    "জানিয়েছে",
    "বলেছেন",
    "প্রকাশ",
    "অনুযায়ী",
    "সিদ্ধান্ত",
    "অনুমোদন",
    "জারি",
)

#: Stripped from token edges before comparing against markers, so "নয়," and
#: "denied." still match.
_PUNCTUATION = " .,;:!?()[]{}\"'‘’“”।–—-"

#: Passage length bounds. Too short cannot justify anything; too long is a
#: copyright problem and buries the relevant sentence.
MIN_PASSAGE_CHARS = 60
MAX_PASSAGE_CHARS = 600


@dataclass(slots=True)
class ExtractedEvidence:
    """A claim-relevant passage with its labeled relationship."""

    passage: str
    relationship: EvidenceRelationship
    relevance: float
    #: How directly the passage addresses the claim's specific assertion, as
    #: opposed to merely sharing its topic.
    directness: float
    #: Why this label was chosen, stored so a verdict stays explainable.
    rationale: str
    classifier: str = "lexical"
    classifier_version: str = "1.0.0"
    confidence: float = 0.5


def split_passages(text: str) -> list[str]:
    """Split article text into candidate passages.

    Sentence-level, then merged to a readable size: a single sentence often
    lacks the context needed to judge it, while a whole paragraph dilutes the
    relevance signal.
    """
    if not text:
        return []

    passages: list[str] = []
    for block in text.split("\n"):
        block = block.strip()
        if not block:
            continue

        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(block) if s.strip()]
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) + 1 <= MAX_PASSAGE_CHARS:
                current = f"{current} {sentence}".strip()
            else:
                if len(current) >= MIN_PASSAGE_CHARS:
                    passages.append(current)
                current = sentence[:MAX_PASSAGE_CHARS]
        if len(current) >= MIN_PASSAGE_CHARS:
            passages.append(current)

    return passages


def _count_markers(text_lower: str, markers: tuple[str, ...]) -> int:
    """Count marker phrases, matching whole words only.

    Substring matching is wrong and dangerously so: Bengali "না" (not) occurs
    inside "মুনাফা" (profit), so every article about profits registered as a
    denial and true claims came back FALSE. English has the same trap -- "no"
    inside "north", "not" inside "note".

    Multi-word markers ("no evidence") are matched as phrases with boundaries
    at each end.
    """
    # Regex word boundaries are unreliable here: Bengali combining marks are not
    # word characters, so "\bনা\b" still matches inside "মুনাফা". Comparing
    # whitespace-separated tokens is unambiguous in both scripts.
    tokens = {t.strip(_PUNCTUATION) for t in text_lower.split()}

    count = 0
    for marker in markers:
        if " " in marker:
            # Multi-word phrase: fall back to substring, which is safe because
            # a whole phrase cannot hide inside a single word.
            if marker in text_lower:
                count += 1
        elif marker in tokens:
            count += 1
    return count


def _extract_numbers(text: str) -> set[float]:
    """Numeric values in a text, for magnitude comparison."""
    from app.verification.claim_extraction import extract_money, extract_numbers

    values: set[float] = set()
    for item in extract_numbers(text):
        values.add(float(item["value"]))
    for item in extract_money(text):
        values.add(float(item["value"]))
    return values


#: Values that are almost always years or fiscal-year parts rather than
#: quantities being asserted. Comparing "2025" against a claim's "26 thousand
#: crore" is meaningless and produced false contradictions.
_YEAR_MIN = 1900
_YEAR_MAX = 2100


def _comparable_numbers(text: str) -> set[float]:
    """Numbers worth comparing between a claim and a passage.

    Excludes years, which appear constantly in news prose as dates and fiscal
    periods and have nothing to do with the quantity a claim asserts.
    """
    return {
        value
        for value in _extract_numbers(text)
        if not (_YEAR_MIN <= value <= _YEAR_MAX and float(value).is_integer())
    }


def _numeric_conflict(claim_text: str, passage: str) -> tuple[bool, str]:
    """Detect a genuine numeric disagreement.

    Conservative on purpose. Two conditions must both hold:

    1. The claim's number does NOT appear in the passage (within tolerance).
       If the passage states the same figure, there is no disagreement --
       whatever other numbers it also contains.
    2. Some passage number is close enough in magnitude to be *about the same
       quantity*, but materially different.

    Without condition 1, an article confirming "26 thousand crore" was labelled
    a contradiction because it also mentioned the 2023-24 fiscal year. That
    turned true claims into FALSE verdicts, which is the worst failure this
    product can have.
    """
    claim_numbers = _comparable_numbers(claim_text)
    passage_numbers = _comparable_numbers(passage)
    if not claim_numbers or not passage_numbers:
        return False, ""

    for claim_value in claim_numbers:
        if claim_value == 0:
            continue

        # Condition 1: the passage corroborates this figure, so no conflict.
        # 2% tolerance covers rounding ("25,977" reported as "26 thousand").
        if any(abs(claim_value - p) / max(abs(claim_value), 1.0) <= 0.02 for p in passage_numbers):
            continue

        # Condition 2: a comparable-magnitude number that differs materially.
        for passage_value in passage_numbers:
            if passage_value == 0:
                continue
            ratio = max(claim_value, passage_value) / min(claim_value, passage_value)
            # Between 1.5x and 20x: same kind of quantity, different value.
            # Beyond 20x the two numbers are almost certainly measuring
            # different things rather than disagreeing.
            if 1.5 <= ratio <= 20:
                return True, f"claim states {claim_value:g}, source states {passage_value:g}"

    return False, ""


def classify_passage(
    claim_text: str, passage: str, *, language: str = "en", relevance: float = 0.0
) -> ExtractedEvidence:
    """Label a passage's relationship to a claim.

    Conservative by design: NEUTRAL unless the signals clearly point one way.
    """
    passage_lower = passage.lower()
    is_bangla = language == "bn"

    negation_markers = _NEGATION_MARKERS_BN if is_bangla else _NEGATION_MARKERS_EN
    confirmation_markers = _CONFIRMATION_MARKERS_BN if is_bangla else _CONFIRMATION_MARKERS_EN

    # Both scripts are checked regardless of detected language, because Bangla
    # articles routinely quote English and vice versa.
    negations = _count_markers(passage_lower, negation_markers) + _count_markers(
        passage_lower, _NEGATION_MARKERS_EN if is_bangla else _NEGATION_MARKERS_BN
    )
    confirmations = _count_markers(passage_lower, confirmation_markers)

    # How much of the claim's substance appears in this passage.
    claim_tokens = set(tokenize(claim_text, language=language))
    passage_tokens = set(tokenize(passage, language=language))
    overlap = len(claim_tokens & passage_tokens) / max(len(claim_tokens), 1)
    directness = min(1.0, overlap * 1.4)

    has_numeric_conflict, conflict_detail = _numeric_conflict(claim_text, passage)

    # A passage citing a different time period is reporting a different figure,
    # not disputing this one. "Profit was 15,300 crore in FY2023-24" does not
    # contradict a claim about FY2025-26 -- it is simply about another year.
    # Without this, historical-comparison paragraphs (which news articles are
    # full of) manufacture contradictions against true claims.
    claim_years = {v for v in _extract_numbers(claim_text) if _YEAR_MIN <= v <= _YEAR_MAX}
    passage_years = {v for v in _extract_numbers(passage) if _YEAR_MIN <= v <= _YEAR_MAX}
    discusses_other_period = bool(passage_years) and not (claim_years & passage_years)

    # A numeric conflict on an otherwise-relevant passage is the strongest
    # contradiction signal available without a model.
    if has_numeric_conflict and overlap >= 0.25 and not discusses_other_period:
        return ExtractedEvidence(
            passage=passage,
            relationship=EvidenceRelationship.CONTRADICTS,
            relevance=relevance,
            directness=directness,
            rationale=f"Numeric disagreement: {conflict_detail}",
            confidence=0.7,
        )

    if negations >= 1 and overlap >= 0.3:
        return ExtractedEvidence(
            passage=passage,
            relationship=EvidenceRelationship.CONTRADICTS,
            relevance=relevance,
            directness=directness,
            rationale="Passage uses explicit denial or correction language about this claim.",
            confidence=0.6,
        )

    # A passage that repeats the claim's specific figures is reporting the same
    # fact. This is the strongest support signal available without a model, and
    # it works across paraphrase and across languages, where token overlap does
    # not: a Bangla article restating a claim in different words shares few
    # tokens but the same numbers.
    shared_numbers = _comparable_numbers(claim_text) & _comparable_numbers(passage)
    if shared_numbers and overlap >= 0.25:
        return ExtractedEvidence(
            passage=passage,
            relationship=EvidenceRelationship.SUPPORTS,
            relevance=relevance,
            directness=max(directness, 0.7),
            rationale=(
                "Passage reports the same figure"
                f" ({', '.join(f'{n:g}' for n in sorted(shared_numbers))})"
                " for the same subject."
            ),
            confidence=0.7,
        )

    # Support otherwise needs substantial overlap: a shared topic is not support.
    # The threshold is lower for Bangla, where inflection and freer word order
    # mean two reports of the same fact share fewer exact tokens than in English.
    support_threshold = 0.38 if is_bangla else 0.5
    if overlap >= support_threshold and confirmations >= 1:
        return ExtractedEvidence(
            passage=passage,
            relationship=EvidenceRelationship.SUPPORTS,
            relevance=relevance,
            directness=directness,
            rationale="Passage reports the same facts in affirmative terms.",
            confidence=0.6,
        )

    if overlap >= (0.5 if is_bangla else 0.65):
        return ExtractedEvidence(
            passage=passage,
            relationship=EvidenceRelationship.SUPPORTS,
            relevance=relevance,
            directness=directness,
            rationale="Passage closely restates the claim.",
            confidence=0.5,
        )

    # Related, but it does not settle anything. Shown in the report as a source
    # checked, and contributes nothing to the verdict.
    return ExtractedEvidence(
        passage=passage,
        relationship=EvidenceRelationship.NEUTRAL,
        relevance=relevance,
        directness=directness,
        rationale="Passage is topically related but does not confirm or deny the claim.",
        confidence=0.4,
    )


def extract_evidence_for_claim(
    claim_text: str,
    document_text: str,
    queries: list[str],
    *,
    language: str = "en",
    max_passages: int = 3,
    min_relevance: float = 0.15,
) -> list[ExtractedEvidence]:
    """Find and label the passages of one document relevant to one claim.

    Returns at most `max_passages`, best first. Empty when nothing in the
    document is relevant enough -- which is a legitimate, common outcome.
    """
    passages = split_passages(document_text)
    if not passages:
        return []

    scored: list[tuple[float, str]] = []
    for passage in passages:
        relevance = score_against_queries(passage, queries, language=language)
        if relevance >= min_relevance:
            scored.append((relevance, passage))

    scored.sort(key=lambda pair: pair[0], reverse=True)

    results = [
        classify_passage(claim_text, passage, language=language, relevance=relevance)
        for relevance, passage in scored[:max_passages]
    ]

    # A contradiction matters more than another confirmation, so surface it
    # even if it scored slightly lower on lexical relevance.
    results.sort(
        key=lambda e: (
            e.relationship is EvidenceRelationship.CONTRADICTS,
            e.relevance,
        ),
        reverse=True,
    )
    return results
