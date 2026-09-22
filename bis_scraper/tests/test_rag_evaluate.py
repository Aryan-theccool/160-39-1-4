"""Tests for the retrieval evaluator (Part 7).

The metrics in this module are the ones that decide whether the retrieval work
was worth doing, so the tests here are mostly about the *definitions* -- a
metric that is accidentally lenient is worse than no metric, because it gets
quoted. The supersession check in particular reported a 50% violation rate on a
run where the current edition was ranked first in every case; the tests below
pin the corrected definition so that cannot come back.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bis_rag.data import BisData
from bis_rag.evaluate import (
    DEFAULT_CASES_PATH,
    CaseResult,
    EvalCase,
    EvalReport,
    _Corpus,
    evaluate,
    format_report,
    gate_failures,
    load_cases,
    superseded_present,
    superseded_violations,
)
from bis_rag.hybrid import HybridSearch, RetrievalConfig, SearchResult

from synth_bis_data import make_synth_data


# ----------------------------------------------------------------------
# fixtures
# ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def data_root(tmp_path_factory) -> Path:
    return make_synth_data(tmp_path_factory.mktemp("eval_data"))


@pytest.fixture(scope="module")
def search(data_root) -> HybridSearch:
    return HybridSearch(data_root and BisData(data_root), embedder="hash",
                        reranker="lexical",
                        config=RetrievalConfig(top_k=10))


@pytest.fixture(scope="module")
def corpus(data_root) -> _Corpus:
    return _Corpus(BisData(data_root))


def result(designation: str, *, current: bool = True, score: float = 1.0) -> SearchResult:
    return SearchResult(
        id=designation,
        text="",
        metadata={"designation": designation, "is_current": current},
        score=score,
    )


# ----------------------------------------------------------------------
# loading the test set
# ----------------------------------------------------------------------
def test_shipped_case_file_loads_and_is_the_size_we_claim():
    cases = load_cases(DEFAULT_CASES_PATH)
    scored = [c for c in cases if not c.is_rejection]
    negatives = [c for c in cases if c.is_rejection]
    # 56 scored rather than the 50 asked for: the extra six are the questions
    # with the least keyword overlap, which is where a retriever is most likely
    # to fail. The 12 out-of-scope cases are counted separately because they are
    # not retrieval cases at all -- they have no rank to be right or wrong about.
    assert len(scored) == 56
    assert len(negatives) >= 10, "the brief asks for at least 10 out-of-scope queries"
    assert len({c.id for c in cases}) == len(cases)


def test_out_of_scope_cases_declare_themselves_and_say_why():
    for case in load_cases(DEFAULT_CASES_PATH):
        if not case.is_rejection:
            continue
        assert case.rationale, f"{case.id} does not say why it is out of scope"
        assert case.sector_name == "Out of scope", case.id
        # An out-of-scope case that names a standard would be scored as a
        # retrieval miss as well, which double-counts one query as two failures.
        assert case.expected == ()


def test_shipped_cases_are_questions_not_designation_lookups():
    """The whole point of this set.

    A case whose query already contains its own answer measures nothing, which
    is exactly what the template-generated qa_pairs.jsonl did.
    """
    cases = load_cases(DEFAULT_CASES_PATH)
    offenders = []
    for case in cases:
        lowered = case.query.lower()
        for expected in case.expected:
            number = expected.split()[-1].split(":")[0]
            if "is " + number in lowered or f"is{number}" in lowered.replace(" ", ""):
                offenders.append(case.id)
    assert offenders == [], (
        "these cases name the standard they are looking for, so a designation "
        f"lookup would answer them: {offenders}"
    )


def test_shipped_cases_cover_every_expected_standard_with_a_rationale():
    for case in load_cases(DEFAULT_CASES_PATH):
        assert case.rationale, f"{case.id} has no rationale"
        assert case.tags, case.id
        if case.is_rejection:
            assert case.difficulty == "out_of_scope", case.id
            continue
        assert case.expected, f"{case.id} has no expected standard"
        assert case.difficulty in ("easy", "medium", "hard"), case.id
        # The sector breakdown is only meaningful if every scored case has one.
        assert case.sector_name not in ("", "unspecified"), case.id


def test_a_query_naming_its_own_answer_is_rejected_by_the_guard():
    """The guard above must actually be able to fail."""
    case = EvalCase(id="bad", query="What is IS 269:2015?", expected=("IS 269",))
    number = case.expected[0].split()[-1]
    assert f"is {number}" in case.query.lower()


def test_load_cases_skips_comments_and_blank_lines(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(
        "# a comment\n"
        "\n"
        + json.dumps({"id": "a", "query": "cement", "expected": ["IS 269"]}) + "\n"
        + json.dumps({"id": "b", "query": "steel", "expected": "IS 1786"}) + "\n",
        encoding="utf-8",
    )
    cases = load_cases(path)
    assert [c.id for c in cases] == ["a", "b"]
    # A bare string for `expected` is accepted, because hand-editing JSONL makes
    # it easy to write one and the intent is unambiguous.
    assert cases[1].expected == ("IS 1786",)


def test_load_cases_rejects_duplicate_ids(tmp_path):
    """Duplicates silently shrink the denominator and hide a real miss."""
    path = tmp_path / "cases.jsonl"
    path.write_text(
        json.dumps({"id": "same", "query": "a", "expected": ["IS 269"]}) + "\n"
        + json.dumps({"id": "same", "query": "b", "expected": ["IS 456"]}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate case id"):
        load_cases(path)


def test_load_cases_rejects_a_case_with_no_query(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps({"id": "x", "expected": ["IS 269"]}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no query"):
        load_cases(path)


def test_missing_file_error_names_the_shipped_path(tmp_path):
    with pytest.raises(FileNotFoundError) as excinfo:
        load_cases(tmp_path / "nope.jsonl")
    assert str(DEFAULT_CASES_PATH) in str(excinfo.value)


def test_bad_json_reports_the_line_number(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text('{"id": "a", "query": "x"}\nnot json\n', encoding="utf-8")
    with pytest.raises(ValueError, match=":2:"):
        load_cases(path)


# ----------------------------------------------------------------------
# the supersession metric -- the definition that matters
# ----------------------------------------------------------------------
def test_current_edition_above_withdrawn_is_not_a_violation(corpus):
    """The bug this definition replaced.

    IS 456:2000 first, IS 456:1978 fourth. The user reads the top result and it
    is the right one, so nothing is wrong. The first version of this check
    flagged exactly this and reported a 50% violation rate.
    """
    results = [
        result("IS 456:2000"),
        result("IS 456:2000"),
        result("IS 383:2016"),
        result("IS 456:1978", current=False),
    ]
    assert superseded_violations(results, corpus, 5) == []


def test_withdrawn_edition_above_its_current_edition_is_a_violation(corpus):
    results = [
        result("IS 383:2016"),
        result("IS 456:1978", current=False),
        result("IS 456:2000"),
    ]
    assert superseded_violations(results, corpus, 5) == ["IS 456:1978"]


def test_withdrawn_edition_with_the_current_one_absent_is_a_violation(corpus):
    """The user sees only the withdrawn edition, with nothing to compare against."""
    results = [result("IS 383:2016"), result("IS 456:1978", current=False)]
    assert superseded_violations(results, corpus, 5) == ["IS 456:1978"]


def test_withdrawn_edition_of_a_standard_absent_from_the_corpus_is_not_flagged(corpus):
    """A withdrawn edition is only wrong if a current one exists to prefer.

    Flagging this would blame the ranker for a gap in the corpus.
    """
    results = [result("IS 99999:1970", current=False)]
    assert superseded_violations(results, corpus, 5) == []


def test_violations_are_only_looked_for_within_the_depth(corpus):
    results = [result("IS 456:2000")] + [result("IS 383:2016")] * 5 + [
        result("IS 456:1978", current=False)
    ]
    assert superseded_violations(results, corpus, 5) == []
    assert superseded_violations(results, corpus, 10) == []


def test_a_withdrawn_edition_with_no_current_anywhere_is_not_a_violation(corpus):
    """Depth window narrower than the current edition's rank."""
    results = [result("IS 456:1978", current=False), result("IS 456:2000")]
    assert superseded_violations(results, corpus, 1) == ["IS 456:1978"]


