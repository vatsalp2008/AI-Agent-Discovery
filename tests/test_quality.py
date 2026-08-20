"""The retrieval quality report.

Everything here runs against a stub store rather than Ollama: the point of
these tests is the arithmetic and the parsing, and a real index would make
them slow, non-deterministic and dependent on which model is installed.
"""

import json
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

        assert "1 of 1 measured guards pass by less than" in report
        assert "+0.0010" in report and "Other" in report

    def test_a_comfortable_guard_is_not(self):
        report = self._report([{"query": "q", "rank": 1, "margin": 0.4,
                                "rival": "Other", "expected": ["Right"]}])

        assert "None of the measured guards is close." in report

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
        assert "0 of 1 measured guards pass by less than" in report
        assert "None of the measured guards is close." in report

    def test_a_guard_that_is_thin_but_passing_still_counts(self):
        report = quality.render(
            [{"category": "C", "agents": 1, "mrr": 0.5, "unfindable": 0}], [],
            [{"query": "q", "rank": 2, "margin": 0.001, "rival": "X",
              "expected": ["R"]}])

        assert "1 of 1 measured guards pass by less than" in report


class TestUnmeasuredIsNotClear:
    """"We could not tell" must not print as "every guard has room"."""

    def _report(self, guards):
        return quality.render(
            [{"category": "C", "agents": 1, "mrr": 0.9, "unfindable": 0}], [], guards)

    def test_guards_with_no_measurable_margin_leave_the_denominator(self):
        """Under `--limit 3` every margin is None, and the old wording turned
        a report that measured nothing into a clean bill of health."""
        report = self._report([{"query": "q", "rank": 1, "margin": None,
                                "rival": None, "expected": ["R"]}] * 3)

        assert "0 of 0 measured guards" in report
        assert "3 could not be measured" in report
        assert "every guard has room" not in report

    def test_a_mix_counts_only_what_was_measured(self):
        report = self._report([
            {"query": "a", "rank": 1, "margin": 0.4, "rival": "X", "expected": ["R"]},
            {"query": "b", "rank": 1, "margin": None, "rival": None, "expected": ["R"]},
        ])

        assert "0 of 1 measured guards" in report
        assert "1 could not be measured" in report

    def test_nothing_unmeasured_says_nothing_about_it(self):
        report = self._report([{"query": "a", "rank": 1, "margin": 0.4,
                                "rival": "X", "expected": ["R"]}])

        assert "could not be measured" not in report
        assert "None of the measured guards is close." in report


class TestReadingTheHistory:
    def test_no_history_yet_is_not_an_error(self, tmp_path):
        assert quality.read_history(tmp_path / "absent.jsonl") == []

    def test_runs_come_back_oldest_first(self, tmp_path):
        where = tmp_path / "h.jsonl"
        where.write_text('{"commit": "aaa"}\n{"commit": "bbb"}\n')

        assert [r["commit"] for r in quality.read_history(where)] == ["aaa", "bbb"]

    def test_a_damaged_line_is_skipped_not_fatal(self, tmp_path):
        """This is a record of measurements. Losing one is not worth failing
        the measurement being taken now."""
        where = tmp_path / "h.jsonl"
        where.write_text('{"commit": "aaa"}\nnot json\n\n{"commit": "ccc"}\n')

        assert [r["commit"] for r in quality.read_history(where)] == ["aaa", "ccc"]

    def test_a_line_that_is_not_an_object_is_skipped(self, tmp_path):
        where = tmp_path / "h.jsonl"
        where.write_text('[1, 2]\n{"commit": "aaa"}\n')

        assert [r["commit"] for r in quality.read_history(where)] == ["aaa"]


class TestRecording:
    def _rows(self):
        return [{"category": "Safety", "agents": 21, "mrr": 0.849, "unfindable": 0},
                {"category": "MLOps", "agents": 20, "mrr": 0.975, "unfindable": 0}]

    def test_a_run_appends_rather_than_replaces(self, tmp_path):
        where = tmp_path / "h.jsonl"
        quality.record(self._rows(), [], 303, 10, path=where)
        quality.record(self._rows(), [], 304, 10, path=where)

        assert len(quality.read_history(where)) == 2

    def test_it_keeps_what_a_later_comparison_needs(self, tmp_path):
        where = tmp_path / "h.jsonl"
        guards = [{"rank": 1, "margin": 0.4}, {"rank": 7, "margin": -0.1},
                  {"rank": 1, "margin": None}]
        run = quality.record(self._rows(), guards, 303, 10, path=where)

        assert run["agents"] == 303
        assert run["categories"]["Safety"] == 0.849
        assert run["guards"] == 3
        assert run["failing"] == 1
        assert run["thinnest"] == -0.1

    def test_no_measurable_margin_records_none_rather_than_zero(self, tmp_path):
        """Zero would read as "one guard is right on the edge"."""
        run = quality.record(self._rows(), [{"rank": 1, "margin": None}], 303,
                             10, path=tmp_path / "h.jsonl")

        assert run["thinnest"] is None


