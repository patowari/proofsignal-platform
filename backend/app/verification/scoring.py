"""Deterministic verdict scoring.

The LLM does not decide verdicts. This module does, from labeled evidence, using
arithmetic anyone can inspect. Same inputs always produce the same verdict.

Why it matters that this is not a model call: a verdict produced by an LLM would
be unreproducible, unauditable, and steerable by any webpage we retrieved. Here,
a page that successfully injects instructions still cannot move the outcome,
because the only thing a model contributes is a per-passage label that then goes
through fixed arithmetic.

Everything here is pure: no I/O, no clock reads (evaluation time is passed in),
no randomness. The formula is documented in docs/SCORING.md; that file and this
module must be changed together, along with a SCORING_VERSION bump.

The weights are engineering judgement, not calibrated against labeled data.
They are explainable and testable, which is the honest claim to make about them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.enums import (
    ClaimType,
    ConfidenceBand,
    EvidenceRelationship,
    PenaltyType,
    SourceType,
    Verdict,
)
from app.core.versions import SCORING_VERSION

# ---------------------------------------------------------------------------
# Tunable constants. Every one of these is referenced in docs/SCORING.md.
# ---------------------------------------------------------------------------

#: Source type weighting. Modulates how much a passage counts; never a truth
#: oracle. No domain is trusted by name -- see .claude/rules/verification.md.
SOURCE_FACTORS: dict[SourceType, float] = {
    SourceType.OFFICIAL_GOVERNMENT: 1.30,
    SourceType.PRIMARY_DOCUMENT: 1.30,
    SourceType.SCIENTIFIC_SOURCE: 1.25,
    SourceType.OFFICIAL_COMPANY: 1.20,
    SourceType.NEWS_AGENCY: 1.15,
    SourceType.NEWS_ORGANIZATION: 1.00,
    SourceType.SPECIALIST_PUBLICATION: 1.00,
    SourceType.BLOG: 0.70,
    SourceType.SOCIAL_MEDIA: 0.60,
    SourceType.USER_PROVIDED: 0.55,
    SourceType.UNKNOWN: 0.50,
}

#: Bonus when the source is the natural primary authority for this claim type
#: (a seismological agency for an earthquake magnitude). Applied before the cap.
PRIMARY_SOURCE_BONUS = 0.15
SOURCE_FACTOR_MIN = 0.50
SOURCE_FACTOR_MAX = 1.30

#: Context penalties, applied to the supported reading of a claim. These are the
#: cases where every individual fact checks out but the claim as framed misleads.
PENALTY_VALUES: dict[PenaltyType, float] = {
    PenaltyType.NUMERIC_MISMATCH: 0.45,
    PenaltyType.DATE_MISMATCH: 0.35,
    PenaltyType.LOCATION_MISMATCH: 0.35,
    PenaltyType.ENTITY_MISMATCH: 0.30,
    PenaltyType.STALE_MEDIA: 0.40,
    PenaltyType.EXAGGERATION: 0.25,
}

#: Non-representative members of an origin cluster contribute only this fraction.
#: This is what stops fifty reprints of one wire story reading as fifty
#: confirmations.
CLUSTER_DAMPING = 0.15

#: Independent origins for full coverage credit.
TARGET_ORIGINS = 3

#: Below this total weight there is not enough evidence to say anything.
#:
#: Lowered from 0.8 in 1.1.0. The original figure was set before evidence
#: classification worked well, when most passages were undifferentiated NEUTRAL
#: noise and a high bar was the only defence against acting on it. With accurate
#: classification, one directly-relevant passage from the publisher that
#: reported the story is real evidence, and 0.8 was discarding it -- a claim
#: could be confirmed verbatim by its own source and still return UNVERIFIED.
#:
#: This does not weaken the strong verdicts: VERIFIED and FALSE still require
#: multiple independent origins and much greater mass (see the constants below).
#: It only lets a single good source produce LIKELY_TRUE instead of nothing.
MIN_EVIDENCE_WEIGHT = 0.45

#: Thresholds for the claim verdict decision table.
NET_VERIFIED = 0.75
NET_STRONG_SUPPORT = 0.60
NET_LIKELY_TRUE = 0.50
NET_LIKELY_FALSE = -0.40
NET_FALSE = -0.75

#: A penalty at or above this level turns strong support into MISLEADING rather
#: than merely PARTLY_TRUE.
PENALTY_MISLEADING_THRESHOLD = 0.35

#: Minimum evidence mass for the strongest verdicts, so a single flimsy source
#: cannot produce VERIFIED or FALSE.
MIN_SUPPORT_FOR_VERIFIED = 2.0
MIN_CONTRADICTION_FOR_FALSE = 1.5
MIN_ORIGINS_FOR_VERIFIED = 3
MIN_ORIGINS_FOR_FALSE = 2

CONFIDENCE_HIGH = 0.70
CONFIDENCE_MEDIUM = 0.40

#: A claim at or above this importance can drive the overall verdict alone.
IMPORTANCE_THRESHOLD = 0.7


# ---------------------------------------------------------------------------
# Inputs and outputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvidenceSignal:
    """One evidence item reduced to what scoring needs.

    Deliberately not the ORM model: keeping this a plain value object is what
    makes the scoring function pure and trivially testable.
    """

    relationship: EvidenceRelationship
    #: Retrieval/reranker score for this passage against this claim, 0-1.
    relevance: float
    source_type: SourceType = SourceType.UNKNOWN
    #: Whether this source is the natural primary authority for this claim type.
    is_primary_source: bool = False
    #: 1.0 when the document's publication window covers the claimed event.
    temporal_factor: float = 1.0
    #: Whether the passage addresses the specific assertion or merely the topic.
    directness: float = 1.0
    #: Origin cluster. Items sharing an id are copies of one report. None means
    #: this item is its own origin.
    cluster_id: str | None = None
    #: Stable identifier, useful when explaining a breakdown.
    evidence_id: str | None = None


@dataclass(frozen=True, slots=True)
class AppliedPenalty:
    penalty_type: PenaltyType
    value: float
    #: What triggered it, e.g. "claim says $50bn, evidence says $5bn".
    reason: str


@dataclass(frozen=True, slots=True)
class ClaimSignals:
    """Everything needed to score one claim."""

    claim_id: str
    claim_type: ClaimType = ClaimType.OTHER
    importance: float = 0.5
    evidence: tuple[EvidenceSignal, ...] = ()
    penalties: tuple[AppliedPenalty, ...] = ()
    #: True when the content came from a source known to publish satire.
    is_satirical_source: bool = False


@dataclass(frozen=True, slots=True)
class ClaimScore:
    """A scored claim, with everything needed to explain it."""

    claim_id: str
    verdict: Verdict
    confidence_band: ConfidenceBand
    confidence_score: float
    support_score: float
    contradiction_score: float
    coverage_score: float
    net: float
    independent_origins: int
    total_weight: float
    applied_penalty: float
    penalties: tuple[AppliedPenalty, ...]
    #: Which numbered rule in docs/SCORING.md produced this verdict.
    decision_rule: int
    evidence_weights: tuple[dict[str, object], ...] = ()

    def to_breakdown(self) -> dict[str, object]:
        """Serializable breakdown for storage and the report UI."""
        return {
            "scoring_version": SCORING_VERSION,
            "verdict": self.verdict.value,
            "confidence_band": self.confidence_band.value,
            "confidence_score": round(self.confidence_score, 4),
            "support_score": round(self.support_score, 4),
            "contradiction_score": round(self.contradiction_score, 4),
            "coverage_score": round(self.coverage_score, 4),
            "net": round(self.net, 4),
            "independent_origins": self.independent_origins,
            "total_weight": round(self.total_weight, 4),
            "applied_penalty": round(self.applied_penalty, 4),
            "penalties": [
                {"type": p.penalty_type.value, "value": p.value, "reason": p.reason}
                for p in self.penalties
            ],
            "decision_rule": self.decision_rule,
            "evidence_weights": list(self.evidence_weights),
        }


@dataclass(frozen=True, slots=True)
class OverallScore:
    verdict: Verdict
    confidence_band: ConfidenceBand
    confidence_score: float
    claim_scores: tuple[ClaimScore, ...]
    decision_rule: int
    #: True when a provider was missing or a stage degraded; caps confidence.
    degraded: bool = False
    degradation_reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_breakdown(self) -> dict[str, object]:
        return {
            "scoring_version": SCORING_VERSION,
            "verdict": self.verdict.value,
            "confidence_band": self.confidence_band.value,
            "confidence_score": round(self.confidence_score, 4),
            "decision_rule": self.decision_rule,
            "degraded": self.degraded,
            "degradation_reasons": list(self.degradation_reasons),
            "claims": [c.to_breakdown() for c in self.claim_scores],
        }


# ---------------------------------------------------------------------------
# Stage 1: evidence weight
# ---------------------------------------------------------------------------


def source_factor(source_type: SourceType, *, is_primary_source: bool = False) -> float:
    """Weight contributed by the source's characteristics.

    Capped in both directions so no single source type can dominate a verdict:
    even a government primary document does not overwhelm contradicting evidence
    on its own.
    """
    base = SOURCE_FACTORS.get(source_type, SOURCE_FACTORS[SourceType.UNKNOWN])
    if is_primary_source:
        base += PRIMARY_SOURCE_BONUS
    return max(SOURCE_FACTOR_MIN, min(SOURCE_FACTOR_MAX, base))


def evidence_weight(signal: EvidenceSignal) -> float:
    """Weight of one evidence item: relevance x source x temporal x directness."""
    return (
        max(0.0, min(1.0, signal.relevance))
        * source_factor(signal.source_type, is_primary_source=signal.is_primary_source)
        * max(0.0, min(1.0, signal.temporal_factor))
        * max(0.0, min(1.0, signal.directness))
    )


# ---------------------------------------------------------------------------
# Stage 2: independence clustering
# ---------------------------------------------------------------------------


def _cluster_weights(
    signals: tuple[EvidenceSignal, ...],
) -> tuple[float, int, list[dict[str, object]]]:
    """Collapse evidence into origin clusters.

    Within a cluster only the strongest item counts fully; the others are damped
    to CLUSTER_DAMPING. Returns (total_weight, origin_count, per-item detail).

    This is the rule that keeps syndication from inflating confidence.
    """
    if not signals:
        return 0.0, 0, []

    clusters: dict[str, list[tuple[EvidenceSignal, float]]] = {}
    detail: list[dict[str, object]] = []

    for index, signal in enumerate(signals):
        weight = evidence_weight(signal)
        # An item with no cluster id is its own origin.
        key = signal.cluster_id or f"__singleton_{index}"
        clusters.setdefault(key, []).append((signal, weight))
        detail.append(
            {
                "evidence_id": signal.evidence_id or f"idx_{index}",
                "relationship": signal.relationship.value,
                "relevance": round(signal.relevance, 4),
                "source_factor": round(
                    source_factor(signal.source_type, is_primary_source=signal.is_primary_source), 4
                ),
                "temporal_factor": round(signal.temporal_factor, 4),
                "directness": round(signal.directness, 4),
                "weight": round(weight, 4),
                "cluster": key,
            }
        )

    total = 0.0
    for members in clusters.values():
        weights = sorted((w for _, w in members), reverse=True)
        total += weights[0] + CLUSTER_DAMPING * sum(weights[1:])

    return total, len(clusters), detail


# ---------------------------------------------------------------------------
# Stage 3-4: claim scoring
# ---------------------------------------------------------------------------


def score_claim(signals: ClaimSignals) -> ClaimScore:
    """Score one claim. Pure: same input always yields the same output."""
    supporting = tuple(
        s for s in signals.evidence if s.relationship is EvidenceRelationship.SUPPORTS
    )
    contradicting = tuple(
        s for s in signals.evidence if s.relationship is EvidenceRelationship.CONTRADICTS
    )

    support_score, support_origins, support_detail = _cluster_weights(supporting)
    contradiction_score, contra_origins, contra_detail = _cluster_weights(contradicting)

    # NEUTRAL and INSUFFICIENT items add no support or contradiction, but they
    # were still checked and are still shown in the report.
    _, _, other_detail = _cluster_weights(
        tuple(
            s
            for s in signals.evidence
            if s.relationship in (EvidenceRelationship.NEUTRAL, EvidenceRelationship.INSUFFICIENT)
        )
    )

    total_weight = support_score + contradiction_score
    independent_origins = support_origins + contra_origins

    net = (support_score - contradiction_score) / total_weight if total_weight > 1e-9 else 0.0

    coverage_score = min(1.0, independent_origins / TARGET_ORIGINS)
    applied_penalty = max((p.value for p in signals.penalties), default=0.0)

    verdict, rule = _decide_claim_verdict(
        signals=signals,
        net=net,
        support_score=support_score,
        contradiction_score=contradiction_score,
        total_weight=total_weight,
        independent_origins=independent_origins,
        applied_penalty=applied_penalty,
    )

    confidence_score, band = _confidence(
        coverage_score=coverage_score,
        total_weight=total_weight,
        support_score=support_score,
        contradiction_score=contradiction_score,
        evidence=signals.evidence,
        verdict=verdict,
    )

    return ClaimScore(
        claim_id=signals.claim_id,
        verdict=verdict,
        confidence_band=band,
        confidence_score=confidence_score,
        support_score=support_score,
        contradiction_score=contradiction_score,
        coverage_score=coverage_score,
        net=net,
        independent_origins=independent_origins,
        total_weight=total_weight,
        applied_penalty=applied_penalty,
        penalties=signals.penalties,
        decision_rule=rule,
        evidence_weights=tuple(support_detail + contra_detail + other_detail),
    )


def _decide_claim_verdict(
    *,
    signals: ClaimSignals,
    net: float,
    support_score: float,
    contradiction_score: float,
    total_weight: float,
    independent_origins: int,
    applied_penalty: float,
) -> tuple[Verdict, int]:
    """The decision table from docs/SCORING.md. First match wins.

    Rule numbers are stored with each result so a verdict can be traced back to
    the exact branch that produced it.
    """
    # 1. Not enough evidence to say anything. This is the honest default, and it
    #    is emphatically not FALSE.
    if total_weight < MIN_EVIDENCE_WEIGHT or independent_origins == 0:
        return Verdict.UNVERIFIED, 1

    # 2. Opinions and predictions are not checkable against evidence.
    if signals.claim_type in (ClaimType.OPINION, ClaimType.PREDICTION):
        return Verdict.OPINION, 2

    # 3. Satire is a genre, not a lie.
    if signals.is_satirical_source:
        return Verdict.SATIRE, 3

    # 4. Strong support plus a large context penalty: the authentic-photo,
    #    false-caption case. This must never resolve to VERIFIED.
    if net >= NET_STRONG_SUPPORT and applied_penalty >= PENALTY_MISLEADING_THRESHOLD:
        return Verdict.MISLEADING, 4

    # 5. Strong support with a smaller penalty: core is right, specifics are off.
    if net >= NET_STRONG_SUPPORT and applied_penalty > 0:
        return Verdict.PARTLY_TRUE, 5

    # 6. Strong, independent, well-sourced support and no penalties.
    if (
        net >= NET_VERIFIED
        and independent_origins >= MIN_ORIGINS_FOR_VERIFIED
        and support_score >= MIN_SUPPORT_FOR_VERIFIED
    ):
        return Verdict.VERIFIED, 6

    # 7. Good support that falls short of the independence or mass bar.
    if net >= NET_LIKELY_TRUE:
        return Verdict.LIKELY_TRUE, 7

    # 8. Strong, independent contradiction.
    if (
        net <= NET_FALSE
        and independent_origins >= MIN_ORIGINS_FOR_FALSE
        and contradiction_score >= MIN_CONTRADICTION_FOR_FALSE
    ):
        return Verdict.FALSE, 8

    # 9. Meaningful contradiction that is not conclusive.
    if net <= NET_LIKELY_FALSE:
        return Verdict.LIKELY_FALSE, 9

    # 10. Genuinely mixed evidence on both sides.
    if support_score > 0 and contradiction_score > 0:
        return Verdict.PARTLY_TRUE, 10

    # 11. Anything else is not established.
    return Verdict.UNVERIFIED, 11


# ---------------------------------------------------------------------------
# Stage 6: confidence
# ---------------------------------------------------------------------------


def _confidence(
    *,
    coverage_score: float,
    total_weight: float,
    support_score: float,
    contradiction_score: float,
    evidence: tuple[EvidenceSignal, ...],
    verdict: Verdict,
) -> tuple[float, ConfidenceBand]:
    """Confidence reflects how much we know, not how extreme the verdict is."""
    mass = min(1.0, total_weight / 4.0)

    # Agreement: how one-sided the evidence is. Evenly split evidence means we
    # are less sure, whatever the verdict.
    if total_weight > 1e-9:
        minority = min(support_score, contradiction_score)
        agreement = 1.0 - (minority / total_weight)
    else:
        agreement = 0.0

    if evidence:
        best_source = max(
            source_factor(e.source_type, is_primary_source=e.is_primary_source) for e in evidence
        )
        # Normalize the source factor range onto 0-1.
        source_component = (best_source - SOURCE_FACTOR_MIN) / (
            SOURCE_FACTOR_MAX - SOURCE_FACTOR_MIN
        )
    else:
        source_component = 0.0

    raw = 0.40 * coverage_score + 0.25 * mass + 0.20 * agreement + 0.15 * source_component

    # An UNVERIFIED verdict from absent evidence is always low confidence: we are
    # confident about nothing, we simply did not find enough.
    if verdict is Verdict.UNVERIFIED:
        return raw, ConfidenceBand.LOW

    if raw >= CONFIDENCE_HIGH:
        return raw, ConfidenceBand.HIGH
    if raw >= CONFIDENCE_MEDIUM:
        return raw, ConfidenceBand.MEDIUM
    return raw, ConfidenceBand.LOW


# ---------------------------------------------------------------------------
# Stage 5: overall verdict
# ---------------------------------------------------------------------------


def score_overall(
    claim_scores: tuple[ClaimScore, ...],
    importances: dict[str, float],
    *,
    degraded: bool = False,
    degradation_reasons: tuple[str, ...] = (),
) -> OverallScore:
    """Aggregate claim verdicts into an overall verdict.

    Driven by the most important claims, not by counting minor ones: a single
    false load-bearing claim makes the whole item false even alongside several
    true incidental ones. That is how real misinformation is constructed.
    """
    if not claim_scores:
        return OverallScore(
            verdict=Verdict.UNVERIFIED,
            confidence_band=ConfidenceBand.LOW,
            confidence_score=0.0,
            claim_scores=(),
            decision_rule=0,
            degraded=degraded,
            degradation_reasons=degradation_reasons,
        )

    important = [
        c for c in claim_scores if importances.get(c.claim_id, 0.5) >= IMPORTANCE_THRESHOLD
    ]
    # With no explicitly important claim, every claim is treated as load-bearing
    # rather than silently ignoring all of them.
    considered = important or list(claim_scores)
    verdicts = {c.verdict for c in considered}

    verdict, rule = _decide_overall_verdict(considered, verdicts)

    # Overall confidence is the importance-weighted mean of claim confidences,
    # so an unresolved central claim lowers it more than an unresolved aside.
    total_importance = sum(max(0.01, importances.get(c.claim_id, 0.5)) for c in considered)
    confidence_score = (
        sum(c.confidence_score * max(0.01, importances.get(c.claim_id, 0.5)) for c in considered)
        / total_importance
    )

    if verdict is Verdict.UNVERIFIED:
        band = ConfidenceBand.LOW
    elif confidence_score >= CONFIDENCE_HIGH:
        band = ConfidenceBand.HIGH
    elif confidence_score >= CONFIDENCE_MEDIUM:
        band = ConfidenceBand.MEDIUM
    else:
        band = ConfidenceBand.LOW

    # A degraded run cannot claim high confidence: we know we did not look
    # everywhere we normally would.
    if degraded and band is ConfidenceBand.HIGH:
        band = ConfidenceBand.MEDIUM

    return OverallScore(
        verdict=verdict,
        confidence_band=band,
        confidence_score=confidence_score,
        claim_scores=claim_scores,
        decision_rule=rule,
        degraded=degraded,
        degradation_reasons=degradation_reasons,
    )


def _decide_overall_verdict(
    considered: list[ClaimScore], verdicts: set[Verdict]
) -> tuple[Verdict, int]:
    """Overall decision table from docs/SCORING.md. First match wins."""
    # 1-3. A false or misleading load-bearing claim decides the whole item.
    if Verdict.FALSE in verdicts:
        return Verdict.FALSE, 1
    if Verdict.MISLEADING in verdicts:
        return Verdict.MISLEADING, 2
    if Verdict.LIKELY_FALSE in verdicts:
        return Verdict.LIKELY_FALSE, 3

    # 8. Genre verdicts propagate when they cover every considered claim.
    if verdicts == {Verdict.SATIRE}:
        return Verdict.SATIRE, 8
    if verdicts == {Verdict.OPINION}:
        return Verdict.OPINION, 8

    substantive = verdicts - {Verdict.SATIRE, Verdict.OPINION}

    # 4. Any partly-true claim makes the whole item partly true.
    if Verdict.PARTLY_TRUE in substantive:
        return Verdict.PARTLY_TRUE, 4

    # 5-6. Everything checkable holds up.
    if substantive == {Verdict.VERIFIED}:
        return Verdict.VERIFIED, 5
    if substantive and substantive <= {Verdict.VERIFIED, Verdict.LIKELY_TRUE}:
        return Verdict.LIKELY_TRUE, 6

    # 7. Mostly unresolved. Mixing verified and unverified claims is partly true;
    #    a majority unverified is UNVERIFIED overall.
    unverified_count = sum(1 for c in considered if c.verdict is Verdict.UNVERIFIED)
    if unverified_count and unverified_count >= len(considered) / 2:
        return Verdict.UNVERIFIED, 7
    if substantive & {Verdict.VERIFIED, Verdict.LIKELY_TRUE} and Verdict.UNVERIFIED in substantive:
        return Verdict.PARTLY_TRUE, 4

    return Verdict.UNVERIFIED, 7