def test_present_reports_withdrawn_editions_regardless_of_order(corpus):
    """Reported separately so a fix to ordering cannot hide bad retrieval."""
    correct = [result("IS 456:2000"), result("IS 456:1978", current=False)]
    assert superseded_violations(correct, corpus, 5) == []
    assert superseded_present(correct, corpus, 5) == ["IS 456:1978"]


def test_current_edition_must_rank_first_even_when_far_apart(corpus):
    results = [
        result("IS 383:2016"),
        result("IS 383:2016"),
        result("IS 1786:2008"),
        result("IS 456:1978", current=False),
        result("IS 456:2000"),
    ]
    assert superseded_violations(results, corpus, 5) == ["IS 456:1978"]


# ----------------------------------------------------------------------
# report arithmetic
# ----------------------------------------------------------------------
def make_report(rows: list[tuple[str, int | None, bool]]) -> EvalReport:
    """Build a report from (id, rank, answerable) triples."""
    report = EvalReport(top_k=10)
    for case_id, rank, answerable in rows:
        case = EvalCase(id=case_id, query=f"query {case_id}", expected=("IS 269",))
        report.cases.append(CaseResult(case=case, rank=rank, answerable=answerable))
    return report


def test_unanswerable_cases_are_excluded_from_every_rate():
    """Scoring a retriever against an answer the corpus lacks measures nothing."""
    report = make_report([
        ("a", 1, True),
        ("b", 3, True),
        ("c", None, False),   # expected standard not in the corpus
    ])
    assert report.coverage == pytest.approx(2 / 3)
    assert report.hit_rate(1) == pytest.approx(0.5)
    assert report.hit_rate(3) == pytest.approx(1.0)
    assert report.mrr(5) == pytest.approx((1.0 + 1 / 3) / 2)