class TestMovement:
    def _now(self, **scores):
        return [{"category": c, "agents": 10, "mrr": m, "unfindable": 0}
                for c, m in scores.items()]

    def test_a_fall_past_the_threshold_is_reported(self):
        moves = quality.movement(self._now(Safety=0.849),
                                 {"categories": {"Safety": 0.921}})

        assert moves == [{"category": "Safety", "from": 0.921,
                          "to": 0.849, "delta": -0.072}]

    def test_a_rise_is_reported_too(self):
        """Only ever hearing bad news hides a wording fix working."""
        moves = quality.movement(self._now(Evaluation=0.917),
                                 {"categories": {"Evaluation": 0.855}})

        assert moves[0]["delta"] == 0.062

    def test_wobble_below_the_threshold_is_not(self):
        moves = quality.movement(self._now(MLOps=0.975),
                                 {"categories": {"MLOps": 0.967}})

        assert moves == []

    def test_the_biggest_fall_comes_first(self):
        moves = quality.movement(
            self._now(A=0.90, B=0.50, C=0.99),
            {"categories": {"A": 0.95, "B": 0.90, "C": 0.90}})

        assert [m["category"] for m in moves] == ["B", "A", "C"]

    def test_a_new_category_has_nothing_to_compare_against(self):
        assert quality.movement(self._now(Brand_New=0.5),
                                {"categories": {"Other": 0.9}}) == []

    def test_no_previous_run_reports_nothing(self):
        assert quality.movement(self._now(A=0.5), None) == []

    def test_a_non_numeric_stored_score_is_ignored(self):
        """The file is hand-editable and appended to by two callers."""
        assert quality.movement(self._now(A=0.5), {"categories": {"A": "?"}}) == []


class TestRenderingTheTrend:
    def _report(self, moves, previous=None):
        return quality.render(
            [{"category": "C", "agents": 1, "mrr": 0.9, "unfindable": 0}], [],
            [{"query": "q", "rank": 1, "margin": 0.4, "rival": "X",
              "expected": ["R"]}], moves=moves, previous=previous)

    def test_movement_is_shown_with_what_it_is_measured_against(self):
        report = self._report(
            [{"category": "Safety", "from": 0.921, "to": 0.849, "delta": -0.072}],
            previous={"commit": "d9dad34", "at": "2026-08-18T00:00:00+00:00",
                      "agents": 278})

        assert "Moved since the last run" in report
        assert "d9dad34" in report and "278 agents" in report
        assert "-0.072" in report

    def test_a_steady_run_says_nothing_about_movement(self):
        assert "Moved since the last run" not in self._report([])


class TestTheLimitIsPartOfTheMeasurement:
    """A run at `--limit 3` cannot see an agent ranked fourth, so every
    reciprocal is lower. Comparing that against a default run reports the
    setting as a change in the catalogue — an across-the-board rise that never
    happened."""

    def _rows(self):
        return [{"category": "Safety", "agents": 21, "mrr": 0.849, "unfindable": 0}]

    def test_the_limit_is_written_with_the_run(self, tmp_path):
        run = quality.record(self._rows(), [], 303, 3, path=tmp_path / "h.jsonl")

        assert run["limit"] == 3

    def test_a_different_limit_is_not_compared(self):
        moves = quality.movement(self._rows(),
                                 {"categories": {"Safety": 0.976}, "limit": 3},
                                 limit=10)

        assert moves == []

    def test_the_same_limit_is_compared(self):
        moves = quality.movement(self._rows(),
                                 {"categories": {"Safety": 0.976}, "limit": 10},
                                 limit=10)

        assert moves and moves[0]["delta"] == -0.127

    def test_a_run_recorded_before_the_field_existed_is_read_as_the_default(self):
        """Those runs were all taken at the default, so that is what an
        absent field means — not "comparable with anything you ask for".
        Read as None, a legacy line reported a 0.376 collapse in Safety that
        was entirely the effect of `--limit 3`."""
        legacy = {"categories": {"Safety": 0.976}}

        assert quality.movement(self._rows(), legacy,
                                limit=quality.DEFAULT_LIMIT)[0]["delta"] == -0.127
        assert quality.movement(self._rows(), legacy, limit=3) == []


