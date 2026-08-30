"""Atomic claim extraction.

Splits content into independently checkable assertions. "A 7.8 earthquake hit
Japan today, killing 500" is not one claim -- it is several, and they can have
different verdicts. Verifying the blob as a whole would hide exactly the case
that matters: mostly-true text carrying one false detail.

This implementation is rule-based, so it runs with no model and no network. An
Ollama-backed extractor lands in a later phase behind the same interface; the
structured output contract here is what that extractor will have to satisfy.

Numbers, dates, and money are extracted as *parsed values*, not strings, because
scoring compares magnitudes: "$50 billion" versus "$5 billion" has to register as
an order-of-magnitude contradiction rather than a string difference.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.core.enums import ClaimOrigin, ClaimType

#: Sentence boundaries. Abbreviations and decimals are protected below.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?।])\s+")

#: Bangla uses the danda; its digits are a separate Unicode range.
_BENGALI_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

#: Abbreviations whose trailing period is not a sentence end.
_ABBREVIATIONS = (
    "mr.",
    "mrs.",
    "ms.",
    "dr.",
    "prof.",
    "sr.",
    "jr.",
    "st.",
    "vs.",
    "inc.",
    "ltd.",
    "co.",
    "corp.",
    "u.s.",
    "u.k.",
    "e.g.",
    "i.e.",
    "etc.",
    "approx.",
    "est.",
    "no.",
    "fig.",
    "a.m.",
    "p.m.",
)

_MONEY_RE = re.compile(
    r"(?P<currency>[$€£¥₹৳]|\b(?:USD|EUR|GBP|BDT|INR|JPY)\b)\s*"
    r"(?P<amount>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<scale>billion|million|trillion|thousand|bn|mn|k|crore|lakh)?",
    re.IGNORECASE,
)

_PERCENT_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?:%|percent|per cent|শতাংশ)", re.IGNORECASE)

_NUMBER_RE = re.compile(
    r"\b(?P<value>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<scale>billion|million|trillion|thousand|bn|mn|crore|lakh)?\b",
    re.IGNORECASE,
)

_DATE_PATTERNS = (
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
    re.compile(
        r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b",
        re.IGNORECASE,
    ),
)

#: Relative references. These matter enormously: "today" in a claim about a
#: three-year-old photo is the whole misinformation pattern.
_RELATIVE_DATE_RE = re.compile(
    r"\b(today|yesterday|tomorrow|this (?:morning|afternoon|evening|week|month|year)|"
    r"last (?:night|week|month|year)|next (?:week|month|year)|just now|moments ago|"
    r"আজ|গতকাল|আগামীকাল|এই সপ্তাহে|গত সপ্তাহে)\b",
    re.IGNORECASE,
)

_SCALE_MULTIPLIERS = {
    "thousand": 1_000,
    "k": 1_000,
    "million": 1_000_000,
    "mn": 1_000_000,
    "billion": 1_000_000_000,
    "bn": 1_000_000_000,
    "trillion": 1_000_000_000_000,
    "lakh": 100_000,
    "crore": 10_000_000,
}

#: Phrasing that marks a statement as opinion or prediction rather than a
#: checkable fact. Checking "X is the best" against evidence is a category error.
_OPINION_MARKERS = re.compile(
    r"\b(i think|i believe|in my opinion|arguably|should|ought to|best|worst|"
    r"beautiful|ugly|terrible|wonderful|deserve|hopefully|probably will)\b",
    re.IGNORECASE,
)
_PREDICTION_MARKERS = re.compile(
    r"\b(will|going to|expected to|forecast|predicted|by \d{4}|next year|soon)\b",
    re.IGNORECASE,
)

_ATTRIBUTION_MARKERS = re.compile(
    r"\b(said|says|according to|reported|claimed|stated|announced|told|"
    r"বলেছেন|জানিয়েছে|অনুযায়ী)\b",
    re.IGNORECASE,
)

_QUOTE_RE = re.compile(r'"([^"]{10,})"|“([^”]{10,})”')


@dataclass(slots=True)
class ExtractedClaim:
    """One atomic claim with its parsed components."""

    claim_text: str
    normalized_claim: str
    language: str
    claim_type: ClaimType
    origin: ClaimOrigin
    importance: float
    dates: list[dict[str, Any]] = field(default_factory=list)
    numbers: list[dict[str, Any]] = field(default_factory=list)
    money: list[dict[str, Any]] = field(default_factory=list)
    percentages: list[dict[str, Any]] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    entities: list[dict[str, str]] = field(default_factory=list)


def _protect_abbreviations(text: str) -> str:
    """Mask periods that do not end sentences, so splitting stays correct."""
    protected = text
    for abbr in _ABBREVIATIONS:
        protected = re.sub(
            re.escape(abbr), abbr.replace(".", "\x00"), protected, flags=re.IGNORECASE
        )
    # Decimals: 7.8 must not split into "7" and "8". The sentinel is written as
    # a real NUL in the replacement, not an escape -- re treats "\x00" in a
    # template as an unknown escape and raises.
    protected = re.sub(r"(\d)\.(\d)", "\\1\x00\\2", protected)
    return protected


def split_sentences(text: str) -> list[str]:
    """Split into sentences, handling English and Bangla punctuation."""
    if not text or not text.strip():
        return []

    protected = _protect_abbreviations(text)
    parts = _SENTENCE_SPLIT.split(protected)
    return [p.replace("\x00", ".").strip() for p in parts if p.replace("\x00", ".").strip()]


def _parse_scaled(value: str, scale: str | None) -> float | None:
    try:
        number = float(value.replace(",", ""))
    except ValueError:
        return None
    if scale:
        number *= _SCALE_MULTIPLIERS.get(scale.lower(), 1)
    return number


def extract_money(text: str) -> list[dict[str, Any]]:
    """Extract monetary amounts as parsed values.

    Normalizing to a single number is what lets scoring detect that $50bn and
    $5bn differ by an order of magnitude.
    """
    results = []
    for match in _MONEY_RE.finditer(text):
        amount = _parse_scaled(match.group("amount"), match.group("scale"))
        if amount is None:
            continue
        results.append(
            {
                "raw": match.group(0).strip(),
                "currency": match.group("currency"),
                "value": amount,
                "scale": match.group("scale"),
            }
        )
    return results


def extract_percentages(text: str) -> list[dict[str, Any]]:
    results = []
    for match in _PERCENT_RE.finditer(text):
        try:
            results.append({"raw": match.group(0).strip(), "value": float(match.group("value"))})
        except ValueError:
            continue
    return results


def extract_numbers(
    text: str, *, exclude_spans: list[tuple[int, int]] | None = None
) -> list[dict[str, Any]]:
    """Extract plain numbers, skipping spans already claimed by money/percent."""
    exclude_spans = exclude_spans or []
    results = []

    for match in _NUMBER_RE.finditer(text):
        if any(start <= match.start() < end for start, end in exclude_spans):
            continue
        value = _parse_scaled(match.group("value"), match.group("scale"))
        if value is None:
            continue
        # Bare four-digit numbers in date range are almost always years, which
        # the date extractor handles.
        if (
            1900 <= value <= 2100
            and match.group("scale") is None
            and "." not in match.group("value")
        ):
            continue
        results.append(
            {"raw": match.group(0).strip(), "value": value, "scale": match.group("scale")}
        )
    return results


def extract_dates(text: str) -> list[dict[str, Any]]:
    """Extract absolute dates and relative references.

    Relative references are kept explicitly: they must be resolved against the
    submission time, and a mismatch between "today" and the evidence's actual
    date is a primary misinformation signal.
    """
    results: list[dict[str, Any]] = []

    for pattern in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            results.append({"raw": match.group(0), "type": "absolute"})

    for match in _RELATIVE_DATE_RE.finditer(text):
        results.append({"raw": match.group(0), "type": "relative"})

    # Standalone years.
    for match in re.finditer(r"\b(1[89]\d{2}|20\d{2})\b", text):
        year = match.group(0)
        if not any(year in r["raw"] for r in results):
            results.append({"raw": year, "type": "year", "value": int(year)})

    return results


def extract_entities(text: str) -> list[dict[str, str]]:
    """Extract candidate named entities.

    Capitalization-based, so it is approximate. It is used for retrieval overlap
    and entity-mismatch signals, where recall matters more than precision -- a
    spurious candidate costs a little ranking noise, a missed one costs a
    mismatch we fail to notice.
    """
    entities: list[dict[str, str]] = []
    seen: set[str] = set()

    for match in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", text):
        surface = match.group(1)
        # Skip a leading sentence-initial word, which is capitalized by grammar
        # rather than because it names something.
        if match.start() == 0 and " " not in surface:
            continue
        if len(surface) < 3 or surface.lower() in seen:
            continue
        seen.add(surface.lower())
        entities.append({"text": surface, "type": "UNKNOWN"})

    return entities


def _classify(sentence: str) -> ClaimType:
    """Assign a claim type. Order matters: opinion and prediction win, because
    checking them against evidence is a category error."""
    if _OPINION_MARKERS.search(sentence):
        return ClaimType.OPINION
    if _PREDICTION_MARKERS.search(sentence):
        return ClaimType.PREDICTION
    if _QUOTE_RE.search(sentence):
        return ClaimType.QUOTE
    if _ATTRIBUTION_MARKERS.search(sentence):
        return ClaimType.ATTRIBUTION
    if _PERCENT_RE.search(sentence) or _MONEY_RE.search(sentence):
        return ClaimType.STATISTIC
    if re.search(r"\b(because|due to|caused by|led to|resulted in)\b", sentence, re.I):
        return ClaimType.CAUSAL
    if _RELATIVE_DATE_RE.search(sentence) or any(p.search(sentence) for p in _DATE_PATTERNS):
        return ClaimType.EVENT
    return ClaimType.OTHER


def _importance(sentence: str, index: int, total: int, claim_type: ClaimType) -> float:
    """How load-bearing a claim is.

    Drives the overall verdict, where one false central claim must outweigh
    several true incidental ones.
    """
    score = 0.5

    # Journalism front-loads the central assertion.
    if index == 0:
        score += 0.25
    elif index < 3:
        score += 0.1

    # Specific, checkable detail is what a claim stands or falls on.
    if _MONEY_RE.search(sentence) or _PERCENT_RE.search(sentence):
        score += 0.15
    if any(p.search(sentence) for p in _DATE_PATTERNS) or _RELATIVE_DATE_RE.search(sentence):
        score += 0.1
    if re.search(
        r"\b(killed|died|deaths|casualties|injured|arrested|banned|approved)\b", sentence, re.I
    ):
        score += 0.15

    # Opinions and predictions cannot be central to a factual verdict.
    if claim_type in (ClaimType.OPINION, ClaimType.PREDICTION):
        score -= 0.3

    return max(0.05, min(1.0, score))


def normalize_claim(sentence: str) -> str:
    """Canonical form for retrieval and comparison.

    The original is always preserved separately -- we never translate away or
    discard what the user actually submitted.
    """
    normalized = sentence.translate(_BENGALI_DIGITS)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.rstrip(".!?।")


def extract_claims(
    text: str,
    *,
    language: str = "en",
    origin: ClaimOrigin = ClaimOrigin.USER_TEXT,
    max_claims: int = 25,
) -> list[ExtractedClaim]:
    """Decompose text into atomic claims."""
    if not text or not text.strip():
        return []

    sentences = split_sentences(text)
    if not sentences:
        return []

    claims: list[ExtractedClaim] = []

    for index, sentence in enumerate(sentences[:max_claims]):
        # Fragments too short to assert anything checkable.
        if len(sentence) < 15:
            continue

        claim_type = _classify(sentence)

        money = extract_money(sentence)
        percentages = extract_percentages(sentence)
        money_spans = [(m.start(), m.end()) for m in _MONEY_RE.finditer(sentence)]
        percent_spans = [(m.start(), m.end()) for m in _PERCENT_RE.finditer(sentence)]
        numbers = extract_numbers(sentence, exclude_spans=money_spans + percent_spans)

        claims.append(
            ExtractedClaim(
                claim_text=sentence,
                normalized_claim=normalize_claim(sentence),
                language=language,
                claim_type=claim_type,
                origin=origin,
                importance=_importance(sentence, index, len(sentences), claim_type),
                dates=extract_dates(sentence),
                numbers=numbers,
                money=money,
                percentages=percentages,
                entities=extract_entities(sentence),
            )
        )

    return claims
