"""The retrieval quality report.

Everything here runs against a stub store rather than Ollama: the point of
these tests is the arithmetic and the parsing, and a real index would make
them slow, non-deterministic and dependent on which model is installed.
"""

import sys

import pytest

import config

# Resolved from config rather than a relative path: `sys.path.insert(0,
# "ai-agent-discovery")` is relative to the working directory, so collection
# failed outright whenever pytest ran from anywhere but the repo root.
sys.path.insert(0, str(config.PACKAGE_DIR))

import quality  # noqa: E402


class FakeStore:
    """Returns a canned ranking per query."""

    def __init__(self, rankings):
        self.rankings = rankings
        self.vector_store = object()

    def search(self, query, limit=10, **kwargs):
        return [{"name": name, "score": score}
                for name, score in self.rankings.get(query, [])][:limit]


class Agent:
    def __init__(self, name, category, use_case, description=""):
        self.name, self.category = name, category
        self.use_case, self.description = use_case, description


class TestRankOf:
    def test_reports_the_first_match_one_based(self):
        results = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
        assert quality.rank_of(results, {"B"}) == 2

    def test_reports_the_best_of_several_expected(self):
        results = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
        assert quality.rank_of(results, {"C", "B"}) == 2

    def test_none_when_nothing_matched(self):
        assert quality.rank_of([{"name": "A"}], {"Z"}) is None

    def test_none_on_no_results_at_all(self):
        assert quality.rank_of([], {"Z"}) is None


class TestSelfRetrieval:
    def test_an_agent_found_by_its_own_words_scores_one(self):
        store = FakeStore({"run models locally": [("Ollama", 0.9)]})
        rows = quality.self_retrieval(store, [Agent("Ollama", "Infra", "run models locally")])

        assert rows[0]["rank"] == 1
        assert rows[0]["reciprocal"] == 1.0

    def test_an_agent_that_never_appears_scores_zero(self):
        """Zero rather than a missing value: it has to average with the rest,
        and an unfindable agent is the strongest signal the report has."""
        store = FakeStore({"do a thing": [("Other", 0.9)]})
        rows = quality.self_retrieval(store, [Agent("Ghost", "Infra", "do a thing")])

        assert rows[0]["rank"] is None
        assert rows[0]["reciprocal"] == 0.0

    def test_it_records_what_outranked_the_agent(self):
        store = FakeStore({"q": [("A", 0.9), ("B", 0.8), ("Target", 0.7)]})
        rows = quality.self_retrieval(store, [Agent("Target", "Infra", "q")])

        assert rows[0]["rank"] == 3
        assert rows[0]["beaten_by"] == ["A", "B"]

    def test_it_falls_back_to_the_description(self):
        """Every catalogue entry has a use_case today, but the field is not
        required by the schema and an empty one would query the empty string,
        which matches arbitrarily."""
        store = FakeStore({"the long form": [("A", 0.9)]})
        rows = quality.self_retrieval(store, [Agent("A", "Infra", "", "the long form")])

        assert rows[0]["rank"] == 1


class TestByCategory:
    def test_it_averages_within_a_category_and_sorts_weakest_first(self):
        rows = [
            {"category": "Strong", "reciprocal": 1.0},
            {"category": "Strong", "reciprocal": 1.0},
            {"category": "Weak", "reciprocal": 0.5},
            {"category": "Weak", "reciprocal": 0.0},
        ]
        summary = quality.by_category(rows)

        assert [row["category"] for row in summary] == ["Weak", "Strong"]
        assert summary[0]["mrr"] == 0.25
        assert summary[0]["unfindable"] == 1
        assert summary[1]["mrr"] == 1.0


class TestReadingTheGuards:
    def test_it_reads_the_live_suite_rather_than_restating_it(self):
        """A second copy of the ground truth drifts from the first, and then
        this tool is reassuring about a suite it no longer describes."""
        cases = quality.read_guards()

        assert len(cases) > 50
        queries = {query for query, _ in cases}
        assert "fine tune a model on one GPU" in queries

    def test_it_skips_the_pairs_that_are_not_guards(self):
        """The same file holds typo-tolerance cases shaped ("cluade code",
        "Claude Code") — a string, not a set of acceptable answers. Reading
        those as guards would measure a query nobody asserted a top-3 on.
        """
        queries = {query for query, _ in quality.read_guards()}

        assert "cluade code" not in queries
        assert "langchian" not in queries

    def test_every_case_carries_at_least_one_expected_name(self):
        assert all(expected for _, expected in quality.read_guards())


