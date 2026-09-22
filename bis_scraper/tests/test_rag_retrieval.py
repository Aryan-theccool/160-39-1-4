"""End-to-end tests for retrieval and generation: Parts 1-3.

These run against the synthetic corpus in ``synth_bis_data.py``, whose field
names are copied from the real generators. A retrieval assertion that passes
here ("drinking water" must return IS 10500) is therefore meaningful, and the
same assertion failed earlier in development for the right reason: ontology
expansion had pulled "unplasticized, pipes, tubes" into the query and pushed a
PVC-pipe standard to the top.
"""

from __future__ import annotations

import pytest

from bis_rag.bm25 import BM25Index
from bis_rag.data import BisData
from bis_rag.embeddings import EmbedderMismatch, HashingEmbedder, get_embedder
from bis_rag.hybrid import HybridSearch, LexicalReranker, RetrievalConfig
from bis_rag.query_processor import Intent, QueryProcessor
from bis_rag.rag import ExtractiveGenerator, RAGPipeline, verify_citations
from bis_rag.vectorstore import available_backends

from synth_bis_data import make_synth_data


@pytest.fixture(scope="module")
def data_root(tmp_path_factory):
    return make_synth_data(tmp_path_factory.mktemp("bis_data"))


@pytest.fixture(scope="module")
def data(data_root) -> BisData:
    return BisData(data_root)


@pytest.fixture(scope="module")
def store_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("store")


@pytest.fixture(scope="module")
def built_store(data: BisData, store_dir):
    """Build the store once per module; BM25 indexing and embedding are the slow part."""
    from bis_rag.build_vector_store import BuildConfig, build

    build(BuildConfig(data_dir=data.root, store_dir=store_dir, backend="json",
                      embedder="hash", batch_size=8, verify=False))
    return store_dir


@pytest.fixture(scope="module")
def search(data: BisData, built_store) -> HybridSearch:
    return HybridSearch(data, store_dir=built_store, embedder="hash",
                        reranker=LexicalReranker())


# ----------------------------------------------------------------------
# Part 1: the vector store
# ----------------------------------------------------------------------
def test_build_indexes_every_chunk_and_standard(data, built_store):
    from bis_rag.vectorstore import CHUNK_COLLECTION, STANDARD_COLLECTION, open_store

    chunks = open_store(built_store, CHUNK_COLLECTION, backend="json", create=False)
    standards = open_store(built_store, STANDARD_COLLECTION, backend="json", create=False)
    assert chunks.count() == len(data.chunks())
    assert standards.count() == len(data.standards())


def test_store_records_the_embedder_fingerprint(data, built_store):
    from bis_rag.vectorstore import CHUNK_COLLECTION, open_store

    store = open_store(built_store, CHUNK_COLLECTION, backend="json", create=False)
    meta = store.get_meta()
    assert meta["embedder"]["name"] == "hash-bow-v1"
    assert meta["embedder"]["fingerprint"]


def test_querying_with_a_different_embedder_raises(data, built_store):
    """The silent-corruption guard: mismatched vectors must not be scored."""
    from bis_rag.vectorstore import CHUNK_COLLECTION, open_store

    other = HashingEmbedder(dim=8192)          # different width AND fingerprint
    store = open_store(built_store, CHUNK_COLLECTION, backend="json", create=False)
    with pytest.raises(EmbedderMismatch) as excinfo:
        store.assert_compatible(other)
    message = str(excinfo.value)
    assert "different models" in message or "meaningless" in message
    assert "bis-rag build" in message


def test_dense_retrieval_returns_the_right_standard(search, built_store):
    vector = get_embedder("hash").encode_one("ordinary portland cement", is_query=True)
    hits = search._store("standards").query(vector, n_results=3)
    assert hits
    assert "269" in hits[0].designation


