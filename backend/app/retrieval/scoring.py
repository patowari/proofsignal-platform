"""Lexical relevance scoring for retrieval candidates.

Pure functions: text and queries in, a 0-1 score out. No I/O, no model, so this
runs with no optional dependencies installed and is exhaustively testable.

Bangla needs explicit handling. Bengali script has no capitalization to signal
proper nouns, words carry heavy inflectional suffixes, and digits live in a
separate Unicode range -- so a naive English-shaped tokenizer scores Bangla
close to zero and the system silently fails to find obviously relevant articles.
"""

from __future__ import annotations

import re
import unicodedata

#: Bengali digits map to ASCII so "৮.৫" and "8.5" compare as the same number.
_BENGALI_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

#: Very common words carry no discriminating signal. Kept deliberately short:
#: over-aggressive stopword removal strips meaning from short claims.
_STOPWORDS_EN = frozenset(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "then",
        "than",
        "that",
        "this",
        "these",
        "those",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "with",
        "by",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "has",
        "have",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "can",
        "it",
        "its",
        "his",
        "her",
        "their",
        "our",
        "your",
        "my",
        "we",
        "they",
        "he",
        "she",
        "you",
        "i",
        "not",
        "no",
        "nor",
        "so",
        "such",
        "only",
        "own",
        "same",
        "too",
        "very",
        "just",
        "about",
        "after",
        "before",
        "over",
        "under",
        "again",
        "further",
        "once",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "all",
        "any",
        "both",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "what",
        "which",
        "who",
        "whom",
    ]
)

#: Bangla function words and extremely common verbs.
_STOPWORDS_BN = frozenset(
    [
        "এই",
        "সেই",
        "ওই",
        "এবং",
        "বা",
        "কিন্তু",
        "যদি",
        "তবে",
        "যে",
        "যা",
        "এর",
        "তার",
        "তাদের",
        "আমাদের",
        "আপনার",
        "আমার",
        "করে",
        "করা",
        "হয়",
        "হয়েছে",
        "হবে",
        "ছিল",
        "আছে",
        "নেই",
        "থেকে",
        "জন্য",
        "সঙ্গে",
        "দিয়ে",
        "নিয়ে",
        "পর",
        "আগে",
        "মধ্যে",
        "সব",
        "কিছু",
        "একটি",
        "একটা",
        "এক",
        "দুই",
        "তিন",
        "করেন",
        "বলে",
        "বলেছেন",
        "জানান",
        "জানিয়েছে",
        "হিসেবে",
        "সম্পর্কে",
        "ও",
        "তবু",
        "যদিও",
        "কারণ",
    ]
)

#: Suffixes stripped to match inflected forms. Bengali is agglutinative, so
#: "শিক্ষকদের" (of the teachers) must match "শিক্ষক" (teacher) or a headline
#: about the same subject scores zero.
_BENGALI_SUFFIXES = (
    "েরই",
    "দেরকে",
    "গুলোর",
    "গুলোতে",
    "টিতে",
    "টির",
    "দের",
    "গুলো",
    "গুলি",
    "রা",
    "কে",
    "তে",
    "য়ে",
    "ের",
    "ার",
    "টি",
    "টা",
    "খানা",
    "খানি",
    "েই",
    "ও",
)

#: Words that are long enough to look discriminating but appear in a large
#: share of headlines from this corpus. Matching only these is coincidence:
#: without the list, a claim about an embassy on Mars "matches" a central bank
#: report because both mention Bangladesh.
_LOW_INFORMATION_TERMS = frozenset(
    {
        # Bangla
        "বাংলাদেশ",
        "বাংলাদেশে",
        "বাংলাদেশের",
        "সরকার",
        "সরকারের",
        "দেশে",
        "ঢাকা",
        "ঢাকায়",
        "মানুষ",
        "প্রধান",
        "কর্মকর্তা",
        "বিষয়ে",
        "ক্ষেত্রে",
        "অনুষ্ঠিত",
        "জানানো",
        "সংবাদ",
        "প্রতিবেদন",
        # English
        "bangladesh",
        "government",
        "official",
        "officials",
        "people",
        "country",
        "national",
        "report",
        "reports",
        "news",
        "dhaka",
        "minister",
        "ministry",
        "president",
        "authority",
        "authorities",
    }
)

_WORD_RE = re.compile(r"[\wঀ-৿]+", re.UNICODE)

#: Below this, a match is noise rather than evidence of relevance.
MIN_MEANINGFUL_SCORE = 0.08


def _is_bengali(token: str) -> bool:
    return any("ঀ" <= c <= "৿" for c in token)


