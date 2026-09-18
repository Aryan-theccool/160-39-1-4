"""Tests for merging, edition resolution and the search index."""

import json
from pathlib import Path

import pytest

from bis_pipeline.index import SearchIndex, export_for_chroma, tokenize
from bis_pipeline.iscode import parse_designation
from bis_pipeline.mandatory import MandatoryStandard
from bis_pipeline.merger import (
    StandardRecord,
    archive_items_from_jsonl,
    from_archive_items,
    from_mandatory,
    from_portal_rows,
    merge,
    resolve_editions,
    to_dataframe,
    write_outputs,
)

from conftest import fixture_json


def make_archive_item(identifier="gov.in.is.11367.1985"):
    from bis_pipeline.archive_scraper import parse_item
    return parse_item(fixture_json("item_gov_in_is_11367_1985.json"), identifier=identifier)


class TestMerge:
    def test_same_standard_from_two_sources_collapses(self):
        archive = from_archive_items([make_archive_item()])
        qco = from_mandatory([MandatoryStandard(
            designation=parse_designation("IS 11367:1985"), title="Aerospace textile glossary",
            product_category="Textiles", scheme="Scheme-I")])

        merged = merge(archive, qco)
        assert len(merged) == 1

        rec = merged[0]
        assert rec.canonical == "IS|11367|None|None|1985|None"
        assert set(rec.sources) == {"ARCHIVE_ORG", "BIS_QCO"}
        assert rec.is_compulsory is True
        assert rec.division == "Textiles", "archive metadata is retained"
        assert rec.product_category == "Textiles", "QCO metadata is added"

    def test_qco_wins_over_archive_on_shared_fields(self):
        archive = from_archive_items([make_archive_item()])
        qco = from_mandatory([MandatoryStandard(
            designation=parse_designation("IS 11367:1985"), title="QCO title")])

        rec = merge(archive, qco)[0]
        assert rec.title == "QCO title", "BIS_QCO outranks ARCHIVE_ORG"
        assert rec.status == "mandatory"

    def test_dash_and_paren_spellings_collapse(self):
        a = from_mandatory([MandatoryStandard(designation=parse_designation("IS 302-2-15:2009"))])
        b = from_mandatory([MandatoryStandard(designation=parse_designation("IS 302 (Part 2 / Section 15):2009"))])
        assert len(merge(a, b)) == 1

    def test_unparseable_portal_rows_are_dropped_not_coerced(self):
        rows = [
            {"is_number": "IS 456:2000", "title": "Concrete"},
            {"is_number": "IS 1 113C7 - 1905", "title": "OCR garbage"},
            {"is_number": "", "title": "no number"},
        ]
        records = from_portal_rows(rows)
        assert [r.designation for r in records] == ["IS 456:2000"]

    def test_full_text_flag_propagates(self, tmp_path):
        (tmp_path / "gov.in.is.11367.1985.txt").write_text("some text")
        rec = from_archive_items([make_archive_item()], text_dir=tmp_path)[0]
        assert rec.has_full_text is True
        assert rec.text_path.endswith("gov.in.is.11367.1985.txt")


class TestEditions:
    def test_newest_edition_is_current(self):
        records = merge(from_portal_rows([
            {"is_number": "IS 14220:1994", "title": "old"},
            {"is_number": "IS 14220:2002", "title": "new"},
        ]))
        # portal rows are distinct standards (different years), not merged
        assert len(records) == 2
        by_year = {r.year: r for r in records}
        assert by_year[2002].is_current is True
        assert by_year[1994].is_current is False
        assert by_year[1994].superseded_by == "IS 14220:2002"
        assert by_year[2002].superseded_by == ""

    def test_undated_records_stay_current(self):
        records = merge(from_portal_rows([{"is_number": "IS 14220", "title": "x"}]))
        assert records[0].is_current is True

    def test_output_is_sorted(self):
        records = merge(from_portal_rows([
            {"is_number": "IS 456:2000"}, {"is_number": "IS 100:1990"},
            {"is_number": "SP 7:2026"},
        ]))
        assert [(r.prefix, r.number) for r in records] == [("IS", 100), ("IS", 456), ("SP", 7)]