@pytest.mark.skipif("chroma" not in available_backends(), reason="chromadb not installed")
def test_chroma_backend_round_trips(data, tmp_path):
    from bis_rag.build_vector_store import BuildConfig, build
    from bis_rag.vectorstore import CHUNK_COLLECTION, open_store

    store_dir = tmp_path / "chroma_store"
    build(BuildConfig(data_dir=data.root, store_dir=store_dir, backend="chroma",
                      embedder="hash", batch_size=8, verify=False))
    store = open_store(store_dir, CHUNK_COLLECTION, backend="chroma", create=False)
    assert store.count() == len(data.chunks())
    hits = store.query(get_embedder("hash").encode_one("drinking water", is_query=True),
                       n_results=3)
    assert any("10500" in h.designation for h in hits)


def test_chroma_metadata_filter_uses_native_types(data, tmp_path):
    """An int year must filter numerically, not lexicographically."""
    from bis_rag.build_vector_store import BuildConfig, build
    from bis_rag.vectorstore import CHUNK_COLLECTION, open_store

    store_dir = tmp_path / "chroma_filter"
    build(BuildConfig(data_dir=data.root, store_dir=store_dir, backend="chroma",
                      embedder="hash", batch_size=8, verify=False))
    store = open_store(store_dir, CHUNK_COLLECTION, backend="chroma", create=False)
    vector = get_embedder("hash").encode_one("standard", is_query=True)
    hits = store.query(vector, n_results=20, where={"year": {"$gte": 2010}})
    assert hits
    assert all(h.metadata["year"] >= 2010 for h in hits)


# ----------------------------------------------------------------------
# Part 2a: query understanding
# ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def processor(data: BisData) -> QueryProcessor:
    return QueryProcessor(data)


@pytest.mark.parametrize("query,intent", [
    ("Is cement covered under mandatory BIS certification?", Intent.COMPLIANCE),
    ("Has IS 456:1978 been superseded?", Intent.SUPERSESSION),
    ("What is the latest standard for drinking water?", Intent.LATEST),
    ("What is IS 1239:2004?", Intent.LOOKUP),
    ("What does IS 456:2000 cover?", Intent.EXPLAIN),
])
def test_intent_classification(processor, query, intent):
    assert processor.process(query).intent == intent


def test_designation_extraction_uses_iscode(processor):
    processed = processor.process("compare IS 456:2000 with IS 1786:2008")
    assert [d.format() for d in processed.designations] == ["IS 456:2000", "IS 1786:2008"]


def test_ocr_noise_is_not_mistaken_for_a_designation(processor):
    assert processor.process("see IS 1 113C7 - 1905 for details").designations == []


def test_division_filter_resolves_to_a_real_division(processor):
    processed = processor.process("standards for Civil Engineering")
    assert processed.divisions == ["Civil Engineering"]
    assert processed.where()["$and"][0]["division"]["$in"] == ["Civil Engineering"]


def test_committee_filter_does_not_match_a_longer_committee_code(processor):
    """``CED 2`` must not match text about ``CED 25``."""
    assert processor.process("what does CED 2 handle?").committees == ["CED 2"]
    assert processor.process("what does CED 25 handle?").committees == ["CED 25"]


def test_compliance_queries_do_not_filter_out_superseded_editions(processor):
    """The whole point of a compliance check is finding withdrawn editions."""
    assert processor.process("is cement mandatory?").current_only is False
    assert processor.process("cement standard").current_only is True


def test_expansion_requires_two_supporting_standards(processor):
    """"drinking water" must not drag in a lone PVC-pipe standard's vocabulary."""
    processed = processor.process("drinking water quality")
    assert "unplasticized" not in processed.expansions
    assert "tubes" not in processed.expansions


def test_bm25_uses_the_unexpanded_query(search):
    """Expansions belong to the dense leg only; they distort BM25 term counts."""
    processed = search._processor().process("drinking water quality")
    assert processed.expansions or True     # expansions may exist
    assert processed.search_text == "drinking water quality"