def _strip_bengali_suffix(token: str) -> str:
    """Crude stemming for Bengali.

    Longest suffix first, and never reduce a token below three characters --
    over-stemming collapses distinct words together and creates false matches.
    """
    for suffix in sorted(_BENGALI_SUFFIXES, key=len, reverse=True):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def _strip_english_suffix(token: str) -> str:
    """Light English stemming: plurals and common verb endings only."""
    for suffix in ("ies", "ing", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            if suffix == "ies":
                return token[:-3] + "y"
            return token[: -len(suffix)]
    return token


def tokenize(text: str, *, language: str | None = None) -> list[str]:
    """Split text into normalized, stemmed tokens.

    Handles both scripts in one pass, since real content mixes them: a Bangla
    article routinely contains English names, dates, and numbers.
    """
    if not text:
        return []

    text = unicodedata.normalize("NFKC", text).translate(_BENGALI_DIGITS).lower()

    tokens: list[str] = []
    for raw in _WORD_RE.findall(text):
        if len(raw) < 2:
            continue
        if _is_bengali(raw):
            if raw in _STOPWORDS_BN:
                continue
            tokens.append(_strip_bengali_suffix(raw))
        else:
            if raw in _STOPWORDS_EN:
                continue
            # Keep digits verbatim: numbers are high-signal for claim matching.
            tokens.append(raw if raw.isdigit() else _strip_english_suffix(raw))

    return tokens


def _numbers_in(tokens: list[str]) -> set[str]:
    return {t for t in tokens if t.isdigit() or re.fullmatch(r"\d+\.\d+", t)}


def score_against_queries(text: str, queries: list[str], *, language: str | None = None) -> float:
    """Score a document's relevance to a claim's queries, 0-1.

    Combines proportional token overlap with bonuses for the signals that most
    reliably indicate two texts are about the same event: shared rare terms,
    shared numbers, and matching multi-word phrases.
    """
    if not text or not queries:
        return 0.0

    doc_tokens = tokenize(text, language=language)
    if not doc_tokens:
        return 0.0
    doc_set = set(doc_tokens)

    best = 0.0
    for query in queries:
        query_tokens = tokenize(query, language=language)
        if not query_tokens:
            continue
        query_set = set(query_tokens)

        overlap = query_set & doc_set
        if not overlap:
            continue

        # A match on one common word is coincidence, not relevance. "Bangladesh"
        # appears in a large share of Bangladeshi headlines, so a claim about an
        # embassy on Mars would otherwise "match" a central bank profit report.
        # Require either a discriminating term or genuine multi-word overlap.
        discriminating = {
            t for t in overlap if (len(t) >= 6 or t.isdigit()) and t not in _LOW_INFORMATION_TERMS
        }
        if not discriminating:
            continue

        # Proportion of the query found in the document. Query-relative rather
        # than document-relative, so a long article is not penalized for
        # containing material beyond the claim.
        coverage = len(overlap) / len(query_set)

        # Longer tokens are rarer and more discriminating: matching
        # "ভূমিকম্প" says far more than matching "নতুন".
        rare_matches = sum(1 for t in overlap if len(t) >= 6)
        rare_bonus = min(0.25, rare_matches * 0.06)

        # Shared numbers are strong evidence of the same event -- and numeric
        # disagreement is what later flags a contradiction.
        shared_numbers = _numbers_in(query_tokens) & _numbers_in(doc_tokens)
        number_bonus = min(0.20, len(shared_numbers) * 0.10)

        # Adjacent query tokens appearing adjacently in the document indicate a
        # real phrase match rather than scattered coincidental words.
        phrase_bonus = _phrase_bonus(query_tokens, doc_tokens)

        score = min(1.0, coverage * 0.6 + rare_bonus + number_bonus + phrase_bonus)
        best = max(best, score)

    return best if best >= MIN_MEANINGFUL_SCORE else 0.0


def _phrase_bonus(query_tokens: list[str], doc_tokens: list[str]) -> float:
    """Reward consecutive query bigrams appearing in the document."""
    if len(query_tokens) < 2:
        return 0.0

    doc_bigrams = {(doc_tokens[i], doc_tokens[i + 1]) for i in range(len(doc_tokens) - 1)}
    query_bigrams = [(query_tokens[i], query_tokens[i + 1]) for i in range(len(query_tokens) - 1)]
    matches = sum(1 for bg in query_bigrams if bg in doc_bigrams)
    return min(0.25, matches * 0.12)


def build_queries(claim_text: str, *, language: str = "en", max_queries: int = 4) -> list[str]:
    """Build retrieval queries from a claim.

    Produces several shapes because one query rarely serves every source: the
    full claim matches close paraphrases, while a keyword-only form matches
    reports that word the same facts differently.
    """
    if not claim_text or not claim_text.strip():
        return []

    queries: list[str] = [claim_text.strip()]

    tokens = tokenize(claim_text, language=language)
    if tokens:
        # Content-word query: drops filler that dilutes overlap scoring.
        significant = [t for t in tokens if len(t) >= 4 or t.isdigit()]
        if significant and len(significant) < len(tokens):
            queries.append(" ".join(significant[:12]))

        # Rare-term query: the most discriminating words alone.
        rare = sorted({t for t in tokens if len(t) >= 6}, key=len, reverse=True)[:6]
        if len(rare) >= 2:
            queries.append(" ".join(rare))

    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for query in queries:
        key = query.lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(query)

    return unique[:max_queries]