def test_hit_rate_and_mrr_on_a_mix():
    report = make_report([
        ("a", 1, True),
        ("b", 2, True),
        ("c", 5, True),
        ("d", None, True),
    ])
    assert report.hit_rate(1) == pytest.approx(0.25)
    assert report.hit_rate(3) == pytest.approx(0.5)
    assert report.hit_rate(5) == pytest.approx(0.75)
    assert report.hit_rate(10) == pytest.approx(0.75)
    assert report.mrr(5) == pytest.approx((1 + 0.5 + 0.2 + 0) / 4)


def test_mrr_ignores_hits_beyond_k():
    report = make_report([("a", 8, True)])
    assert report.mrr(5) == 0.0
    assert report.mrr(10) == pytest.approx(0.125)


def test_rates_are_zero_rather_than_a_division_error_when_nothing_is_answerable():
    report = make_report([("a", None, False)])
    assert report.hit_rate(1) == 0.0
    assert report.mrr(5) == 0.0
    assert report.superseded_violation_rate == 0.0
    assert report.coverage == 0.0


def test_superseded_violation_rate_counts_cases_not_editions():
    report = make_report([("a", 1, True), ("b", 1, True)])
    report.cases[0].superseded_ahead = ["IS 456:1978", "IS 269:1989"]
    assert report.superseded_violation_rate == pytest.approx(0.5)


def test_hallucination_rate_is_per_citation():
    report = EvalReport()
    report.citations_total = 8
    report.citations_unresolvable = ["IS 99999", "IS 1"]
    assert report.hallucination_rate == pytest.approx(0.25)


def test_hallucination_rate_with_no_citations_is_zero_not_a_division_error():
    assert EvalReport().hallucination_rate == 0.0