class TestChoosingSomethingToCompareAgainst:
    def test_the_newest_run_at_the_same_depth_wins(self):
        """One `--record --limit 3` used to blind every later default run:
        it mismatched, movement returned nothing, and a comparable run sat
        one line above it unused."""
        history = [{"commit": "aaa", "limit": 10}, {"commit": "bbb", "limit": 3}]

        assert quality.comparable(history, 10)["commit"] == "aaa"
        assert quality.comparable(history, 3)["commit"] == "bbb"

    def test_a_legacy_line_counts_as_the_default(self):
        assert quality.comparable([{"commit": "old"}], quality.DEFAULT_LIMIT)

    def test_nothing_at_that_depth_is_none(self):
        assert quality.comparable([{"commit": "aaa", "limit": 10}], 3) is None

    def test_no_history_is_none(self):
        assert quality.comparable([], 10) is None


class TestSayingWhyThereIsNoComparison:
    def test_a_depth_with_no_baseline_says_so(self):
        """Going silent reads as a steady week, which is the same information
        loss the limit guard exists to prevent, only quieter."""
        report = quality.render(
            [{"category": "C", "agents": 1, "mrr": 0.9, "unfindable": 0}], [],
            [{"query": "q", "rank": 1, "margin": 0.4, "rival": "X", "expected": ["R"]}],
            moves=[], previous=None, limit=3,
            history=[{"commit": "aaa", "limit": 10}])

        assert "Nothing to compare against" in report
        assert "measured to 3" in report

    def test_a_first_ever_run_says_nothing_about_comparison(self):
        report = quality.render(
            [{"category": "C", "agents": 1, "mrr": 0.9, "unfindable": 0}], [],
            [{"query": "q", "rank": 1, "margin": 0.4, "rival": "X", "expected": ["R"]}],
            moves=[], previous=None, limit=10, history=[])

        assert "Nothing to compare against" not in report


class TestTheReportStatesItsOwnDepth:
    def _report(self, limit):
        return quality.render(
            [{"category": "C", "agents": 1, "mrr": 0.9, "unfindable": 1}],
            [{"name": "A", "category": "C", "rank": None, "reciprocal": 0.0,
              "beaten_by": ["B"]}],
            [], limit=limit)

    def test_the_column_counts_what_it_says_it_counts(self):
        """`--limit 3` produced a column headed "Not in top 10" counting
        agents outside the top three."""
        assert "Not in top 3 " in self._report(3)
        assert "Not in top 10 " in self._report(10)

    def test_a_missing_agent_is_described_at_the_right_depth(self):
        assert "outside the top 3" in self._report(3)


class TestMainThreadsTheLimitThrough:
    """Every other test here calls movement() and record() directly. These
    drive main, so the wiring is covered too — choosing the baseline, and
    recording the depth it was taken at.

    Two guards now stop a cross-depth comparison, and only one is load
    bearing here: `comparable()` picks a baseline at the right depth, after
    which `movement`'s own limit check has nothing left to reject. That
    second check is kept for direct callers, who pass whatever `previous`
    they like, and the tests above cover it at that level.
    """

    @pytest.fixture
    def wired(self, tmp_path, monkeypatch, capsys):
        import config

        history = tmp_path / "quality-history.jsonl"
        history.write_text(json.dumps(
            {"commit": "old", "limit": 10, "agents": 2,
             "categories": {"Infra": 0.90}}) + "\n")
        monkeypatch.setattr(quality, "history_path", lambda: history)

        agent = Agent("Ollama", "Infra", "run models locally")
        monkeypatch.setattr(quality, "load_agents", lambda: [agent])
        monkeypatch.setattr(quality, "read_guards", lambda path=None: [])
        # Rank 3, so the score depends on how deep the run looks.
        monkeypatch.setattr(quality, "VectorStore", lambda: FakeStore(
            {"run models locally": [("A", 0.9), ("B", 0.8), ("Ollama", 0.7)]}))
        monkeypatch.setattr(config, "REPO_ROOT", tmp_path)
        return history

    def test_a_shallower_run_is_not_compared_against_a_default_one(self, wired, capsys):
        assert quality.main(["--limit", "3"]) == 0
        report = capsys.readouterr().out

        assert "Nothing to compare against" in report
        assert "0.90" not in report, "it compared across depths"

    def test_a_matching_run_is_compared(self, wired, capsys):
        assert quality.main([]) == 0

        assert "Moved since the last run" in capsys.readouterr().out

    def test_the_recorded_limit_is_the_one_that_was_used(self, wired):
        quality.main(["--record", "--limit", "3"])

        assert quality.read_history(wired)[-1]["limit"] == 3
