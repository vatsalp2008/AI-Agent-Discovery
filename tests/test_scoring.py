import pytest

from scoring import relevance_score


def test_zero_distance_is_a_perfect_score():
    assert relevance_score(0.0) == 1.0


def test_score_decreases_as_distance_grows():
    scores = [relevance_score(d) for d in (0.0, 0.5, 1.0, 5.0, 20.0)]
    assert scores == sorted(scores, reverse=True)


def test_score_stays_within_bounds():
    for distance in (0, 0.3, 1, 42, 1e6):
        assert 0.0 <= relevance_score(distance) <= 1.0


def test_realistic_distances_stay_strictly_positive():
    for distance in (0, 0.3, 1, 42, 500):
        assert relevance_score(distance) > 0.0


def test_negative_distance_is_clamped():
    assert relevance_score(-3) == 1.0


@pytest.mark.parametrize("bad", [None, "abc", object(), float("nan")])
def test_unusable_values_score_zero(bad):
    assert relevance_score(bad) == 0.0