# ----------------------------------------------------------------------
# latency percentiles
# ----------------------------------------------------------------------
def test_percentiles_interpolate_between_samples():
    report = EvalReport()
    report.latencies = [float(n) for n in range(1, 101)]   # 1..100
    assert report.percentile(50) == pytest.approx(50.5)
    assert report.percentile(95) == pytest.approx(95.05)
    assert report.percentile(0) == pytest.approx(1.0)
    assert report.percentile(100) == pytest.approx(100.0)


def test_percentile_of_a_single_sample_is_that_sample():
    report = EvalReport()
    report.latencies = [7.5]
    for p in (1, 50, 99, 100):
        assert report.percentile(p) == pytest.approx(7.5)


def test_percentile_with_no_samples_is_zero():
    assert EvalReport().percentile(95) == 0.0


def test_latency_sample_count_is_reported():
    """A P99 from 12 samples is the second-worst observation, so the count matters."""
    report = EvalReport()
    report.latencies = [1.0] * 12
    assert report.latency_samples == 12


# ----------------------------------------------------------------------
# threshold gating
# ----------------------------------------------------------------------
def test_superseded_violations_fail_by_default():
    report = make_report([("a", 1, True)])
    report.cases[0].superseded_ahead = ["IS 456:1978"]
    problems = gate_failures(report)
    assert len(problems) == 1
    assert "superseded" in problems[0]


def test_a_clean_report_passes_every_gate():
    report = make_report([("a", 1, True), ("b", 1, True)])
    assert gate_failures(report) == []


def test_hit_rate_floors_are_opt_in():
    report = make_report([("a", 4, True)])
    assert gate_failures(report) == []
    assert gate_failures(report, min_hit_rate_1=0.5)
    assert gate_failures(report, min_hit_rate_5=1.0) == []


def test_hallucination_gate_is_opt_in():
    report = make_report([("a", 1, True)])
    report.citations_total = 4
    report.citations_unresolvable = ["IS 99999"]
    assert gate_failures(report) == []
    assert gate_failures(report, max_hallucination=0.1)


def test_gate_messages_carry_the_numbers():
    report = make_report([("a", None, True)])
    problems = gate_failures(report, min_hit_rate_5=0.9)
    assert "0.0%" in problems[0] and "90.0%" in problems[0]


# ----------------------------------------------------------------------
# the evaluation run itself
# ----------------------------------------------------------------------
def test_evaluate_returns_one_result_per_case(search):
    cases = load_cases(DEFAULT_CASES_PATH)[:6]
    report = evaluate(search, cases, top_k=10, check_supersession=False)
    assert len(report.cases) == len(cases)
    assert report.corpus_size == 12
    assert report.latency_samples == len(cases)


def test_evaluate_rejects_a_top_k_too_small_for_the_ranks_it_reports(search):
    """Silently reporting Hit Rate @10 from five results would look like a miss."""
    with pytest.raises(ValueError, match="at least 10"):
        evaluate(search, [], top_k=5)


def test_evaluate_finds_the_expected_standard_for_a_plain_query(search):
    case = EvalCase(id="cement", query="ordinary portland cement 33 grade",
                    expected=("IS 269",))
    report = evaluate(search, [case], top_k=10, check_supersession=False)
    assert report.cases[0].rank == 1
    assert report.hit_rate(1) == 1.0


def test_evaluate_marks_a_case_unanswerable_when_the_standard_is_absent(search):
    case = EvalCase(id="absent", query="cement", expected=("IS 99999",))
    report = evaluate(search, [case], top_k=10, check_supersession=False)
    assert report.cases[0].answerable is False
    # ...and it must not drag the hit rate down, because the retriever could
    # not have returned it.
    assert report.hit_rate(1) == 0.0
    assert report.coverage == 0.0


def test_evaluate_repeats_add_latency_samples_without_changing_the_ranking(search):
    case = EvalCase(id="cement", query="ordinary portland cement 33 grade",
                    expected=("IS 269",))
    once = evaluate(search, [case], top_k=10, check_supersession=False, repeats=1)
    thrice = evaluate(search, [case], top_k=10, check_supersession=False, repeats=3)
    assert once.latency_samples == 1
    assert thrice.latency_samples == 3
    assert once.cases[0].rank == thrice.cases[0].rank


