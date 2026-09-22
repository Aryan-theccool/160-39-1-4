"""What happens when a model cites something that is not there.

The citation check is the only thing standing between a language model and a
user who will act on what it says -- "the permissible limit is X per IS 1234",
where IS 1234 does not exist or is not the standard being discussed. That check
had never been exercised end to end, because exercising it needed an API key.

`ScriptedGenerator` removes the key from the problem without faking the path: it
implements the same protocol as the real generators, so the pipeline runs its
real code -- mode becomes "llm", `verify_citations` runs, unsupported citations
are flagged -- and the assertions below are assertions about `RAGPipeline`.

Three deliberate failures, per the brief:
  a. a valid standard the context supports;
  b. a fabricated IS number;
  c. a real standard cited with the wrong edition.

The live tests at the bottom run against a real provider when GROQ_API_KEY is
set, and are skipped otherwise. They are marked `live_llm` so a normal run is
keyless; see pyproject.toml for the marker registration.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from bis_rag.data import BisData
from bis_rag.hybrid import HybridSearch, RetrievalConfig
from bis_rag.rag import RAGPipeline, ScriptedGenerator, verify_citations

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


# ----------------------------------------------------------------------
# fixtures
# ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def data(tmp_path_factory) -> BisData:
    """A small real corpus, built by the same code the product uses."""
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from synth_bis_data import make_synth_data

    root = tmp_path_factory.mktemp("citation_data")
    make_synth_data(root / "bis_data")
    return BisData(root / "bis_data")


@pytest.fixture(scope="module")
def search(data, tmp_path_factory) -> HybridSearch:
    from bis_rag.build_vector_store import BuildConfig, build

    store = tmp_path_factory.mktemp("citation_store") / "store"
    build(BuildConfig(data_dir=data.root, store_dir=store, backend="json",
                      embedder="hash", batch_size=8, verify=False))
    return HybridSearch(data, store_dir=store, embedder="hash",
                        config=RetrievalConfig(top_k=6), reranker="lexical")


@pytest.fixture
def render(pipeline_factory):
    def _render(generator, question="ordinary portland cement 33 grade"):
        return pipeline_factory(generator).answer(question, top_k=6)

    return _render


@pytest.fixture
def pipeline_factory(data, search):
    def _factory(generator) -> RAGPipeline:
        return RAGPipeline(data, search=search, generator=generator)

    return _factory


# ----------------------------------------------------------------------
# the three scripted answers
# ----------------------------------------------------------------------
def test_a_supported_citation_is_not_flagged(pipeline_factory, render, search):
    """(a) The model cites a standard that is genuinely in the context."""
    context = search.search("ordinary portland cement 33 grade", top_k=6)
    assert context.results, "the fixture must retrieve something for this test"
    designation = context.results[0].designation

    answer = render(ScriptedGenerator([f"Ordinary Portland cement is covered by {designation}."]))
    assert answer.mode == "llm"
    assert answer.unsupported_citations == []
    assert answer.grounded is True


def test_a_fabricated_standard_is_flagged_and_reported(render):
    """(b) A citation for a standard the corpus does not hold."""
    answer = render(ScriptedGenerator([
        "Cement is covered by IS 269:2015. Site safety is covered by IS 99999:2021."
    ]))
    assert answer.mode == "llm"
    assert "IS 99999:2021" in answer.unsupported_citations
    assert answer.grounded is False
    # A flag nobody sees is not a guard: the warning has to reach the caller.
    assert any("IS 99999:2021" in warning for warning in answer.warnings)
    assert any("not present in the retrieved context" in warning for warning in answer.warnings)


def test_the_wrong_edition_of_a_real_standard_is_flagged_as_an_edition_error(render):
    """(c) The standard exists; the cited year does not match the context.

    Distinguished from (b) on purpose. "IS 269:1970" is a different complaint
    from "IS 99999" -- one is an invented edition of a real standard, the other
    is an invented standard -- and the message says which.
    """
    answer = render(ScriptedGenerator(["Use IS 269:1970 for ordinary Portland cement."]))
    flagged = " ".join(answer.unsupported_citations)
    assert "IS 269:1970" in flagged
    assert "edition not in the retrieved context" in flagged


def test_a_yearless_citation_of_a_held_standard_is_accepted(render, search):
    """The counterpart to (c): brevity is not an error.

    A model that writes "IS 269" when the context holds "IS 269:2015" is not
    wrong, and flagging it would train the reader to ignore the flag.
    """
    number = search.search("ordinary portland cement 33 grade", top_k=1).results[0].designation
    stem = number.split(":")[0]
    answer = render(ScriptedGenerator([f"The relevant standard is {stem}."]))
    assert answer.unsupported_citations == []


def test_several_bad_citations_are_all_reported_not_just_the_first(render):
    answer = render(ScriptedGenerator([
        "IS 99998:2021 and IS 99999:2021 both apply, and so does IS 269:1970."
    ]))
    assert len(answer.unsupported_citations) == 3
    assert len(answer.warnings) == 1, "one warning listing them all, not one each"


def test_a_generator_failure_falls_back_to_extractive_and_says_so(pipeline_factory):
    """A provider outage must not become an unsourced answer."""

    class Exploding:
        name = "exploding"
        is_llm = True

        def complete(self, *, system, user, max_tokens=900):
            raise RuntimeError("provider returned 503")

    answer = pipeline_factory(Exploding()).answer("ordinary portland cement", top_k=4)
    assert answer.mode == "extractive"
    assert answer.citations, "the fallback still answers from retrieved passages"
    assert any("503" in note for note in answer.notes)


def test_the_scripted_generator_replays_in_order_and_then_repeats(pipeline_factory):
    """The double itself, so a passing test above cannot be a silent no-op."""
    generator = ScriptedGenerator(["first", "second"])
    assert generator.complete(system="s", user="u1") == "first"
    assert generator.complete(system="s", user="u2") == "second"
    assert generator.complete(system="s", user="u3") == "second"
    assert generator.calls == 3
    assert generator.prompts == ["u1", "u2", "u3"]
    assert generator.is_llm is True


def test_verify_citations_is_what_flags_them(search):
    """The check called directly, without a pipeline in the way."""
    results = search.search("ordinary portland cement 33 grade", top_k=3).results
    unsupported = verify_citations("IS 269:2015 and IS 99999:2021", results)
    assert unsupported == ["IS 99999:2021"]


# ----------------------------------------------------------------------
# live provider (optional)
# ----------------------------------------------------------------------
live = pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="live_llm tests need GROQ_API_KEY; they are skipped without one",
)


@pytest.mark.live_llm
@live
def test_a_real_model_does_not_invent_citations_past_the_guard(pipeline_factory):
    """The same guarantee, against a real provider.

    Asserts the *invariant*, not the prose: whatever the model writes, anything
    it cites that is not in the retrieved context must be flagged. A model that
    hallucinates is not a test failure -- the system is not supposed to prevent
    that; failing to notice it is.
    """
    pipeline = pipeline_factory("groq")
    answer = pipeline.answer("ordinary portland cement 33 grade", top_k=6)
    assert answer.mode == "llm", "GROQ_API_KEY is set, so this should have generated"
    assert answer.unsupported_citations == [] or answer.warnings
    # And the citations it did make must resolve.
    for citation in answer.citations:
        assert citation.designation


@pytest.mark.live_llm
@live
def test_a_real_model_answers_from_the_context_it_was_given(pipeline_factory):
    pipeline = pipeline_factory("groq")
    answer = pipeline.answer("what is ordinary portland cement used for", top_k=6)
    assert answer.mode == "llm"
    assert answer.answer.strip()
    assert answer.grounded or answer.unsupported_citations
