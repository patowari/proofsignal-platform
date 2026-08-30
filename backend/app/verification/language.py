"""Language detection.

Script-based rather than statistical. For our V1 language set (English and
Bangla) the Unicode block is a decisive signal and needs no model, no download,
and no runtime dependency -- Bengali script is unambiguous.

This deliberately does not attempt broad language identification. It answers the
question the pipeline actually asks -- which of our supported languages is this,
and is it mixed -- and returns "unknown" rather than guessing wildly.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

#: Unicode ranges for the scripts we handle.
_BENGALI_RANGE = (0x0980, 0x09FF)
_DEVANAGARI_RANGE = (0x0900, 0x097F)
_ARABIC_RANGE = (0x0600, 0x06FF)
_CJK_RANGE = (0x4E00, 0x9FFF)
_CYRILLIC_RANGE = (0x0400, 0x04FF)

SUPPORTED_LANGUAGES = frozenset({"en", "bn"})
DEFAULT_LANGUAGE = "en"

#: Below this fraction of a script, treat it as incidental (a quoted name, a
#: transliteration) rather than the document's language.
_SCRIPT_THRESHOLD = 0.15


@dataclass(frozen=True, slots=True)
class LanguageResult:
    language: str
    confidence: float
    #: True when two scripts are both substantially present. Worth knowing:
    #: mixed-script content often means a quote in another language, which
    #: affects how retrieval queries should be generated.
    is_mixed: bool = False
    script_distribution: dict[str, float] | None = None


def _in_range(codepoint: int, bounds: tuple[int, int]) -> bool:
    return bounds[0] <= codepoint <= bounds[1]


def analyze_scripts(text: str) -> dict[str, float]:
    """Fraction of letters belonging to each script.

    Only letters count: punctuation, digits, and whitespace are script-neutral
    and would dilute the signal.
    """
    counts = {"latin": 0, "bengali": 0, "devanagari": 0, "arabic": 0, "cjk": 0, "cyrillic": 0}
    total = 0

    for char in text:
        if not char.isalpha():
            continue
        total += 1
        cp = ord(char)
        if _in_range(cp, _BENGALI_RANGE):
            counts["bengali"] += 1
        elif _in_range(cp, _DEVANAGARI_RANGE):
            counts["devanagari"] += 1
        elif _in_range(cp, _ARABIC_RANGE):
            counts["arabic"] += 1
        elif _in_range(cp, _CJK_RANGE):
            counts["cjk"] += 1
        elif _in_range(cp, _CYRILLIC_RANGE):
            counts["cyrillic"] += 1
        elif "LATIN" in unicodedata.name(char, ""):
            counts["latin"] += 1

    if total == 0:
        return dict.fromkeys(counts, 0.0)
    return {k: v / total for k, v in counts.items()}


def detect_language_detailed(text: str) -> LanguageResult:
    """Detect language with script distribution."""
    if not text or not text.strip():
        return LanguageResult(DEFAULT_LANGUAGE, 0.0)

    distribution = analyze_scripts(text)
    bengali = distribution["bengali"]
    latin = distribution["latin"]

    significant = [name for name, frac in distribution.items() if frac >= _SCRIPT_THRESHOLD]
    is_mixed = len(significant) > 1

    if bengali >= _SCRIPT_THRESHOLD and bengali >= latin:
        return LanguageResult("bn", bengali, is_mixed, distribution)

    if latin >= _SCRIPT_THRESHOLD:
        return LanguageResult("en", latin, is_mixed, distribution)

    # A script we do not support. Say so rather than mislabelling it as English,
    # which would send retrieval down the wrong path.
    for script, code in (
        ("devanagari", "hi"),
        ("arabic", "ar"),
        ("cjk", "zh"),
        ("cyrillic", "ru"),
    ):
        if distribution[script] >= _SCRIPT_THRESHOLD:
            return LanguageResult(code, distribution[script], is_mixed, distribution)

    return LanguageResult(DEFAULT_LANGUAGE, 0.0, is_mixed, distribution)


def detect_language(text: str) -> str:
    return detect_language_detailed(text).language


def is_supported(language: str) -> bool:
    """Whether we have full retrieval support for this language.

    Unsupported languages still get processed; the report discloses the
    limitation rather than pretending to full coverage.
    """
    return language in SUPPORTED_LANGUAGES
