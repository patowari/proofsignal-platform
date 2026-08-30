"""Deterministic scoring tests.

These encode the product's judgement calls. Several assert things that are easy
to get wrong and damaging when wrong:

- UNVERIFIED is not FALSE.
- Syndicated copies are one origin, not many.
- An authentic photo with a false caption is MISLEADING, not VERIFIED.
- One false load-bearing claim outweighs several true incidental ones.
"""

from __future__ import annotations

import pytest

from app.core.enums import (
    ClaimType,
    ConfidenceBand,
    EvidenceRelationship,
    PenaltyType,
    SourceType,
    Verdict,
)
from app.verification.scoring import (
    AppliedPenalty,
    ClaimSignals,
    EvidenceSignal,
    evidence_weight,
    score_claim,
    score_overall,
    source_factor,
)


def supporting(
    n: int = 1,
    *,
    relevance: float = 0.9,
    source_type: SourceType = SourceType.NEWS_ORGANIZATION,
    cluster: str | None = None,
    temporal: float = 1.0,
    directness: float = 1.0,
    primary: bool = False,
) -> tuple[EvidenceSignal, ...]:
    """n supporting items, each its own origin unless a cluster is given."""
    return tuple(
        EvidenceSignal(
            relationship=EvidenceRelationship.SUPPORTS,
            relevance=relevance,
            source_type=source_type,
            cluster_id=cluster,
            temporal_factor=temporal,
            directness=directness,
            is_primary_source=primary,
            evidence_id=f"s{i}",
        )
        for i in range(n)
    )


def contradicting(
    n: int = 1,
    *,
    relevance: float = 0.9,
    source_type: SourceType = SourceType.NEWS_ORGANIZATION,
    cluster: str | None = None,
) -> tuple[EvidenceSignal, ...]:
    return tuple(
        EvidenceSignal(
            relationship=EvidenceRelationship.CONTRADICTS,
            relevance=relevance,
            source_type=source_type,
            cluster_id=cluster,
            evidence_id=f"c{i}",
        )
        for i in range(n)
    )


class TestDeterminism:
    def test_identical_inputs_give_identical_output(self) -> None:
        """The whole point of not using an LLM here."""
        signals = ClaimSignals(claim_id="c1", evidence=supporting(3))
        first = score_claim(signals)
        for _ in range(20):
            assert score_claim(signals).to_breakdown() == first.to_breakdown()


class TestInsufficientEvidence:
    def test_no_evidence_is_unverified_not_false(self) -> None:
        """The single most important rule in the product."""
        result = score_claim(ClaimSignals(claim_id="c1", evidence=()))
        assert result.verdict is Verdict.UNVERIFIED
        assert result.verdict is not Verdict.FALSE
        assert result.decision_rule == 1

    def test_weak_evidence_is_unverified(self) -> None:
        weak = (
            EvidenceSignal(
                relationship=EvidenceRelationship.SUPPORTS,
                relevance=0.2,
                source_type=SourceType.UNKNOWN,
            ),
        )
        assert score_claim(ClaimSignals(claim_id="c1", evidence=weak)).verdict is Verdict.UNVERIFIED

    def test_unverified_is_always_low_confidence(self) -> None:
        result = score_claim(ClaimSignals(claim_id="c1", evidence=()))
        assert result.confidence_band is ConfidenceBand.LOW

    def test_neutral_evidence_alone_is_unverified(self) -> None:
        """Documents about the topic that do not address the assertion."""
        neutral = tuple(
            EvidenceSignal(
                relationship=EvidenceRelationship.NEUTRAL,
                relevance=0.9,
                source_type=SourceType.NEWS_AGENCY,
                evidence_id=f"n{i}",
            )
            for i in range(5)
        )
        assert (
            score_claim(ClaimSignals(claim_id="c1", evidence=neutral)).verdict is Verdict.UNVERIFIED
        )


