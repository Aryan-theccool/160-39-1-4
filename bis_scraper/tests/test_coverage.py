"""Tests for the QCO coverage report.

The question this answers: of the standards BIS says you must comply with,
which are already free to index (CC0 archive.org corpus) and which need
registration at standardsbis.bsbedge.com.
"""

import csv
import json

import pytest

from bis_pipeline import cli
from bis_pipeline.cli import main
from bis_pipeline.coverage import (
    build_corpus_index,
    report,
    summarise,
    write_report,
    CoverageRow,
)
from bis_pipeline.http import HttpClient, RetryPolicy
from bis_pipeline.iscode import parse_designation
from bis_pipeline.mandatory import MandatoryStandard

from conftest import FakeResponse, FakeSession, NoSleep


def make_client(session) -> HttpClient:
    return HttpClient(session=session, sleep=NoSleep(), min_interval=0.0,
                      policy=RetryPolicy(attempts=2))


def corpus_page(identifiers, num_found=None):
    payload = {
        "response": {
            "numFound": num_found if num_found is not None else len(identifiers),
            "docs": [{"identifier": i} for i in identifiers],
        }
    }
    return FakeResponse(200, json.dumps(payload).encode())


CORPUS = [
    "gov.in.is.10500.2012",   # drinking water, current
    "gov.in.is.10500.1991",   # drinking water, older edition
    "gov.in.is.8034.1974",    # submersible pumps
    "gov.in.is.14220.2002",   # pump sets
]


def ms(code, product=""):
    return MandatoryStandard(designation=parse_designation(code),
                             title=product, product_category=product, scheme="Scheme-I")


class TestBuildCorpusIndex:
    def test_groups_editions_under_one_key(self):
        session = FakeSession({"advancedsearch": corpus_page(CORPUS)})
        index = build_corpus_index(make_client(session))

        assert set(index) == {
            "IS|10500|None|None", "IS|8034|None|None", "IS|14220|None|None",
        }
        assert index["IS|10500|None|None"] == [
            "gov.in.is.10500.1991", "gov.in.is.10500.2012",
        ]

    def test_non_scheme_identifiers_are_skipped(self):
        session = FakeSession({"advancedsearch": corpus_page(
            CORPUS + ["bis2005completec0000vari", "gov.in.is.abc"])})
        index = build_corpus_index(make_client(session))
        assert len(index) == 3, "restricted/non-IS items must not pollute the index"

    def test_paginates_until_num_found(self):
        pages = [corpus_page(CORPUS[:2], num_found=4), corpus_page(CORPUS[2:], num_found=4)]
        state = {"n": 0}

        def responder(method, url, kwargs):
            page = pages[min(state["n"], len(pages) - 1)]
            state["n"] += 1
            return page

        session = FakeSession({"advancedsearch": responder})
        index = build_corpus_index(make_client(session), page_size=2)
        assert len(index) == 3
        assert session.count("advancedsearch") == 2


class TestReport:
    def test_matches_ignore_the_year(self):
        """A QCO citing IS 10500:2012 is satisfied by any edition we hold."""
        session = FakeSession({"advancedsearch": corpus_page(CORPUS)})
        index = build_corpus_index(make_client(session))

        rows = report([ms("IS 10500:2012", "Drinking water")], index)
        assert rows[0].held is True
        assert rows[0].best_match == "gov.in.is.10500.2012", "newest edition first"

    def test_missing_standard_is_reported_not_dropped(self):
        session = FakeSession({"advancedsearch": corpus_page(CORPUS)})
        index = build_corpus_index(make_client(session))

        rows = report([ms("IS 17440:2020", "Carbon black")], index)
        assert rows[0].held is False
        assert rows[0].matches == ()
        assert rows[0].product == "Carbon black"

    def test_part_numbers_must_match(self):
        """IS 15844 (Part 1) is not the same standard as IS 15844 (Part 2)."""
        session = FakeSession({"advancedsearch": corpus_page(["gov.in.is.15844.1.2023"])})
        index = build_corpus_index(make_client(session))

        assert report([ms("IS 15844 (Part 1):2023")], index)[0].held is True
        assert report([ms("IS 15844 (Part 2):2023")], index)[0].held is False

    def test_duplicate_rows_are_collapsed(self):
        session = FakeSession({"advancedsearch": corpus_page(CORPUS)})
        index = build_corpus_index(make_client(session))
        rows = report([ms("IS 8034:1974", "Pumps"), ms("IS 8034:1974", "Pumps")], index)
        assert len(rows) == 1

    def test_summarise(self):
        rows = [
            CoverageRow("IS 10500:2012", "IS|10500|None|None", "water", "I", ("a",)),
            CoverageRow("IS 8034:1974", "IS|8034|None|None", "pumps", "I", ("b",)),
            CoverageRow("IS 17440:2020", "IS|17440|None|None", "carbon", "I", ()),
        ]
        stats = summarise(rows)
        assert stats == {"qco_standards": 3, "held_in_cc0_corpus": 2, "not_held": 1,
                         "coverage_pct": 66.7, "rows": 3}

    def test_summarise_on_empty_input(self):
        assert summarise([])["coverage_pct"] == 0.0


class TestWriteReport:
    def test_splits_held_and_missing(self, tmp_path):
        rows = [
            CoverageRow("IS 10500:2012", "k1", "Drinking water", "I",
                        ("gov.in.is.10500.2012",)),
            CoverageRow("IS 17440:2020", "k2", "Carbon black", "I", ()),
        ]
        paths = write_report(rows, tmp_path)

        held = list(csv.DictReader(open(paths["qco_held"], encoding="utf-8")))
        missing = list(csv.DictReader(open(paths["qco_missing"], encoding="utf-8")))

        assert [r["designation"] for r in held] == ["IS 10500:2012"]
        assert held[0]["archive_url"] == "https://archive.org/details/gov.in.is.10500.2012"
        assert [r["designation"] for r in missing] == ["IS 17440:2020"]
        assert missing[0]["archive_url"] == ""


class TestCoverageCommand:
    def _seed(self, tmp_path, codes):
        (tmp_path / "mandatory").mkdir()
        (tmp_path / "mandatory" / "mandatory.json").write_text(json.dumps([
            {"designation": c, "canonical": "c", "title": c, "product_category": c,
             "scheme": "Scheme-I", "source_url": "u"} for c in codes
        ]))

    def test_end_to_end(self, tmp_path, monkeypatch, capsys):
        self._seed(tmp_path, ["IS 10500:2012", "IS 8034:1974", "IS 17440:2020"])

        from test_cli import fake_client_factory
        session = FakeSession({"advancedsearch": corpus_page(CORPUS)})
        monkeypatch.setattr(cli, "build_client", fake_client_factory(session))

        assert main(["--data-dir", str(tmp_path), "coverage"]) == 0

        out = capsys.readouterr().out
        assert "already free (CC0)     : 2" in out
        assert "need registration      : 1" in out
        assert "standardsbis.bsbedge.com" in out
        assert (tmp_path / "coverage" / "qco_held.csv").exists()
        assert (tmp_path / "coverage" / "qco_missing.csv").exists()

    def test_requires_mandatory_first(self, tmp_path, capsys):
        assert main(["--data-dir", str(tmp_path), "coverage"]) == 1
        assert "run `mandatory` first" in capsys.readouterr().out