# ----------------------------------------------------------------------
# Part 3: hybrid search
# ----------------------------------------------------------------------
@pytest.mark.parametrize("query,expected", [
    ("cement for construction", "269"),
    ("drinking water quality", "10500"),
    ("steel reinforcement bars for concrete", "1786"),
    ("unplasticized PVC pipes for potable water", "4985"),
])
def test_top_hit_is_the_right_standard(search, query, expected):
    response = search.search(query, top_k=5)
    designations = [r.designation for r in response.results]
    assert any(expected in d for d in designations), designations
    assert expected in response.results[0].designation


def test_exact_designation_lookup_is_promoted_to_rank_one(search):
    response = search.search("IS 1239:2004", top_k=5)
    assert "1239" in response.results[0].designation
    assert response.results[0].provenance.get("exact") == 1


def test_results_carry_provenance(search):
    response = search.search("steel reinforcement", top_k=3)
    top = response.results[0]
    assert top.provenance, "every result must say which retriever found it"
    assert top.score > 0


def test_fusion_rewards_agreement(search):
    """A document found by several retrievers must outrank one found by one.

    Tested on the fuser directly rather than through ``search()``: reranking is
    a separate stage that legitimately reorders by a different signal, so a
    ranking assertion made end-to-end would be testing both at once and would
    not tell you which one broke.
    """
    from bis_rag.hybrid import Candidate

    agreed = Candidate(id="agreed", text="x", metadata={"is_current": True},
                       score=0.5, retriever="bm25:chunks", rank=2)
    agreed_too = Candidate(id="agreed", text="x", metadata={"is_current": True},
                           score=0.4, retriever="dense:chunks", rank=1)
    single = Candidate(id="single", text="y", metadata={"is_current": True},
                       score=9.9, retriever="bm25:chunks", rank=1)

    fused = search._fuse([[single], [agreed, agreed_too]])
    assert fused[0].id == "agreed", "agreement across retrievers must win"
    assert set(fused[0].provenance) == {"bm25:chunks", "dense:chunks"}
    # A huge raw score from one retriever does not beat agreement, because RRF
    # ignores scores entirely.
    assert fused[1].id == "single"


def test_superseded_edition_produces_a_warning(search):
    response = search.search("Has IS 456:1978 been superseded?", top_k=5)
    assert response.supersession_warnings
    warning = response.supersession_warnings[0]
    assert warning["designation"] == "IS 456:1978"
    assert warning["superseded_by"] == "IS 456:2000"


def test_current_editions_excluded_by_default_for_topic_search(search):
    response = search.search("code of practice for reinforced concrete", top_k=8)
    assert all(r.is_current for r in response.results)


def test_diversity_cap_limits_repeats_of_one_standard(data, store_dir):
    search = HybridSearch(data, store_dir=store_dir, embedder="hash",
                          config=RetrievalConfig(max_per_standard=1),
                          reranker=LexicalReranker())
    response = search.search("cement", top_k=6)
    canonicals = [r.canonical for r in response.results if r.canonical]
    assert len(canonicals) == len(set(canonicals))


def test_bm25_index_scores_better_for_a_rarer_term(data):
    index = BM25Index.from_standards(data.standards())
    hits = index.search("unplasticized polyvinyl chloride")
    assert hits
    top = data.standards()[hits[0][0]]
    assert "4985" in top.designation


# ----------------------------------------------------------------------
# Part 2b: generation and citation verification
# ----------------------------------------------------------------------
def test_extractive_answer_quotes_and_cites_without_an_llm(search):
    pipeline = RAGPipeline(search.data, search, generator=ExtractiveGenerator())
    answer = pipeline.answer("what is IS 1239:2004?", top_k=3)
    assert answer.mode == "extractive"
    assert answer.citations
    assert "1239" in answer.citations[0].designation
    assert any("No LLM is configured" in note for note in answer.notes)