class TestSourceIndependence:
    def test_syndicated_copies_count_as_one_origin(self) -> None:
        """Fifty reprints of one wire story are not fifty confirmations."""
        syndicated = supporting(50, cluster="wire-story-1")
        result = score_claim(ClaimSignals(claim_id="c1", evidence=syndicated))
        assert result.independent_origins == 1

    def test_syndication_cannot_reach_verified(self) -> None:
        """Volume must not substitute for independence."""
        result = score_claim(
            ClaimSignals(claim_id="c1", evidence=supporting(50, cluster="wire-story-1"))
        )
        assert result.verdict is not Verdict.VERIFIED

    def test_independent_sources_do_reach_verified(self) -> None:
        result = score_claim(
            ClaimSignals(
                claim_id="c1",
                evidence=(
                    *supporting(1, cluster="a", source_type=SourceType.NEWS_AGENCY),
                    *supporting(1, cluster="b", source_type=SourceType.OFFICIAL_GOVERNMENT),
                    *supporting(1, cluster="c", source_type=SourceType.NEWS_ORGANIZATION),
                ),
            )
        )
        assert result.verdict is Verdict.VERIFIED
        assert result.independent_origins == 3

    def test_clustered_weight_is_damped_not_dropped(self) -> None:
        """Copies still add a little: they show the story propagated."""
        one = score_claim(ClaimSignals(claim_id="c1", evidence=supporting(1, cluster="x")))
        five = score_claim(ClaimSignals(claim_id="c1", evidence=supporting(5, cluster="x")))
        assert five.support_score > one.support_score
        assert five.support_score < 2 * one.support_score


class TestMisleadingContext:
    def test_authentic_media_with_false_caption_is_misleading(self) -> None:
        """Real photo, wrong date. Everything checks out except the framing."""
        result = score_claim(
            ClaimSignals(
                claim_id="c1",
                evidence=(
                    *supporting(1, cluster="a"),
                    *supporting(1, cluster="b"),
                    *supporting(1, cluster="c"),
                ),
                penalties=(
                    AppliedPenalty(
                        PenaltyType.STALE_MEDIA,
                        0.40,
                        "image first appeared three years before the claimed event",
                    ),
                ),
            )
        )
        assert result.verdict is Verdict.MISLEADING
        assert result.decision_rule == 4

    def test_strong_support_with_penalty_never_verified(self) -> None:
        """Regression guard: a penalty must not be overridden by strong support."""
        for penalty_type, value in [
            (PenaltyType.DATE_MISMATCH, 0.35),
            (PenaltyType.LOCATION_MISMATCH, 0.35),
            (PenaltyType.NUMERIC_MISMATCH, 0.45),
            (PenaltyType.STALE_MEDIA, 0.40),
        ]:
            result = score_claim(
                ClaimSignals(
                    claim_id="c1",
                    evidence=supporting(6, source_type=SourceType.OFFICIAL_GOVERNMENT),
                    penalties=(AppliedPenalty(penalty_type, value, "mismatch"),),
                )
            )
            assert result.verdict is not Verdict.VERIFIED, penalty_type

    def test_small_penalty_gives_partly_true(self) -> None:
        """Exaggerating real research is PARTLY_TRUE, not FALSE."""
        result = score_claim(
            ClaimSignals(
                claim_id="c1",
                evidence=(*supporting(1, cluster="a"), *supporting(1, cluster="b")),
                penalties=(
                    AppliedPenalty(
                        PenaltyType.EXAGGERATION, 0.25, "evidence supports a weaker claim"
                    ),
                ),
            )
        )
        assert result.verdict is Verdict.PARTLY_TRUE
        assert result.decision_rule == 5


class TestContradiction:
    def test_strong_independent_contradiction_is_false(self) -> None:
        result = score_claim(
            ClaimSignals(
                claim_id="c1",
                evidence=(
                    *contradicting(1, cluster="a", source_type=SourceType.OFFICIAL_GOVERNMENT),
                    *contradicting(1, cluster="b", source_type=SourceType.NEWS_AGENCY),
                ),
            )
        )
        assert result.verdict is Verdict.FALSE
        assert result.decision_rule == 8

    def test_single_contradicting_source_is_not_false(self) -> None:
        """One source is not enough to call something false."""
        result = score_claim(ClaimSignals(claim_id="c1", evidence=contradicting(1, cluster="a")))
        assert result.verdict is not Verdict.FALSE

    def test_mixed_evidence_is_partly_true(self) -> None:
        result = score_claim(
            ClaimSignals(
                claim_id="c1",
                evidence=(
                    *supporting(1, cluster="a"),
                    *contradicting(1, cluster="b"),
                ),
            )
        )
        assert result.verdict in (Verdict.PARTLY_TRUE, Verdict.LIKELY_FALSE, Verdict.LIKELY_TRUE)

    def test_contradiction_outweighing_support_is_likely_false(self) -> None:
        result = score_claim(
            ClaimSignals(
                claim_id="c1",
                evidence=(
                    *supporting(1, cluster="a", relevance=0.4),
                    *contradicting(1, cluster="b", relevance=0.95),
                    *contradicting(1, cluster="c", relevance=0.95),
                ),
            )
        )
        assert result.verdict in (Verdict.LIKELY_FALSE, Verdict.FALSE)