class TestGuardMargins:
    def test_a_comfortable_guard_reports_a_wide_margin(self):
        store = FakeStore({"q": [("Right", 0.90), ("X", 0.50), ("Y", 0.40), ("Z", 0.30)]})
        row = quality.guard_margins(store, [("q", {"Right"})])[0]

        assert row["rank"] == 1
        assert row["margin"] == pytest.approx(0.60)

    def test_a_thin_guard_reports_the_gap_that_will_break_it(self):
        """`fine tune a model on one GPU` passed by 0.002 for weeks before an
        unrelated addition displaced it; this is the number that was missing.
        """
        store = FakeStore({"q": [("A", 0.610), ("B", 0.605), ("Right", 0.594),
                                 ("C", 0.5938)]})
        row = quality.guard_margins(store, [("q", {"Right"})])[0]

        assert row["rank"] == 3
        assert row["margin"] == pytest.approx(0.0002, abs=1e-6)
        assert row["rival"] == "C"

    def test_an_already_failing_guard_reports_its_rank(self):
        store = FakeStore({"q": [("A", 0.9), ("B", 0.8), ("C", 0.7), ("Right", 0.6)]})
        row = quality.guard_margins(store, [("q", {"Right"})])[0]

        assert row["rank"] == 4

    def test_a_query_returning_nothing_is_not_a_crash(self):
        row = quality.guard_margins(FakeStore({}), [("q", {"Right"})])[0]

        assert row["rank"] is None and row["margin"] is None


class TestRendering:
    def _report(self, guards):
        return quality.render([{"category": "C", "agents": 2, "mrr": 0.5,
                                "unfindable": 1}], [], guards)

    def test_a_thin_guard_is_listed(self):
        report = self._report([{"query": "q", "rank": 3, "margin": 0.001,
                                "rival": "Other", "expected": ["Right"]}])

        assert "1 of 1 pass by less than" in report
        assert "+0.0010" in report and "Other" in report

    def test_a_comfortable_guard_is_not(self):
        report = self._report([{"query": "q", "rank": 1, "margin": 0.4,
                                "rival": "Other", "expected": ["Right"]}])

        assert "None — every guard has room." in report

    def test_a_failing_guard_is_called_out_separately(self):
        """Distinct from a thin margin: one needs watching, the other needs
        fixing now, and the live suite is already red."""
        report = self._report([{"query": "q", "rank": 7, "margin": -0.2,
                                "rival": "Other", "expected": ["Right"]}])

        assert "1 failing now" in report

    def test_a_guard_with_no_results_does_not_break_the_table(self):
        report = self._report([{"query": "q", "rank": None, "margin": None,
                                "rival": None, "expected": ["Right"]}])

        assert "1 failing now" in report


class TestMarginsThatCannotBeMeasured:
    """A margin needs something that could actually take the place."""

    def test_too_few_rivals_reports_no_margin_rather_than_a_wrong_one(self):
        """Under `--limit 3` — the depth the live suite asserts on — there are
        never three non-expected results, so the old fallback measured the gap
        to the weakest visible one. That understates it, and understating is
        what makes a comfortable guard look thin.
        """
        store = FakeStore({"q": [("Right", 0.9), ("A", 0.5), ("B", 0.4)]})
        row = quality.guard_margins(store, [("q", {"Right"})], limit=3)[0]

        assert row["rank"] == 1
        assert row["margin"] is None
        assert row["rival"] is None

    def test_three_rivals_is_enough_to_measure(self):
        store = FakeStore({"q": [("Right", 0.9), ("A", 0.5), ("B", 0.4), ("C", 0.3)]})
        row = quality.guard_margins(store, [("q", {"Right"})])[0]

        assert row["rival"] == "C"
        assert row["margin"] == pytest.approx(0.6)


class TestFailingIsNotThin:
    def test_a_failing_guard_is_not_also_counted_as_passing_narrowly(self):
        """It was reported twice — once as failing, once as "passes by
        -0.2", which is not a thing a guard can do."""
        report = quality.render(
            [{"category": "C", "agents": 1, "mrr": 0.5, "unfindable": 0}], [],
            [{"query": "q", "rank": 7, "margin": -0.2, "rival": "X",
              "expected": ["R"]}])

        assert "1 failing now" in report
        assert "0 of 1 pass by less than" in report
        assert "None — every guard has room." in report

    def test_a_guard_that_is_thin_but_passing_still_counts(self):
        report = quality.render(
            [{"category": "C", "agents": 1, "mrr": 0.5, "unfindable": 0}], [],
            [{"query": "q", "rank": 2, "margin": 0.001, "rival": "X",
              "expected": ["R"]}])

        assert "1 of 1 pass by less than" in report