class TestSearchIndex:
    @pytest.fixture
    def index(self):
        records = merge(
            from_archive_items([make_archive_item()]),
            from_portal_rows([
                {"is_number": "IS 10500:2012", "title": "Drinking water - Specification"},
                {"is_number": "IS 8034:1974", "title": "Submersible pumps for irrigation"},
                {"is_number": "IS 15560:2005", "title": "Steel reinforcement bars for concrete"},
            ]),
        )
        return SearchIndex(dim=1 << 12).build(records)

    def test_ranks_by_relevance(self, index):
        hits = index.search("drinking water quality", k=1)
        assert hits[0].designation == "IS 10500:2012"

    def test_finds_submersible_pumps(self, index):
        hits = index.search("submersible pump for irrigation", k=1)
        assert hits[0].designation == "IS 8034:1974"

    def test_metadata_is_searchable(self, index):
        hits = index.search("IS 11367 aerospace textile glossary", k=1)
        assert hits[0].designation == "IS 11367:1985"

    def test_current_only_suppresses_superseded(self):
        records = merge(from_portal_rows([
            {"is_number": "IS 14220:1994", "title": "submersible pump old edition"},
            {"is_number": "IS 14220:2002", "title": "submersible pump new edition"},
        ]))
        index = SearchIndex(dim=1 << 12).build(records)

        current = index.search("submersible pump", k=5, current_only=True)
        assert [h.designation for h in current] == ["IS 14220:2002"]

        everything = index.search("submersible pump", k=5, current_only=False)
        assert len(everything) == 2
        assert any(not h.is_current for h in everything)

    def test_empty_index_and_empty_query(self, index):
        assert SearchIndex().search("anything") == []
        assert index.search("") == []

    def test_roundtrip_persistence(self, index, tmp_path):
        path = index.save(tmp_path / "idx.json")
        restored = SearchIndex.load(path)
        assert len(restored) == len(index)
        assert restored.search("drinking water", k=1)[0].designation == "IS 10500:2012"

    def test_dense_backend_is_used_when_provided(self):
        records = merge(from_portal_rows([
            {"is_number": "IS 10500:2012", "title": "Drinking water"},
            {"is_number": "IS 8034:1974", "title": "Submersible pumps"},
        ]))
        # A toy 2-D embedding keyed off one discriminative word.
        def embed(texts):
            return [[1.0 if "water" in t.lower() else 0.0,
                     1.0 if "pump" in t.lower() else 0.0] for t in texts]

        index = SearchIndex(dim=4).build(records, embed_fn=embed)
        assert index.dense is True
        assert index.search("water", k=1)[0].designation == "IS 10500:2012"
        assert index.search("pump", k=1)[0].designation == "IS 8034:1974"

    def test_export_for_chroma_shape(self, index):
        payload = export_for_chroma(index)
        assert set(payload) == {"ids", "documents", "metadatas", "embeddings"}
        assert len(payload["ids"]) == len(payload["metadatas"]) == len(index)
        assert payload["embeddings"] is None, "no dense vectors in a tf-idf index"

    def test_indexes_real_ocr_text(self, tmp_path):
        text = tmp_path / "gov.in.is.11367.1985.txt"
        text.write_text(
            "IS 11367 (1985) : Glossary of terms relating to textile materials\n"
            "for aerospace purposes [TXD 13]\n"
            "Air Permeability - The rate of air flow through fabric\n"
        )
        rec = from_archive_items([make_archive_item()], text_dir=tmp_path)[0]
        index = SearchIndex(dim=1 << 12).build([rec])

        assert index.search("air permeability fabric", k=1)[0].designation == "IS 11367:1985"