class TestClaimTypes:
    def test_opinion_is_not_fact_checked(self) -> None:
        result = score_claim(
            ClaimSignals(claim_id="c1", claim_type=ClaimType.OPINION, evidence=supporting(3))
        )
        assert result.verdict is Verdict.OPINION

    def test_prediction_is_not_fact_checked(self) -> None:
        result = score_claim(
            ClaimSignals(claim_id="c1", claim_type=ClaimType.PREDICTION, evidence=supporting(3))
        )
        assert result.verdict is Verdict.OPINION

    def test_satire_is_a_genre_not_a_lie(self) -> None:
        result = score_claim(
            ClaimSignals(claim_id="c1", evidence=supporting(3), is_satirical_source=True)
        )
        assert result.verdict is Verdict.SATIRE
        assert result.verdict is not Verdict.FALSE


class TestSourceFactors:
    def test_primary_and_official_sources_weigh_more(self) -> None:
        assert source_factor(SourceType.OFFICIAL_GOVERNMENT) > source_factor(SourceType.BLOG)
        assert source_factor(SourceType.SCIENTIFIC_SOURCE) > source_factor(SourceType.SOCIAL_MEDIA)

    def test_source_factor_is_capped_both_ways(self) -> None:
        """No source type may dominate a verdict by itself."""
        highest = source_factor(SourceType.OFFICIAL_GOVERNMENT, is_primary_source=True)
        lowest = source_factor(SourceType.UNKNOWN)
        assert highest <= 1.30
        assert lowest >= 0.50
        assert highest / lowest < 3.0

    def test_primary_source_bonus_applies(self) -> None:
        assert source_factor(SourceType.NEWS_AGENCY, is_primary_source=True) > source_factor(
            SourceType.NEWS_AGENCY
        )

    def test_low_quality_source_cannot_alone_verify(self) -> None:
        """Three anonymous blogs are not three confirmations."""
        result = score_claim(
            ClaimSignals(
                claim_id="c1",
                evidence=(
                    *supporting(1, cluster="a", source_type=SourceType.UNKNOWN, relevance=0.6),
                    *supporting(1, cluster="b", source_type=SourceType.BLOG, relevance=0.6),
                    *supporting(1, cluster="c", source_type=SourceType.SOCIAL_MEDIA, relevance=0.6),
                ),
            )
        )
        assert result.verdict is not Verdict.VERIFIED


class TestEvidenceWeight:
    def test_temporal_mismatch_reduces_weight(self) -> None:
        fresh = evidence_weight(supporting(1, temporal=1.0)[0])
        stale = evidence_weight(supporting(1, temporal=0.4)[0])
        assert stale < fresh

    def test_indirect_evidence_weighs_less(self) -> None:
        direct = evidence_weight(supporting(1, directness=1.0)[0])
        topical = evidence_weight(supporting(1, directness=0.5)[0])
        assert topical < direct

    def test_weight_factors_are_bounded(self) -> None:
        """Out-of-range inputs must not produce runaway weights."""
        wild = EvidenceSignal(
            relationship=EvidenceRelationship.SUPPORTS,
            relevance=99.0,
            temporal_factor=-5.0,
            directness=42.0,
            source_type=SourceType.OFFICIAL_GOVERNMENT,
        )
        assert 0.0 <= evidence_weight(wild) <= 1.31


class TestConfidence:
    def test_more_independent_origins_raises_confidence(self) -> None:
        few = score_claim(ClaimSignals(claim_id="c1", evidence=supporting(1, cluster="a")))
        many = score_claim(
            ClaimSignals(
                claim_id="c1",
                evidence=(
                    *supporting(1, cluster="a"),
                    *supporting(1, cluster="b"),
                    *supporting(1, cluster="c"),
                ),
            )
        )
        assert many.confidence_score > few.confidence_score

    def test_conflicting_evidence_lowers_confidence(self) -> None:
        agreed = score_claim(
            ClaimSignals(
                claim_id="c1",
                evidence=(*supporting(1, cluster="a"), *supporting(1, cluster="b")),
            )
        )
        conflicted = score_claim(
            ClaimSignals(
                claim_id="c1",
                evidence=(*supporting(1, cluster="a"), *contradicting(1, cluster="b")),
            )
        )
        assert conflicted.confidence_score < agreed.confidence_score

    def test_no_fake_precision_in_band(self) -> None:
        result = score_claim(ClaimSignals(claim_id="c1", evidence=supporting(3)))
        assert result.confidence_band in (
            ConfidenceBand.LOW,
            ConfidenceBand.MEDIUM,
            ConfidenceBand.HIGH,
        )


