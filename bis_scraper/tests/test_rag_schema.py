"""Tests for the data contract in ``bis_rag.schema`` and ``bis_rag.data``.

The load-bearing test here is
:func:`test_empty_text_field_is_a_hard_error`. It encodes the bug this module
was written to prevent: the original ``build_chromadb.py`` read
``chunk.get("text", chunk.get("content",""))`` from a file whose field is
``chunk``, indexed 9,043 empty documents, and reported success. A test that
merely checks "loading works" would have passed on that build.
"""

from __future__ import annotations

import json

import pytest

from bis_rag.data import BisData
from bis_rag.schema import (
    CHUNK_ALIASES,
    Chunk,
    SchemaError,
    Standard,
    as_bool,
    as_int,
    as_text,
    coverage,
    dedupe_standards,
    first_present,
    load_chunks,
    load_jsonl,
)

from synth_bis_data import make_synth_data


@pytest.fixture(scope="module")
def data_root(tmp_path_factory) -> object:
    return make_synth_data(tmp_path_factory.mktemp("bis_data"))


@pytest.fixture(scope="module")
def data(data_root) -> BisData:
    return BisData(data_root)


# ----------------------------------------------------------------------
# coercion
# ----------------------------------------------------------------------
@pytest.mark.parametrize("value,expected", [
    (True, True), (False, False), ("true", True), ("True", True), ("yes", True),
    ("1", True), ("0", False), ("superseded", False), ("current", True),
    (1, True), (0, False), (float("nan"), True),
])
def test_as_bool_handles_csv_roundtrips(value, expected):
    assert as_bool(value) is expected


@pytest.mark.parametrize("value,expected", [
    (1989, 1989), ("1989", 1989), ("1989.0", 1989), ("", None),
    (float("nan"), None), (None, None), ("nan", None), ("not a year", None),
])
def test_as_int_handles_missing_and_floats(value, expected):
    assert as_int(value) == expected


def test_as_text_treats_pandas_nulls_as_empty():
    assert as_text(None) == ""
    assert as_text(float("nan")) == ""
    assert as_text("nan") == ""
    assert as_text("  cement  ") == "cement"


def test_first_present_prefers_the_real_key_then_aliases():
    record = {"is_number": "IS 1:1968", "designation": "IS 1:1968", "title": "Flag"}
    assert first_present(record, "designation", "is_number") == "IS 1:1968"
    assert first_present(record, "chunk", "text", default="none") == "none"


# ----------------------------------------------------------------------
# the regression that matters
# ----------------------------------------------------------------------
def test_empty_text_field_is_a_hard_error(tmp_path):
    """A file whose text field is empty must raise, not index empty vectors."""
    path = tmp_path / "chunked_documents.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        for i in range(10):
            # Exactly the shape the draft script assumed: no `chunk` key at all.
            fh.write(json.dumps({
                "chunk_id": f"c{i}", "standard_id": "IS|1|None|None|1968",
                "designation": "IS 1:1968", "title": "Flag",
                "text": "", "is_number": "IS 1:1968",
            }) + "\n")

    with pytest.raises(SchemaError) as excinfo:
        load_chunks(path)
    message = str(excinfo.value)
    assert "text" in message
    # The message must name the keys it looked for, or it cannot be acted on.
    assert "'chunk'" in message
    assert "silent" not in message.lower() or "nonsense" in message.lower()


def test_alias_is_accepted_but_reported(tmp_path):
    """The draft's field names still load -- and coverage names the alias used."""
    path = tmp_path / "chunked_documents.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        for i in range(5):
            fh.write(json.dumps({
                "chunk_id": f"c{i}",
                "standard_id": "IS|1|None|None|1968",
                "content": "Chloride content shall not exceed the limit in the table. " * 3,
                "is_number": "IS 1:1968",
                "status": "current",
            }) + "\n")

    chunks, report = load_chunks(path)
    assert len(chunks) == 5
    text_cov = next(c for c in report if c.field == "text")
    assert text_cov.source_key == "content"      # alias recorded, not hidden
    assert text_cov.ratio == 1.0
    assert chunks[0].designation == "IS 1:1968"  # is_number was understood
    assert chunks[0].is_current is True          # status string was understood


def test_coverage_counts_per_field():
    records = [{"chunk": "a"}, {"chunk": "b", "year": 1990}]
    report = {c.field: c for c in coverage(records, CHUNK_ALIASES)}
    assert report["text"].filled == 2
    assert report["year"].filled == 1
    assert report["year"].ratio == 0.5


# ----------------------------------------------------------------------
# chunk / standard shaping
# ----------------------------------------------------------------------
def test_chunk_embedding_text_leads_with_metadata_and_ends_with_content():
    chunk = Chunk(chunk_id="c1", text="The pipes shall be galvanized.",
                  designation="IS 1239:2004", title="Steel tubes",
                  division="Mechanical Engineering", year=2004, is_current=True)
    text = chunk.embedding_text()
    assert text.startswith("IS Code: IS 1239:2004")
    assert text.endswith("The pipes shall be galvanized.")
    assert "Status: current" in text


