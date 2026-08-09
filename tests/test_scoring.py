import math

import pytest

from scoring import relevance_score


def test_zero_distance_is_a_perfect_score():
    assert relevance_score(0.0) == 1.0


def test_score_decreases_as_distance_grows():
    scores = [relevance_score(d) for d in (0.0, 0.5, 1.0, 1.4, 2.0)]
    assert scores == sorted(scores, reverse=True)


def test_score_stays_within_bounds():
    for distance in (0, 0.3, 1, 1.414, 2, 42, 1e6):
        assert 0.0 <= relevance_score(distance) <= 1.0


def test_matches_cosine_similarity_for_unit_vectors():
    """The whole point: recover the metric the embedding model was trained on."""
    for cosine in (1.0, 0.9, 0.5, 0.0, -0.5):
        # For unit vectors, |a - b| = sqrt(2 - 2·cos)
        distance = math.sqrt(max(0.0, 2 - 2 * cosine))
        assert relevance_score(distance) == pytest.approx(max(0.0, cosine), abs=1e-4)


def test_orthogonal_vectors_score_a_half():
    assert relevance_score(math.sqrt(2)) == pytest.approx(0.0, abs=1e-4)


def test_opposite_vectors_are_floored_at_zero():
    assert relevance_score(2.0) == 0.0
    assert relevance_score(3.0) == 0.0


def test_real_world_distances_are_well_separated():
    """Measured against the seeded catalogue with nomic-embed-text.

    The previous 1/(1+d) mapping put all three of these in 0.46-0.70.
    """
    verbatim = relevance_score(0.423)
    good = relevance_score(0.772)
    unrelated = relevance_score(1.150)

    assert verbatim > 0.85
    assert 0.6 < good < 0.8
    assert unrelated < 0.4
    assert verbatim - unrelated > 0.5


def test_an_impossible_distance_scores_zero():
    """A negative L2 distance means the index is not the one we assume (an
    inner-product index, say). Scoring it 1.0 would rank the worst matches
    first; ranking it last is the safe failure."""
    assert relevance_score(-3) == 0.0
    assert relevance_score(-0.001) == 0.0


@pytest.mark.parametrize("bad", [float("nan"), None, "abc", [], {}])
def test_unusable_values_score_zero(bad):
    assert relevance_score(bad) == 0.0
