"""Property-based tests.

Example tests pin the cases someone thought of. These assert the invariants
that must hold for *every* input — which is where the awkward values live:
NaN, infinity, the exact boundaries, and unicode nobody would type by hand.
"""

import math

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

import admin
from scoring import relevance_score

# These run on every commit, so keep them quick.
FAST = settings(max_examples=200, deadline=None)


class TestRelevanceScore:
    @FAST
    @given(st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False))
    def test_always_within_zero_and_one(self, distance):
        assert 0.0 <= relevance_score(distance) <= 1.0

    @FAST
    @given(st.floats(min_value=0, max_value=2, allow_nan=False, allow_infinity=False),
           st.floats(min_value=0, max_value=2, allow_nan=False, allow_infinity=False))
    def test_never_increases_with_distance(self, a, b):
        """Ranking depends on this, whatever the model emits."""
        assume(abs(a - b) > 1e-6)
        closer, further = min(a, b), max(a, b)
        assert relevance_score(closer) >= relevance_score(further)

    @FAST
    @given(st.floats(allow_nan=True, allow_infinity=True))
    def test_never_raises_on_any_float(self, distance):
        score = relevance_score(distance)
        assert 0.0 <= score <= 1.0
        assert not math.isnan(score)

    @FAST
    @given(st.one_of(st.none(), st.text(), st.lists(st.integers()), st.booleans()))
    def test_survives_non_numeric_input(self, value):
        assert 0.0 <= relevance_score(value) <= 1.0

    def test_known_anchors(self):
        """The values quoted in the module docstring."""
        assert relevance_score(0.0) == 1.0
        assert relevance_score(2.0) == 0.0
        assert relevance_score(0.42) == pytest.approx(0.91, abs=0.01)
        assert relevance_score(1.15) == pytest.approx(0.34, abs=0.01)

    @FAST
    @given(st.floats(min_value=2.0, max_value=1e6, allow_nan=False, allow_infinity=False))
    def test_beyond_orthogonal_floors_at_zero(self, distance):
        assert relevance_score(distance) == 0.0

    @FAST
    @given(st.floats(min_value=-1e6, max_value=-0.001, allow_nan=False, allow_infinity=False))
    def test_an_impossible_distance_scores_zero_not_one(self, distance):
        """A negative L2 distance means the index is not what we assume.

        Clamping to zero would score it a perfect match and float the worst
        results to the top; ranking it last is the safe failure.
        """
        assert relevance_score(distance) == 0.0


class TestAgentValidation:
    """admin.validate is the gate on everything written to the catalogue."""

    def record(self, **overrides):
        base = {
            "name": "Agent", "description": "Does a thing.", "category": "Automation",
            "tech_stack": [], "github_stars": 0, "url": "", "use_case": "",
        }
        base.update(overrides)
        return base

    @FAST
    @given(st.text(min_size=1).filter(lambda s: s.strip()))
    def test_any_non_blank_name_is_accepted(self, name):
        cleaned = admin.validate(self.record(name=name), [])
        assert cleaned["name"] == name.strip()

    @FAST
    @given(st.text().filter(lambda s: not s.strip()))
    def test_blank_names_are_always_rejected(self, name):
        with pytest.raises(admin.AdminError):
            admin.validate(self.record(name=name), [])

    @FAST
    @given(st.integers(min_value=0, max_value=10**9))
    def test_any_non_negative_star_count_is_accepted(self, stars):
        assert admin.validate(self.record(github_stars=stars), [])["github_stars"] == stars

    @FAST
    @given(st.integers(max_value=-1))
    def test_negative_star_counts_are_always_rejected(self, stars):
        with pytest.raises(admin.AdminError):
            admin.validate(self.record(github_stars=stars), [])

    @FAST
    @given(st.lists(st.text(min_size=1, max_size=admin.MAX_TECH_LENGTH)
                    .filter(lambda s: s.strip() and "," not in s),
                    max_size=admin.MAX_TECH_STACK))
    def test_comma_free_stacks_round_trip(self, stack):
        cleaned = admin.validate(self.record(tech_stack=stack), [])
        assert cleaned["tech_stack"] == [t.strip() for t in stack if t.strip()]

    @FAST
    @given(st.text(min_size=admin.MAX_TECH_LENGTH + 1).filter(lambda s: "," not in s))
    def test_an_overlong_technology_is_always_rejected(self, tech):
        with pytest.raises(admin.AdminError, match="at most"):
            admin.validate(self.record(tech_stack=[tech]), [])

    @FAST
    @given(st.text(min_size=1, max_size=200))
    def test_a_name_is_accepted_exactly_when_it_fits(self, name):
        """The length check runs on the stripped value, so whitespace must
        not push an otherwise-valid name over the limit."""
        fits = 0 < len(name.strip()) <= admin.FIELD_LIMITS["name"]
        if fits:
            assert admin.validate(self.record(name=name), [])["name"] == name.strip()
        else:
            with pytest.raises(admin.AdminError):
                admin.validate(self.record(name=name), [])

    @FAST
    @given(st.lists(st.text(min_size=1).map(lambda s: s + ","), min_size=1, max_size=4))
    def test_any_comma_in_a_stack_entry_is_rejected(self, stack):
        """stack is stored comma-joined, so a comma would split the entry."""
        with pytest.raises(admin.AdminError, match="comma"):
            admin.validate(self.record(tech_stack=stack), [])

    @FAST
    @given(st.text(min_size=1).filter(lambda s: not s.strip().startswith(("http://", "https://"))
                                      and s.strip()))
    def test_non_http_urls_are_always_rejected(self, url):
        with pytest.raises(admin.AdminError, match="http"):
            admin.validate(self.record(url=url), [])

    @FAST
    @given(st.text(min_size=1, max_size=40).filter(lambda s: s.strip()))
    def test_a_validated_record_never_contains_unknown_fields(self, name):
        cleaned = admin.validate(self.record(name=name), [])
        assert set(cleaned) <= set(admin.EDITABLE_FIELDS)

    @FAST
    @given(st.text(min_size=1, max_size=30).filter(lambda s: s.strip()))
    def test_validation_is_idempotent(self, name):
        """Re-validating a cleaned record must not change it again."""
        once = admin.validate(self.record(name=name), [])
        assert admin.validate(once, []) == once

    @FAST
    @given(st.text(min_size=1, max_size=30).filter(lambda s: s.strip()))
    def test_a_name_always_conflicts_with_itself(self, name):
        existing = [{"name": name.strip()}]
        with pytest.raises(admin.AdminError):
            admin.validate(self.record(name=name), existing)