class TestOverallVerdict:
    def test_one_false_important_claim_makes_the_item_false(self) -> None:
        """Real misinformation hides one false claim among true ones."""
        true_claim = score_claim(
            ClaimSignals(
                claim_id="true",
                evidence=(
                    *supporting(1, cluster="a", source_type=SourceType.NEWS_AGENCY),
                    *supporting(1, cluster="b", source_type=SourceType.OFFICIAL_GOVERNMENT),
                    *supporting(1, cluster="c"),
                ),
            )
        )
        false_claim = score_claim(
            ClaimSignals(
                claim_id="false",
                evidence=(
                    *contradicting(1, cluster="d", source_type=SourceType.OFFICIAL_GOVERNMENT),
                    *contradicting(1, cluster="e", source_type=SourceType.NEWS_AGENCY),
                ),
            )
        )
        assert true_claim.verdict is Verdict.VERIFIED
        assert false_claim.verdict is Verdict.FALSE

        overall = score_overall((true_claim, false_claim), {"true": 0.9, "false": 0.9})
        assert overall.verdict is Verdict.FALSE

    def test_unimportant_claims_do_not_drive_the_verdict(self) -> None:
        central = score_claim(
            ClaimSignals(
                claim_id="central",
                evidence=(
                    *supporting(1, cluster="a", source_type=SourceType.NEWS_AGENCY),
                    *supporting(1, cluster="b", source_type=SourceType.OFFICIAL_GOVERNMENT),
                    *supporting(1, cluster="c"),
                ),
            )
        )
        aside = score_claim(ClaimSignals(claim_id="aside", evidence=()))
        overall = score_overall((central, aside), {"central": 0.95, "aside": 0.2})
        assert overall.verdict is Verdict.VERIFIED

    def test_all_unverified_is_unverified(self) -> None:
        claims = tuple(score_claim(ClaimSignals(claim_id=f"c{i}", evidence=())) for i in range(3))
        overall = score_overall(claims, {f"c{i}": 0.8 for i in range(3)})
        assert overall.verdict is Verdict.UNVERIFIED
        assert overall.confidence_band is ConfidenceBand.LOW

    def test_no_claims_is_unverified(self) -> None:
        overall = score_overall((), {})
        assert overall.verdict is Verdict.UNVERIFIED

    def test_misleading_propagates(self) -> None:
        misleading = score_claim(
            ClaimSignals(
                claim_id="m",
                evidence=(*supporting(1, cluster="a"), *supporting(1, cluster="b")),
                penalties=(AppliedPenalty(PenaltyType.STALE_MEDIA, 0.40, "recycled image"),),
            )
        )
        overall = score_overall((misleading,), {"m": 0.9})
        assert overall.verdict is Verdict.MISLEADING

    def test_degraded_run_cannot_be_high_confidence(self) -> None:
        """We must not claim certainty when we know we did not look everywhere."""
        strong = score_claim(
            ClaimSignals(
                claim_id="c1",
                evidence=(
                    *supporting(1, cluster="a", source_type=SourceType.OFFICIAL_GOVERNMENT),
                    *supporting(1, cluster="b", source_type=SourceType.NEWS_AGENCY),
                    *supporting(1, cluster="c", source_type=SourceType.SCIENTIFIC_SOURCE),
                    *supporting(1, cluster="d", source_type=SourceType.NEWS_ORGANIZATION),
                ),
            )
        )
        clean = score_overall((strong,), {"c1": 0.9})
        degraded = score_overall(
            (strong,), {"c1": 0.9}, degraded=True, degradation_reasons=("ollama_unavailable",)
        )
        assert clean.confidence_band is ConfidenceBand.HIGH
        assert degraded.confidence_band is ConfidenceBand.MEDIUM