class TestCrossProcessPersistence:
    """The index is built in one process and queried in another.

    This is the shape every real run takes (`index` then `query`), and it is
    what caught the feature hashing using Python's salted builtin `hash()`:
    buckets assigned while building did not match those assigned while
    querying, so a saved index silently returned no results at all.
    """

    def test_saved_index_is_queryable_from_a_new_process(self, tmp_path):
        import subprocess
        import sys

        script = tmp_path / "run.py"
        index_path = tmp_path / "idx.json"

        script.write_text(f"""
import json, sys
sys.path.insert(0, {str(Path(__file__).resolve().parents[1] / "src")!r})
from bis_pipeline.index import SearchIndex
from bis_pipeline.merger import StandardRecord, merge, from_portal_rows

mode = sys.argv[1]
records = merge(from_portal_rows([
    {{"is_number": "IS 10500:2012", "title": "Drinking water - Specification"}},
    {{"is_number": "IS 8034:1974", "title": "Submersible pumps for irrigation"}},
]))
if mode == "build":
    SearchIndex(dim=1 << 12).build(records).save({str(index_path)!r})
else:
    idx = SearchIndex.load({str(index_path)!r})
    hits = idx.search("submersible pump", k=1)
    print(json.dumps([h.designation for h in hits]))
""")

        env = dict(__import__("os").environ, PYTHONHASHSEED="random")
        subprocess.run([sys.executable, str(script), "build"], check=True, env=env)
        out = subprocess.run([sys.executable, str(script), "query"], check=True,
                             env=env, capture_output=True, text=True)

        assert json.loads(out.stdout) == ["IS 8034:1974"], (
            f"a saved index must be queryable from a fresh process; got {out.stdout!r}"
        )


class TestTokenize:
    def test_keeps_designations_intact(self):
        assert "is-14220" in tokenize("IS-14220 concrete")

    def test_strips_stopwords_and_accents(self):
        tokens = tokenize("The café and the résumé")
        assert "the" not in tokens and "and" not in tokens
        assert "cafe" in tokens and "resume" in tokens

    def test_folds_plural_but_keeps_es_endings(self):
        assert "pump" in tokenize("pumps")
        assert "requirement" in tokenize("requirements")
        assert "alloy" in tokenize("alloys")
        assert "class" in tokenize("class")
        assert "analysis" in tokenize("analysis")

    def test_singular_and_plural_queries_match_the_same_document(self):
        rec = merge(from_portal_rows(
            [{"is_number": "IS 8034:1974", "title": "Submersible pumps for irrigation"}]))[0]
        index = SearchIndex(dim=1 << 12).build([rec])
        assert index.search("submersible pump", k=1)[0].designation == "IS 8034:1974"
        assert index.search("submersible pumps", k=1)[0].designation == "IS 8034:1974"

    def test_empty(self):
        assert tokenize("") == []


class TestOutputs:
    def test_writes_json_jsonl_csv(self, tmp_path):
        records = merge(from_archive_items([make_archive_item()]))
        paths = write_outputs(records, tmp_path)

        assert set(paths) == {"json", "jsonl", "csv"}
        for path in paths.values():
            assert path.exists() and path.stat().st_size > 0

        rows = [json.loads(line) for line in
                paths["jsonl"].read_text().strip().splitlines()]
        assert rows[0]["designation"] == "IS 11367:1985"

        df = to_dataframe(records)
        assert "canonical" in df.columns and "is_current" in df.columns

    def test_xlsx_is_opt_in(self, tmp_path):
        records = merge(from_archive_items([make_archive_item()]))
        assert "xlsx" not in write_outputs(records, tmp_path)


class TestJsonlRoundtrip:
    def test_rehydrate_serialised_items(self, tmp_path):
        from bis_pipeline.archive_scraper import scrape
        from bis_pipeline.http import HttpClient, RetryPolicy
        from conftest import FakeResponse, FakeSession, NoSleep, fixture

        session = FakeSession({
            "advancedsearch": FakeResponse(200, fixture("advancedsearch_page0.json").encode()),
            "metadata/gov.in.is.11367.1985": FakeResponse(
                200, fixture("item_gov_in_is_11367_1985.json").encode()),
            "metadata/gov.in.is.12970.3.2.1992": FakeResponse(500, b""),
            "metadata/gov.in.is.104.1979": FakeResponse(500, b""),
            "_djvu.txt": FakeResponse(200, fixture("is.11367.1985_djvu.txt").encode()),
        })
        client = HttpClient(session=session, sleep=NoSleep(), min_interval=0.0,
                            policy=RetryPolicy(attempts=2))
        scrape(client, tmp_path, max_items=1)

        items = archive_items_from_jsonl(tmp_path / "items.jsonl")
        assert len(items) == 1
        assert items[0].designation.format() == "IS 11367:1985"
        assert items[0].division == "Textiles"
        assert items[0].best_text_file().name == "is.11367.1985_djvu.txt"
