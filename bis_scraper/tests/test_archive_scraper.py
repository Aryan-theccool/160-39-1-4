"""Tests for the archive.org scraper, driven by captured real API payloads."""

import json

from bis_pipeline.archive_scraper import (
    fetch_text,
    get_item,
    iter_collection,
    parse_description_fields,
    parse_item,
    scrape,
)
from bis_pipeline.http import HttpClient, HttpError, RetryPolicy

from conftest import FakeResponse, FakeSession, NoSleep, fixture, fixture_json


def make_client(session) -> HttpClient:
    return HttpClient(session=session, sleep=NoSleep(), min_interval=0.0,
                      policy=RetryPolicy(attempts=2))


class TestParseItem:
    def test_real_item_metadata(self):
        item = parse_item(fixture_json("item_gov_in_is_11367_1985.json"))

        assert item.identifier == "gov.in.is.11367.1985"
        assert item.title.startswith("IS 11367:")
        assert item.creator == "Bureau of Indian Standards"
        assert item.license_url == "http://creativecommons.org/publicdomain/zero/1.0/"
        assert "Right to Information Act 2005" in item.rights
        assert item.downloads == 412

    def test_designation_derived_from_identifier(self):
        item = parse_item(fixture_json("item_gov_in_is_11367_1985.json"))
        assert item.designation.format() == "IS 11367:1985"

    def test_public_item_is_not_restricted(self):
        item = parse_item(fixture_json("item_gov_in_is_11367_1985.json"))
        assert item.is_access_restricted is False

    def test_restricted_lending_item_is_detected(self):
        """The BIS 2005 catalogue is gated; every content derivative is private.

        This is the item the original plan tried to download and OCR. It must be
        detected and skipped rather than retried until it 401s forever.
        """
        item = parse_item(fixture_json("item_bis2005_restricted.json"))
        assert item.is_access_restricted is True
        assert item.designation is None, "not a gov.in.is.* item"

    def test_best_text_file_prefers_djvu_txt(self):
        item = parse_item(fixture_json("item_gov_in_is_11367_1985.json"))
        chosen = item.best_text_file()
        assert chosen.name == "is.11367.1985_djvu.txt"
        assert chosen.size == 24585
        assert chosen.md5 == "43a368478b7fe507f24d043b17bd37d8"
        assert chosen.url.endswith("/download/gov.in.is.11367.1985/is.11367.1985_djvu.txt")

    def test_private_files_are_never_chosen(self):
        item = parse_item(fixture_json("item_bis2005_restricted.json"))
        assert item.best_text_file() is None
        assert item.best_pdf_file() is None


class TestDescriptionFields:
    """The structured committee/amendment data lives in `description`, glued
    together with no separator between a value and the next label."""

    def test_real_description(self):
        desc = parse_item(fixture_json("item_gov_in_is_11367_1985.json")).description
        fields = parse_description_fields(desc)

        assert fields["division name"] == "Textiles"
        assert fields["section name"] == "Textile Materials for Aerospace Purposes (TXD 13)"
        assert fields["designator of legally binding document"] == "IS 11367"
        assert fields["number of amendments"] == "1"

    def test_survives_greedy_values_and_empty_trailers(self):
        desc = ("...12 Tables of Code)Name of Standards Organization: Bureau of Indian "
                "Standards (BIS)Division Name: TextilesSection Name: Textile Materials "
                "for Aerospace Purposes (TXD 13)Number of Amendments: 1Equivalence: "
                "Superceding: Superceded by: LEGALLY BINDING DOCUMENT")
        fields = parse_description_fields(desc)

        assert fields["name of standards organization"] == "Bureau of Indian Standards (BIS)"
        assert fields["equivalence"] == ""
        assert fields["superceding"] == ""
        assert fields["superceded by"] == "LEGALLY BINDING DOCUMENT"

    def test_empty_description(self):
        assert parse_description_fields("")["division name"] == ""

    def test_committee_code_is_recovered(self):
        item = parse_item(fixture_json("item_gov_in_is_11367_1985.json"))
        assert "(TXD 13)" in item.section
        assert item.number_of_amendments == 1


class TestIterCollection:
    def test_uses_identifier_scoping_and_paginates(self):
        def responder(method, url, kwargs):
            assert "identifier:gov.in.is.*" in kwargs["params"]["q"]
            return FakeResponse(200, fixture("advancedsearch_page0.json").encode())

        session = FakeSession({"advancedsearch": responder})
        client = make_client(session)

        docs = list(iter_collection(client, max_items=3))
        assert [d["identifier"] for d in docs] == [
            "gov.in.is.11367.1985", "gov.in.is.12970.3.2.1992", "gov.in.is.104.1979",
        ]

    def test_requests_all_needed_fields(self):
        def responder(method, url, kwargs):
            assert "description" in kwargs["params"]["fl[]"]
            return FakeResponse(200, fixture("advancedsearch_page0.json").encode())

        session = FakeSession({"advancedsearch": responder})
        list(iter_collection(make_client(session), max_items=1))


class TestFetchText:
    def test_returns_text_for_public_item(self):
        text = fixture("is.11367.1985_djvu.txt")
        session = FakeSession({"_djvu.txt": FakeResponse(200, text.encode())})
        item = parse_item(fixture_json("item_gov_in_is_11367_1985.json"))

        assert fetch_text(make_client(session), item) == text

    def test_401_is_treated_as_restricted_not_fatal(self):
        session = FakeSession({"_djvu.txt": FakeResponse(401, b"Authorization Required")})
        item = parse_item(fixture_json("item_gov_in_is_11367_1985.json"))
        item.files[4].private = False  # force selection of the gated file

        assert fetch_text(make_client(session), item) is None

    def test_no_text_derivative(self):
        item = parse_item(fixture_json("item_bis2005_restricted.json"))
        assert fetch_text(make_client(FakeSession()), item) is None


class TestScrapeEndToEnd:
    def _session(self):
        text = fixture("is.11367.1985_djvu.txt")
        return FakeSession({
            "advancedsearch": FakeResponse(200, fixture("advancedsearch_page0.json").encode()),
            "metadata/gov.in.is.11367.1985": FakeResponse(
                200, fixture("item_gov_in_is_11367_1985.json").encode()),
            "metadata/gov.in.is.12970.3.2.1992": FakeResponse(
                200, fixture("item_bis2005_restricted.json").encode()),
            "metadata/gov.in.is.104.1979": FakeResponse(500, b"boom"),
            "_djvu.txt": FakeResponse(200, text.encode()),
        })

    def test_writes_jsonl_and_text_and_skips_gated(self, tmp_path):
        client = make_client(self._session())
        items = scrape(client, tmp_path, max_items=3)

        # 1 public item kept, 1 restricted skipped, 1 metadata failure logged.
        assert [i.identifier for i in items] == ["gov.in.is.11367.1985"]
        assert (tmp_path / "text" / "gov.in.is.11367.1985.txt").exists()

        lines = (tmp_path / "items.jsonl").read_text().strip().splitlines()
        record = json.loads(lines[0])
        assert record["designation"] == "IS 11367:1985"
        assert record["designation_canonical"] == "IS|11367|None|None|1985|None"
        assert record["division"] == "Textiles"

    def test_is_resumable(self, tmp_path):
        scrape(make_client(self._session()), tmp_path, max_items=3)
        session2 = self._session()
        items = scrape(make_client(session2), tmp_path, max_items=3)

        assert items == [], "a resumed run must not re-process known items"
        assert session2.count("metadata/gov.in.is.11367.1985") == 0