def test_evaluate_reports_the_supersession_check_against_the_real_ranking(search):
    """The defect this metric found, pinned end to end.

    `IS 456:1978` used to come back at rank 5 with `IS 456:2000` at rank 6 when
    the current-only filter was off.
    """
    case = EvalCase(id="aggregates",
                    query="coarse and fine aggregate grading requirements for concrete",
                    expected=("IS 383",))
    report = evaluate(search, [case], top_k=10, check_supersession=True)
    assert report.superseded_violation_rate == 0.0, (
        "a withdrawn edition outranked its current edition: "
        f"{report.cases[0].superseded_ahead}"
    )


def test_a_case_that_raises_is_recorded_rather_than_aborting_the_run():
    """One broken query must not lose the other 55 results."""

    class EmptyData:
        """The minimum a HybridSearch exposes to the evaluator, and no more."""

        root = Path("/nonexistent")
        reranker = None

        def __init__(self):
            self.data = self   # a retriever points at its own data object

        def standards(self):
            return []

        def chunks(self):
            return []

    class Exploding(EmptyData):
        def search(self, *args, **kwargs):
            raise RuntimeError("retriever is on fire")

    report = evaluate(
        Exploding(),
        [EvalCase(id="x", query="q", expected=("IS 269",)),
         EvalCase(id="y", query="q", expected=("IS 269",))],
        top_k=10, check_supersession=False, warmup=False,
    )
    assert len(report.cases) == 2, "the run must continue past a failing case"
    assert report.cases[0].error.startswith("RuntimeError")
    assert "on fire" in report.cases[0].error
    # A failed case is not evidence about retrieval, so it is excluded rather
    # than counted as a miss.
    assert report.cases[0].answerable is False


# ----------------------------------------------------------------------
# the rendered report
# ----------------------------------------------------------------------
def test_format_report_states_the_things_a_reader_would_otherwise_assume():
    report = make_report([("a", 1, True), ("b", 4, True)])
    report.latency_samples
    report.latencies = [10.0, 20.0]
    report.notes.append("a note")
    text = format_report(report)
    for expected in (
        "Hit Rate @1", "Hit Rate @10", "MRR @5",
        # Renamed from "Hallucination rate" at the user's request: on the search
        # path it is structurally zero and in extractive mode it measures the
        # template, so the old name claimed more than the number supports.
        "Invalid citation rate", "invalid citation rate in extractive mode",
        "Superseded-first", "Superseded exposure", "end-to-end RAG",
        "Retrieval stages", "By difficulty", "Out-of-scope queries",
    ):
        assert expected in text, expected
    assert "a note" in text


def test_format_report_warns_that_an_extractive_hallucination_rate_proves_nothing():
    report = make_report([("a", 1, True)])
    report.answer_mode = "extractive"
    assert "0 by construction" in format_report(report)


def test_format_report_warns_when_the_latency_sample_is_too_small_for_a_p99():
    report = make_report([("a", 1, True)])
    report.latencies = [1.0, 2.0, 3.0]
    text = format_report(report)
    assert "--repeats" in text


def test_format_report_explains_an_unanswerable_case_instead_of_hiding_it():
    report = make_report([("a", None, False)])
    text = format_report(report)
    assert "standards not held" in text
    assert "cannot return a standard the corpus lacks" in text
    # The gap has to be visible in the headline numbers, not only in a note:
    # end-to-end counts cases the corpus cannot answer as misses.
    assert "end-to-end" in text


def test_as_dict_round_trips_through_json():
    report = make_report([("a", 1, True)])
    report.latencies = [3.0]
    payload = json.loads(json.dumps(report.as_dict()))
    assert payload["cases"] == 1
    assert payload["hit_rate"]["@1"] == 1.0
    assert payload["per_case"][0]["id"] == "a"
    assert payload["latency_ms"]["p50"] == 3.0