def test_chunk_metadata_keeps_native_types():
    """Stringifying years breaks ``{"year": {"$gte": ...}}`` filters."""
    chunk = Chunk(chunk_id="c1", text="x", year=2004, is_current=False)
    meta = chunk.as_metadata()
    assert meta["year"] == 2004 and isinstance(meta["year"], int)
    assert meta["is_current"] is False and isinstance(meta["is_current"], bool)
    assert meta["status"] == "superseded"


def test_chunk_missing_year_uses_sentinel_not_none():
    # ChromaDB rejects None metadata values outright.
    assert Chunk(chunk_id="c", text="x").as_metadata()["year"] == -1


def test_standard_naming_its_replacement_is_not_current():
    """The explicit chain beats the flag, which CSV round-trips can corrupt."""
    std = Standard.from_record({
        "canonical": "IS|456|None|None|1978", "designation": "IS 456:1978",
        "is_current": True, "superseded_by": "IS 456:2000",
    })
    assert std.is_current is False
    assert std.superseded_by == "IS 456:2000"
    assert "Superseded by: IS 456:2000" in std.embedding_text()


def test_keywords_accept_list_and_comma_string():
    from_list = Standard.from_record({"keywords": ["cement", "portland"]})
    from_string = Standard.from_record({"keywords": "cement, portland"})
    assert from_list.keywords == ("cement", "portland")
    assert from_string.keywords == ("cement", "portland")


def test_dedupe_prefers_the_richer_row():
    thin = Standard(canonical="IS|1|None|None|1968", designation="IS 1:1968",
                    is_current=True, is_compulsory=True)
    rich = Standard(canonical="IS|1|None|None|1968", designation="IS 1:1968",
                    title="National Flag", summary="full text here", is_current=True)
    merged = dedupe_standards([thin, rich])
    assert len(merged) == 1
    assert merged[0].title == "National Flag"
    assert merged[0].summary == "full text here"
    assert merged[0].is_compulsory is True   # flags are OR-ed, not lost


# ----------------------------------------------------------------------
# loaders
# ----------------------------------------------------------------------
def test_load_jsonl_reports_the_offending_line(tmp_path):
    path = tmp_path / "broken.jsonl"
    path.write_text('{"ok": 1}\n{not json}\n', encoding="utf-8")
    with pytest.raises(SchemaError) as excinfo:
        load_jsonl(path)
    assert ":2:" in str(excinfo.value)


def test_missing_file_error_names_the_regenerating_command(tmp_path):
    data = BisData(tmp_path)
    with pytest.raises(SchemaError) as excinfo:
        data.chunks()
    message = str(excinfo.value)
    assert "create_rag_dataset.py" in message
    assert "BIS_DATA_DIR" in message     # how to point somewhere else


# ----------------------------------------------------------------------
# BisData integration
# ----------------------------------------------------------------------
def test_availability_reports_every_expected_file(data_root):
    statuses = {s.key: s for s in BisData(data_root).availability()}
    assert statuses["chunks"].exists
    assert statuses["search_index"].exists
    assert statuses["merged_standards"].exists
    assert statuses["chunks"].size > 0


def test_summary_counts_match_the_fixture(data):
    summary = data.summary()
    assert summary["chunks"] > 0
    assert summary["standards"] == 12
    assert summary["current"] + summary["superseded"] == 12


def test_supersession_resolves_the_designation_string_to_a_canonical(data):
    """``superseded_by`` holds a designation, not an id -- resolve it."""
    info = data.supersession("IS|456|None|None|1978")
    assert info is not None
    assert info.replacement_designation == "IS 456:2000"
    assert info.replacement_canonical == "IS|456|None|None|2000"
    assert info.in_dataset is True


def test_supersession_of_a_current_standard_is_none(data):
    assert data.supersession("IS|456|None|None|2000") is None


def test_resolve_designation_handles_loose_input(data):
    for text in ("IS 10500:2012", "is 10500:2012", "IS 10500 (2012)"):
        std = data.resolve_designation(text)
        assert std is not None and std.year == 2012


def test_concepts_are_loaded_from_the_ontology(data):
    concepts = data.concepts()
    assert "cement" in concepts
    assert "IS|269|None|None|2015" in concepts["cement"]


def test_tfidf_index_is_reused_not_rebuilt(data):
    index = data.tfidf_index()
    assert index is not None
    assert len(index.docs) == 12
    # The pre-built index must actually answer questions.
    hits = index.search("drinking water", k=3, current_only=True, min_score=0.0)
    assert hits and "10500" in hits[0].designation