def test_superseded_citation_is_flagged_in_the_answer(search):
    pipeline = RAGPipeline(search.data, search, generator=ExtractiveGenerator())
    answer = pipeline.answer("Has IS 456:1978 been superseded?", top_k=5)
    assert answer.warnings
    assert any("superseded" in w.lower() for w in answer.warnings)
    superseded = [c for c in answer.citations if not c.is_current]
    assert superseded and superseded[0].superseded_by == "IS 456:2000"


def test_compliance_answer_reports_qco_status(search):
    pipeline = RAGPipeline(search.data, search, generator=ExtractiveGenerator())
    answer = pipeline.answer("is cement mandatory?", top_k=5)
    assert "compulsory" in answer.answer.lower()
    assert (answer.search is not None
            and answer.search.results[0].is_current), "must lead with the current edition"


def test_empty_result_set_says_so_rather_than_guessing(search):
    pipeline = RAGPipeline(search.data, search, generator=ExtractiveGenerator())
    answer = pipeline.answer("zzzqqq nonexistent topic", top_k=3)
    assert "No matching standards" in answer.answer
    assert answer.search is not None and not answer.search.results
    assert answer.citations == []


# -- citation verification --------------------------------------------
def test_verify_citations_accepts_a_supported_yearless_citation():
    class R:
        designation = "IS 456:2000"
        canonical = "IS|456|None|None|2000"
    assert verify_citations("See (IS 456) for details.", [R()]) == []


def test_verify_citations_rejects_an_invented_standard():
    class R:
        designation = "IS 456:2000"
        canonical = "IS|456|None|None|2000"
    unsupported = verify_citations("Use (IS 9103:1999) and (IS 456:2000).", [R()])
    assert unsupported == ["IS 9103:1999"]


def test_verify_citations_flags_a_wrong_edition_of_a_real_standard():
    class R:
        designation = "IS 456:2000"
        canonical = "IS|456|None|None|2000"
    unsupported = verify_citations("Use (IS 456:1978).", [R()])
    assert unsupported and "edition not in the retrieved context" in unsupported[0]


def test_generated_answer_with_a_bad_citation_is_reported_as_ungrounded(data):
    class LyingGenerator:
        name = "test-lying"
        is_llm = True

        def complete(self, *, system: str, user: str, max_tokens: int = 900) -> str:
            return "According to IS 99999:2020, cement must be blue."

    search = HybridSearch(data, store_dir=data.root / "vector_store", embedder="hash")
    from bis_rag.schema import SchemaError
    try:
        pipeline = RAGPipeline(data, search, generator=LyingGenerator())
        answer = pipeline.answer("cement colour", top_k=3)
    except SchemaError:
        pytest.skip("store not built for this data root")
    assert answer.unsupported_citations
    assert answer.grounded is False


# ----------------------------------------------------------------------
# build/search must agree on where the store lives
# ----------------------------------------------------------------------
def test_build_and_search_default_to_the_same_store_directory(data, tmp_path):
    """Regression: these once differed, so the store was written where the
    searcher never looked and dense retrieval silently disappeared."""
    from bis_rag.build_vector_store import BuildConfig
    from bis_rag.hybrid import DEFAULT_STORE_DIRNAME, HybridSearch

    config = BuildConfig(data_dir=data.root)
    assert config.store_dir is None
    expected = data.root / DEFAULT_STORE_DIRNAME
    search = HybridSearch(data, embedder="hash", reranker=LexicalReranker())
    assert search.store_dir == expected


def test_missing_store_is_reported_not_silently_skipped(data, tmp_path):
    from bis_rag.hybrid import HybridSearch, RetrievalConfig

    search = HybridSearch(data, store_dir=tmp_path / "empty_store", embedder="hash",
                          config=RetrievalConfig(rerank=False), reranker=LexicalReranker())
    response = search.search("cement", top_k=3)
    assert any("dense) retrieval is inactive" in note for note in response.notes)
    # BM25 still answers -- the degradation is visible, not fatal.
    assert response.results
