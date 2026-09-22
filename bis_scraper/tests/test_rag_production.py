"""Tests for the production-validation pass: provenance, year filters, modes.

Four things the brief asked to be verifiable rather than asserted in prose:

* a fixture cannot pass as the real corpus (and says so loudly);
* a year filter works the same way in all three retrievers;
* superseded editions obey the recommender's policy, in both directions;
* out-of-scope queries are scored separately from the ranking metrics.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from bis_rag.data import BisData
from bis_rag.doctor import (
    MIN_PRODUCTION_STANDARDS,
    FixtureDataError,
    doctor_payload,
    format_doctor,
    inspect_corpus,
    inspect_provenance,
    inspect_store,
    require_real_corpus,
)
from bis_rag.evaluate import (
    ABLATION_CONFIGS,
    EvalCase,
    EvalReport,
    ablation_rows,
    gate_failures,
)
from bis_rag.hybrid import HybridSearch, RetrievalConfig
from bis_rag.vectorstore import _matches

sys.path.insert(0, str(Path(__file__).parent))


# ----------------------------------------------------------------------
# fixtures
# ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def fixture_root(tmp_path_factory) -> Path:
    from synth_bis_data import make_synth_data

    root = tmp_path_factory.mktemp("production_data")
    make_synth_data(root / "bis_data")
    return root / "bis_data"


@pytest.fixture(scope="module")
def data(fixture_root) -> BisData:
    return BisData(fixture_root)


@pytest.fixture(scope="module")
def store(data, tmp_path_factory) -> Path:
    from bis_rag.build_vector_store import BuildConfig, build

    path = tmp_path_factory.mktemp("production_store") / "store"
    build(BuildConfig(data_dir=data.root, store_dir=path, backend="json",
                      embedder="hash", batch_size=8, verify=False))
    return path


@pytest.fixture(scope="module")
def search(data, store) -> HybridSearch:
    return HybridSearch(data, store_dir=store, embedder="hash",
                        config=RetrievalConfig(top_k=10), reranker="lexical")


# ----------------------------------------------------------------------
# 1. provenance: a fixture must not pass as the real corpus
# ----------------------------------------------------------------------
def test_the_generator_writes_a_marker_so_a_fixture_can_identify_itself(fixture_root):
    marker = fixture_root / ".synthetic_fixture.json"
    assert marker.exists()
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["generator"] == "tests/synth_bis_data.py"
    assert payload["standards"] == 12


def test_provenance_flags_the_fixture_and_says_it_is_not_certifiable(data):
    facts = inspect_provenance(data)
    assert facts.is_fixture is True
    assert facts.kind == "synthetic fixture"
    assert facts.certifiable is False
    assert "fixture" in facts.warning().lower()
    assert facts.as_dict()["certifiable_as_production"] is False


@pytest.fixture(scope="module")
def unmarked_corpus(tmp_path_factory, fixture_root) -> BisData:
    """The same data with the marker removed: what a scraped corpus looks like."""
    real = tmp_path_factory.mktemp("unmarked") / "bis_data"
    real.mkdir()
    for source in fixture_root.rglob("*"):
        if source.is_file() and source.name != ".synthetic_fixture.json":
            target = real / source.relative_to(fixture_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    return BisData(real)


def test_a_corpus_without_a_marker_is_not_called_a_fixture(unmarked_corpus):
    facts = inspect_provenance(unmarked_corpus)
    assert facts.is_fixture is False
    assert facts.marker is None


def test_a_corpus_without_a_marker_but_too_small_is_still_not_certifiable(unmarked_corpus):
    """The backstop for an old fixture or a partial scrape.

    Certification needs both facts, not one: no marker, *and* a plausible size.
    Twelve standards is not the corpus, however it got that way.
    """
    facts = inspect_provenance(unmarked_corpus)
    assert facts.suspiciously_small is True
    assert facts.kind == "unverified small corpus"
    assert facts.certifiable is False
    with pytest.raises(FixtureDataError) as excinfo:
        require_real_corpus(unmarked_corpus, what="this evaluation")
    message = str(excinfo.value)
    assert str(MIN_PRODUCTION_STANDARDS) in message
    assert "below" in message


def test_a_large_marker_less_corpus_is_certifiable(unmarked_corpus):
    facts = require_real_corpus(unmarked_corpus, what="this evaluation",
                                standards=MIN_PRODUCTION_STANDARDS)
    assert facts.certifiable is True
    assert facts.kind == "real corpus"


def test_require_real_corpus_refuses_a_fixture_and_says_what_to_do(data):
    with pytest.raises(FixtureDataError) as excinfo:
        require_real_corpus(data, what="this evaluation")
    message = str(excinfo.value)
    assert "fixture" in message.lower()
    assert "--data-dir" in message, "a refusal must name the way out"
    assert "197" in message, "and the corpus it expected instead"
    assert "--production" in message, "and how to report fixture numbers instead"


def test_require_real_corpus_can_be_told_to_allow_a_fixture(data):
    facts = require_real_corpus(data, what="a test run", allow_fixture=True)
    assert facts.is_fixture is True


def test_doctor_reports_every_field_the_brief_asks_for(data, store):
    payload = doctor_payload(inspect_corpus(data), inspect_store(store),
                            inspect_provenance(data), embedder="hash")
    assert payload["data_dir"] and payload["store_dir"]
    assert payload["corpus"]["standards"] == 12
    assert payload["corpus"]["chunks"] > 0
    assert payload["vector_store"]["backend"] == "json"
    assert payload["vector_store"]["embedder"]
    assert {c["name"] for c in payload["vector_store"]["collections"]} == {
        "bis_chunks", "bis_standards"}
    assert all(c["count"] is not None for c in payload["vector_store"]["collections"])
    # It survives a JSON round trip, so the artifact and the terminal agree.
    assert json.loads(json.dumps(payload))["corpus"]["standards"] == 12


def test_doctor_prints_the_fixture_banner_where_it_cannot_be_missed(data, store):
    text = format_doctor(doctor_payload(inspect_corpus(data), inspect_store(store),
                                       inspect_provenance(data), embedder="hash"))
    assert "SYNTHETIC FIXTURE" in text
    assert "NOT PRODUCTION DATA" in text


def test_the_store_block_carries_its_own_path(tmp_path):
    """`format_doctor` reads `store["path"]`; the payload has to have one.

    It did not, and the crash landed in the *missing store* branch -- the shape
    a first run has -- so `doctor` raised KeyError exactly when a user most
    needed it to explain what was wrong.
    """
    payload = doctor_payload(inspect_corpus(BisData(tmp_path)),
                             inspect_store(tmp_path / "no_such_store"),
                             inspect_provenance(BisData(tmp_path)))
    assert payload["vector_store"]["path"].endswith("no_such_store")
    text = format_doctor(payload)
    assert "does not exist" in text and "bis-rag build" in text


def test_doctor_exits_non_zero_when_there_is_no_corpus(tmp_path, capsys):
    """Absence of a fixture is not the presence of data.

    Doctor returned 0 while printing "data directory does not exist", so a CI
    step (`bis-rag doctor && ...`) sailed past a missing corpus. Worse, the
    banner read PROVENANCE: REAL CORPUS for a directory that was not there.
    """
    from bis_rag.cli import main

    empty = tmp_path / "empty"
    code = main(["doctor", "--data-dir", str(empty),
                 "--store-dir", str(empty / "store")])
    out = capsys.readouterr().out
    assert code == 2
    assert "NO CORPUS" in out
    assert "REAL CORPUS" not in out


def test_doctor_exits_zero_for_a_fixture_because_it_is_legitimate_to_inspect(data, store):
    """A fixture is a warning, not a failure -- `--production` is where it bites."""
    from bis_rag.cli import main

    code = main(["doctor", "--data-dir", str(data.root), "--store-dir", str(store), "--json"])
    assert code == 0


# ----------------------------------------------------------------------
# 2. year metadata: real years, and never a sentinel
# ----------------------------------------------------------------------
def _yeared_queries(**kwargs):
    from bis_rag.query_processor import Intent, ProcessedQuery

    return ProcessedQuery(raw="cement", normalized="cement",
                          intent=Intent.TOPIC_SEARCH, **kwargs)


def test_an_unknown_year_matches_neither_a_minimum_nor_a_maximum():
    """The bug the sentinel caused, stated as the invariant it violated.

    `year: -1` failed `$gte 2000` (silently losing a retriever from every
    "standards since 2000" query) and *passed* `$lte 1990` (offering a 2015
    standard as a 1980s edition). Unknown must fail both.
    """
    unknown = {"year": None}
    assert _matches(unknown, {"year": {"$gte": 2000}}) is False
    assert _matches(unknown, {"year": {"$lte": 1990}}) is False
    assert _matches(unknown, {"year": 2015}) is False
    # And the old sentinel shows why this mattered.
    assert _matches({"year": -1}, {"year": {"$lte": 1990}}) is True


def test_the_tfidf_index_records_the_real_year(data):
    index = data.tfidf_index()
    assert index is not None
    years = {doc["designation"]: doc.get("year") for doc in index.docs}
    assert years["IS 269:2015"] == 2015
    assert years["IS 269:1989"] == 1989
    assert all(isinstance(y, int) for y in years.values())


def test_tfidf_filters_by_year_range(data, search):
    processed = _yeared_queries(year_from=2010)
    hits = search._tfidf(processed, 10, processed.where())
    assert hits, "a year filter must not empty the TF-IDF leg"
    assert all(h.metadata["year"] >= 2010 for h in hits)


def test_bm25_filters_by_year_range(data, search):
    processed = _yeared_queries(year_from=2010)
    hits = search._bm25("standards", processed, 10, processed.where())
    assert hits
    assert all(h.metadata["year"] >= 2010 for h in hits)


def test_dense_filters_by_year_range(data, search):
    processed = _yeared_queries(year_from=2010)
    hits = search._dense("standards", processed, 10, processed.where())
    assert hits
    assert all(h.metadata["year"] >= 2010 for h in hits)


def test_all_three_retrievers_agree_on_a_year_exclusion(data, search):
    """The independent check the brief asked for: same filter, same verdict."""
    processed = _yeared_queries(year_to=1990)
    processed.current_only = False          # the 1989 edition is superseded
    where = processed.where()
    for name, hits in (
        ("tfidf", search._tfidf(processed, 10, where)),
        ("bm25", search._bm25("standards", processed, 10, where)),
        ("dense", search._dense("standards", processed, 10, where)),
    ):
        assert hits, f"{name} returned nothing for a year-bounded query"
        offenders = [h.designation for h in hits if h.metadata["year"] > 1990]
        assert offenders == [], f"{name} ignored the year ceiling: {offenders}"


def test_an_unknown_year_candidate_is_excluded_from_a_filtered_query(search):
    from bis_rag.hybrid import Candidate

    candidate = Candidate(id="x", text="cement", metadata={"year": None},
                          score=1.0, retriever="tfidf:standards", rank=1)
    assert _matches(candidate.metadata, {"year": {"$gte": 2000}}) is False


# ----------------------------------------------------------------------
# 3. supersession policy
# ----------------------------------------------------------------------
def test_recommendation_mode_offers_no_withdrawn_edition(search):
    response = search.search("ordinary portland cement", top_k=10, mode="recommend")
    assert response.mode == "recommend"
    assert [r.designation for r in response.results if not r.is_current] == []


def test_recommendation_mode_returns_withheld_editions_separately_with_replacement(search):
    """Held out of the ranking, not hidden.

    A user about to specify a product is better served by "IS 269:1989, replaced
    by IS 269:2015" than by silence -- provided the replacement is named, which
    is what makes the exposure acceptable at all.
    """
    processed = search.process("ordinary portland cement")
    processed.current_only = False
    response = search.search(processed, top_k=10, mode="recommend")
    assert response.results, "the current edition must still be recommended"
    assert all(r.is_current for r in response.results)
    if response.superseded:
        for item in response.superseded:
            assert item.metadata.get("superseded_by"), (
                f"{item.designation} was exposed without naming its replacement")


def test_history_mode_still_leads_with_the_old_edition(search):
    """The exception that keeps the policy from breaking the lookup it protects."""
    response = search.search("has IS 269:1989 been superseded?", top_k=10)
    assert response.mode == "history"
    assert response.results


def test_search_mode_never_ranks_a_withdrawn_edition_above_its_replacement(search):
    processed = search.process("ordinary portland cement")
    processed.current_only = False
    response = search.search(processed, top_k=10, mode="search")
    from bis_rag.evaluate import _Corpus, superseded_violations

    corpus = _Corpus(search.data)
    assert superseded_violations(response.results, corpus, 10) == []


def test_an_unknown_mode_is_rejected_rather_than_silently_defaulted(search):
    with pytest.raises(ValueError, match="unknown search mode"):
        search.search("cement", mode="recommendation")


def test_a_withdrawn_result_serialises_the_name_of_its_replacement(search):
    """The policy promises replacement metadata; a promise at object level that
    disappears on the way to JSON is not metadata a client can act on.

    This was a real defect: `with_replacement_metadata` stamped the field and
    `SearchResult.as_dict` did not emit it, so the API -- the only place a
    person ever sees this -- reported `is_current: false` and nothing else.
    """
    response = search.search("IS 269:1989", top_k=5)
    payload = response.as_dict()
    withdrawn = [row for row in payload["results"] if not row["is_current"]]
    assert withdrawn, "an explicitly-named old edition must still be found"
    for row in withdrawn:
        assert row["superseded_by"], (
            f"{row['designation']} reached the client without naming its replacement")
    for row in payload["results"]:
        if row["is_current"]:
            assert row["superseded_by"] == "", (
                "a current standard must not claim to have been replaced")


def test_the_rag_answer_exposes_the_retrieval_envelope(data, search):
    """Mode, stage timings and the withheld editions must reach the caller too.

    `/recommend` answers that returned prose and citations but not the retrieval
    envelope left the client unable to say "your edition was replaced by X", and
    unable to see where the time went without a profiler.
    """
    from bis_rag.rag import RAGPipeline

    answer = RAGPipeline(data, search=search).answer(
        "ordinary portland cement 33 grade", top_k=5, mode="recommend")
    retrieval = answer.as_dict()["retrieval"]
    assert retrieval["mode"] == "recommend"
    assert set(retrieval["timings_ms"]) >= {
        "query_processing", "sparse", "dense", "fusion", "rerank", "total"}
    assert isinstance(retrieval["superseded"], list)
    assert all(item["is_current"] is False for item in retrieval["superseded"])


def test_the_exposure_metric_is_zero_for_a_fixture_run_and_can_fail():
    """The metric must be able to report a violation, or it certifies nothing."""
    from bis_rag.evaluate import CaseResult

    clean = EvalReport(cases=[CaseResult(case=EvalCase(id="a", query="q",
                                                       expected=("IS 269",)))])
    dirty = EvalReport(cases=[CaseResult(
        case=EvalCase(id="a", query="q", expected=("IS 269",)),
        superseded_recommended=["IS 269:1989"])])
    assert clean.superseded_exposure_rate == 0.0
    assert dirty.superseded_exposure_rate == 1.0


# ----------------------------------------------------------------------
# 4. out-of-scope queries
# ----------------------------------------------------------------------
def test_an_empty_expected_list_marks_a_case_as_out_of_scope():
    case = EvalCase(id="n", query="how do I file my taxes", expected=())
    assert case.is_rejection is True
    assert case.sector_name == "Out of scope"


def test_rejection_accuracy_counts_only_the_negative_cases():
    from bis_rag.evaluate import CaseResult

    report = EvalReport(cases=[
        CaseResult(case=EvalCase(id="n1", query="q", expected=()), rejection=True,
                   declined=True),
        CaseResult(case=EvalCase(id="n2", query="q", expected=()), rejection=True,
                   declined=False),
        CaseResult(case=EvalCase(id="p", query="q", expected=("IS 269",)), rank=1),
    ])
    assert report.rejection_accuracy == pytest.approx(0.5)
    # And the negative case must not be in the ranking denominators.
    assert len(report.scoring) == 1
    assert len(report.answerable) == 1
    assert report.hit_rate(1) == 1.0


def test_an_out_of_scope_query_is_not_counted_as_a_coverage_gap():
    from bis_rag.evaluate import CaseResult

    report = EvalReport(cases=[
        CaseResult(case=EvalCase(id="n", query="q", expected=()), rejection=True),
    ])
    assert report.unanswerable == []
    assert report.missing_standards() == {}


def test_the_gate_can_fail_on_rejection_accuracy():
    from bis_rag.evaluate import CaseResult

    report = EvalReport(cases=[
        CaseResult(case=EvalCase(id="n", query="q", expected=()), rejection=True,
                   declined=False)])
    problems = gate_failures(report, min_rejection_accuracy=0.9)
    assert any("rejection accuracy" in p for p in problems)


# ----------------------------------------------------------------------
# 5. latency instrumentation
# ----------------------------------------------------------------------
def test_every_stage_is_timed_and_the_total_covers_them(search):
    response = search.search("ordinary portland cement", top_k=10)
    timings = response.timings
    for stage in ("query_processing", "sparse", "dense", "fusion", "rerank", "total"):
        assert stage in timings, f"{stage} was not timed"
        assert timings[stage] >= 0
    measured = sum(timings[s] for s in ("query_processing", "sparse", "dense",
                                        "fusion", "rerank"))
    assert timings["total"] >= measured * 0.9, (
        "the total must be at least the sum of the stages it contains; "
        f"got {timings['total']} against {measured}")


def test_timings_can_be_switched_off(search):
    quiet = HybridSearch(search.data, store_dir=search.store_dir, embedder="hash",
                         config=RetrievalConfig(top_k=5, instrument=False),
                         reranker="lexical")
    assert quiet.search("cement", top_k=5).timings == {}


def test_stage_summary_reports_p50_p95_p99_per_stage(store, data):
    from bis_rag.evaluate import EvalCase, evaluate

    cases = [EvalCase(id="a", query="ordinary portland cement", expected=("IS 269",)),
             EvalCase(id="b", query="coarse aggregate", expected=("IS 383",))]
    report = evaluate(HybridSearch(data, store_dir=store, embedder="hash",
                                   config=RetrievalConfig(top_k=10),
                                   reranker="lexical"), cases, top_k=10)
    summary = report.stage_summary()
    assert "total" in summary
    assert {"samples", "p50", "p95", "p99", "mean"} <= set(summary["total"])
    assert summary["total"]["samples"] == 2


# ----------------------------------------------------------------------
# 6. artifacts and ablation
# ----------------------------------------------------------------------
def test_the_five_artifacts_are_written_and_named_as_asked(store, data, tmp_path):
    from bis_rag.artifacts import ARTIFACT_NAMES, write_artifacts
    from bis_rag.evaluate import EvalCase, CaseResult

    report = EvalReport(cases=[
        # `answerable=False` is what `evaluate()` sets when the expected
        # standard is absent; the report must not have to re-derive it.
        CaseResult(case=EvalCase(id="miss", query="q", expected=("IS 999",)),
                   answerable=False),
        CaseResult(case=EvalCase(id="neg", query="q", expected=()), rejection=True),
    ], provenance=inspect_provenance(data).as_dict())
    written = write_artifacts(report, out_dir=tmp_path / "results", cases_path="cases.jsonl")
    assert set(written) == set(ARTIFACT_NAMES)
    for path in written.values():
        assert path.exists()

    payload = json.loads((tmp_path / "results" / "latest.json").read_text())
    assert payload["provenance"]["is_fixture"] is True
    assert payload["cases_file"] == "cases.jsonl"

    markdown = (tmp_path / "results" / "latest.md").read_text()
    assert "NOT PRODUCTION ACCURACY" in markdown
    assert "Targets versus measurements" in markdown

    failures = [json.loads(line) for line in
                (tmp_path / "results" / "failures.jsonl").read_text().splitlines()]
    reasons = {row["id"]: row["reasons"] for row in failures}
    # The reason is specific: the standard is not in the corpus, which is a
    # coverage gap, not a ranking miss. Reporting both as "miss" would send
    # someone to tune the ranker for a corpus problem.
    assert reasons["miss"] == ["standard_not_in_corpus"]
    assert reasons["neg"] == ["out_of_scope_answered"]

    missing = json.loads((tmp_path / "results" / "missing_corpus_standards.json").read_text())
    assert missing["missing"][0]["designation"] == "IS 999"
    assert missing["missing"][0]["cases"] == ["miss"]

    assert (tmp_path / "results" / "ablation.csv").exists()


def test_an_answered_out_of_scope_query_lands_in_failures():
    from bis_rag.artifacts import failure_records
    from bis_rag.evaluate import CaseResult

    report = EvalReport(cases=[CaseResult(
        case=EvalCase(id="n", query="best restaurants", expected=()),
        rejection=True, declined=False, top=["IS 1:1968"])])
    records = failure_records(report)
    assert records[0]["reasons"] == ["out_of_scope_answered"]
    assert records[0]["top"] == ["IS 1:1968"]


def test_the_ablation_configs_are_the_six_the_brief_listed():
    names = [c.name for c in ABLATION_CONFIGS]
    assert names == ["tfidf_only", "bm25_only", "dense_only", "bm25_dense",
                     "bm25_dense_rrf", "bm25_dense_rrf_rerank"]
    by_name = {c.name: c for c in ABLATION_CONFIGS}
    assert by_name["tfidf_only"].use_bm25 is False
    assert by_name["bm25_only"].use_dense is False
    # The two fusion rows exist precisely to be compared with each other.
    assert by_name["bm25_dense"].fusion == "score"
    assert by_name["bm25_dense_rrf"].fusion == "rrf"
    assert by_name["bm25_dense_rrf_rerank"].rerank is True


def test_ablation_rows_carry_every_metric_the_brief_asked_for():
    from bis_rag.evaluate import EvalReport

    rows = ablation_rows([(ABLATION_CONFIGS[5], EvalReport())])
    row = rows[0]
    for column in ("hit@1", "hit@3", "hit@5", "hit@10", "mrr@5", "exact_edition",
                   "hard_hit@5", "latency_p50_ms", "latency_p95_ms",
                   "superseded_first", "superseded_exposure"):
        assert column in row, column


def test_rank_fusion_and_score_fusion_disagree_when_the_scales_disagree(search):
    """The two fusion rows differ for a reason, so the ablation can separate them.

    Asserted on constructed candidates rather than on whichever query happens to
    order differently: BM25 scores are unbounded and cosine is not, and the
    point of normalising is that a leg cannot win by emitting larger numbers.
    Here the dense leg is the more confident one (its scores are tightly
    clustered at the top) while BM25 emits one huge number for an unrelated
    document -- rank fusion cannot see the difference, score fusion can.
    """
    from bis_rag.hybrid import Candidate, HybridSearch as HS, RetrievalConfig as RC

    # "consistent" is second in BM25 and second in dense by a hair.
    # "clear_leader" wins the dense leg outright.
    # Rank fusion rewards the first; score fusion rewards the second.
    bm25 = [Candidate(id="consistent", text="x", metadata={}, score=6.0,
                      retriever="bm25:standards", rank=1),
            Candidate(id="runner_up", text="y", metadata={}, score=5.999,
                      retriever="bm25:standards", rank=2)]
    dense = [Candidate(id="clear_leader", text="z", metadata={}, score=0.70,
                       retriever="dense:standards", rank=1),
             Candidate(id="consistent", text="x", metadata={}, score=0.699,
                       retriever="dense:standards", rank=2)]

    def first(fusion: str) -> str:
        searcher = HS(search.data, store_dir=search.store_dir, embedder="hash",
                      config=RC(fusion=fusion))
        return searcher._fuse([bm25, dense])[0].id

    assert first("rrf") == "consistent", (
        "rank fusion counts positions, so a document near the top of both lists "
        "should win")
    assert first("score") == "clear_leader", (
        "score fusion normalises within each leg, so the outright leader of one "
        "leg should win")


def test_the_two_fusion_rows_still_return_a_full_ranking(search):
    """Whatever they disagree about, both have to work end to end."""
    for fusion in ("rrf", "score"):
        searcher = HybridSearch(search.data, store_dir=search.store_dir,
                                embedder="hash",
                                config=RetrievalConfig(top_k=10, fusion=fusion),
                                reranker="none")
        results = searcher.search("ordinary portland cement 33 grade", top_k=10).results
        assert results, fusion
        assert results[0].designation