class TestBreakdownExplainability:
    def test_breakdown_explains_the_verdict(self) -> None:
        """A stored result must be re-explainable after the fact."""
        result = score_claim(
            ClaimSignals(
                claim_id="c1",
                evidence=(*supporting(1, cluster="a"), *contradicting(1, cluster="b")),
                penalties=(AppliedPenalty(PenaltyType.DATE_MISMATCH, 0.35, "date conflict"),),
            )
        )
        breakdown = result.to_breakdown()
        for key in (
            "scoring_version",
            "verdict",
            "support_score",
            "contradiction_score",
            "coverage_score",
            "net",
            "independent_origins",
            "decision_rule",
            "penalties",
            "evidence_weights",
        ):
            assert key in breakdown, f"missing {key}"
        assert breakdown["penalties"][0]["reason"] == "date conflict"

    def test_every_evidence_item_appears_in_the_breakdown(self) -> None:
        result = score_claim(
            ClaimSignals(
                claim_id="c1",
                evidence=(
                    *supporting(2, cluster="a"),
                    *contradicting(1, cluster="b"),
                    EvidenceSignal(
                        relationship=EvidenceRelationship.NEUTRAL, relevance=0.5, evidence_id="n0"
                    ),
                ),
            )
        )
        assert len(result.evidence_weights) == 4

    def test_overall_breakdown_is_serializable(self) -> None:
        import json

        claim = score_claim(ClaimSignals(claim_id="c1", evidence=supporting(2)))
        overall = score_overall((claim,), {"c1": 0.8})
        json.dumps(overall.to_breakdown())


class TestSingleGoodSource:
    """One directly-relevant passage from the reporting publisher is evidence.

    Regression guard for the 1.1.0 threshold change: before it, a claim could be
    confirmed verbatim by the outlet that reported it and still return
    UNVERIFIED, because total weight fell under MIN_EVIDENCE_WEIGHT.
    """

    def test_one_strong_source_is_not_unverified(self) -> None:
        result = score_claim(
            ClaimSignals(
                claim_id="c1",
                evidence=supporting(
                    1, cluster="a", relevance=0.64, source_type=SourceType.NEWS_ORGANIZATION
                ),
            )
        )
        assert result.verdict is not Verdict.UNVERIFIED
        assert result.verdict is Verdict.LIKELY_TRUE

    def test_one_source_still_cannot_reach_verified(self) -> None:
        """Lowering the floor must not weaken the strongest verdict."""
        result = score_claim(
            ClaimSignals(
                claim_id="c1",
                evidence=supporting(
                    1, cluster="a", relevance=1.0, source_type=SourceType.OFFICIAL_GOVERNMENT
                ),
            )
        )
        assert result.verdict is not Verdict.VERIFIED

    def test_one_source_still_cannot_reach_false(self) -> None:
        result = score_claim(
            ClaimSignals(
                claim_id="c1",
                evidence=contradicting(
                    1, cluster="a", relevance=1.0, source_type=SourceType.OFFICIAL_GOVERNMENT
                ),
            )
        )
        assert result.verdict is not Verdict.FALSE

    def test_trivial_evidence_is_still_unverified(self) -> None:
        """The floor still has to reject noise."""
        result = score_claim(
            ClaimSignals(
                claim_id="c1",
                evidence=supporting(
                    1, cluster="a", relevance=0.2, source_type=SourceType.UNKNOWN
                ),
            )
        )
        assert result.verdict is Verdict.UNVERIFIED


class TestRegressionFixtures:
    """Named misinformation patterns from docs/PRODUCT.md."""

    def test_wrong_number_pattern(self) -> None:
        """Claim says $50bn, evidence says $5bn: an order-of-magnitude error."""
        result = score_claim(
            ClaimSignals(
                claim_id="c1",
                evidence=(
                    *supporting(1, cluster="a", source_type=SourceType.OFFICIAL_GOVERNMENT),
                    *supporting(1, cluster="b", source_type=SourceType.NEWS_AGENCY),
                ),
                penalties=(
                    AppliedPenalty(
                        PenaltyType.NUMERIC_MISMATCH, 0.45, "claim says $50bn, evidence says $5bn"
                    ),
                ),
            )
        )
        assert result.verdict is Verdict.MISLEADING

    def test_breaking_news_with_no_coverage_is_unverified(self) -> None:
        """The correct answer for a claim nobody has reported yet."""
        result = score_claim(ClaimSignals(claim_id="c1", evidence=()))
        assert result.verdict is Verdict.UNVERIFIED
        assert result.confidence_band is ConfidenceBand.LOW

    @pytest.mark.parametrize("count", [1, 5, 20, 100])
    def test_duplication_never_reaches_verified(self, count: int) -> None:
        """However many copies exist, one origin is one origin."""
        result = score_claim(
            ClaimSignals(claim_id="c1", evidence=supporting(count, cluster="single-origin"))
        )
        assert result.independent_origins == 1
        assert result.verdict is not Verdict.VERIFIED
