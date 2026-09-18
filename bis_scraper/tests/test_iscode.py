"""Tests for the IS designation grammar.

These are regression tests for real OCR strings found in the corpus. Each one
below has been seen in an actual ``gov.in.is.*`` ``_djvu.txt``.
"""

import pytest

from bis_pipeline.iscode import (
    designation_from_identifier,
    find_all,
    parse_designation,
)


class TestParse:
    @pytest.mark.parametrize("raw,expected", [
        ("IS 14220", "IS 14220"),
        ("IS 14220 : 1994", "IS 14220:1994"),
        ("IS 14220:1994", "IS 14220:1994"),
        ("IS 616:2017", "IS 616:2017"),
        ("SP 7 : 2026", "SP 7:2026"),
        ("IS 11367 (1985)", "IS 11367:1985"),
        ("IS/IEC 61730-1 : 2012", "IS/IEC 61730 (Part 1):2012"),
        ("IS 15844 (Part 1) : 2023", "IS 15844 (Part 1):2023"),
        ("IS 10322 (Part 5 / Section 9) : 2017", "IS 10322 (Part 5 / Section 9):2017"),
        ("IS 4503 (Part 1) : 2001 (Reaffirmed 2012)", "IS 4503 (Part 1):2001 (Reaffirmed 2012)"),
    ])
    def test_accepted(self, raw, expected):
        result = parse_designation(raw)
        assert result is not None, f"{raw!r} should parse"
        assert result.format() == expected

    @pytest.mark.parametrize("raw,expected", [
        # Dash chains and paren chains are two spellings of one thing.
        ("IS 302-2-15 : 2009", "IS 302 (Part 2 / Section 15):2009"),
        ("IS 12970-3-2 : 1992", "IS 12970 (Part 3 / Section 2):1992"),
        ("IS 302-2 (Section 9)", "IS 302 (Part 2 / Section 9)"),
    ])
    def test_chains(self, raw, expected):
        result = parse_designation(raw)
        assert result is not None
        assert result.format() == expected

    def test_dash_and_paren_forms_share_a_key(self):
        a = parse_designation("IS 302-2-15 : 2009")
        b = parse_designation("is 302 (part 2 / section 15):2009")
        assert a.canonical == b.canonical == "IS|302|2|15|2009|None"

    def test_bare_year_after_dash_is_a_year_not_a_part(self):
        # The single most common cross-reference form in the corpus.
        result = parse_designation("IS 232-1985")
        assert result.part is None
        assert result.year == 1985
        assert result.format() == "IS 232:1985"

    def test_section_keyword_is_not_a_part(self):
        result = parse_designation("IS 302 (Section 2)")
        assert result.part is None
        assert result.section == 2

    @pytest.mark.parametrize("raw", [
        "IS 1 113C7 - 1905",   # OCR corruption of IS 11367:1985
        "IS : 11367 . IMS",    # OCR corruption, same standard
        "hello world",
        "IS 11367 : 9999",     # implausible year
        "IS 302 (Part 2) 302-2",
        "IS 14220:1994 (1994)",  # contradictory year readings
        "",
        "   ",
    ])
    def test_rejected(self, raw):
        assert parse_designation(raw) is None, f"{raw!r} must not parse"


class TestGrouping:
    def test_editions_group_but_stay_distinct(self):
        a, b = parse_designation("IS 14220:1994"), parse_designation("IS 14220:2002")
        assert a.key_without_year == b.key_without_year
        assert a.canonical != b.canonical

    def test_reaffirmation_does_not_split_editions(self):
        a = parse_designation("IS 4503 (Part 1) : 2001")
        b = parse_designation("IS 4503 (Part 1) : 2001 (Reaffirmed 2012)")
        assert a.key_without_year == b.key_without_year


class TestIdentifiers:
    @pytest.mark.parametrize("identifier,expected", [
        ("gov.in.is.11367.1985", "IS 11367:1985"),
        ("gov.in.is.12970.3.2.1992", "IS 12970 (Part 3 / Section 2):1992"),
        ("gov.in.is.104.1979", "IS 104:1979"),
    ])
    def test_derived(self, identifier, expected):
        assert designation_from_identifier(identifier).format() == expected

    @pytest.mark.parametrize("identifier", [
        "gov.in.is.abc", "randomid", "", "gov.in.is.", "bis2005completec0000vari",
    ])
    def test_non_scheme_returns_none(self, identifier):
        assert designation_from_identifier(identifier) is None


class TestFindAll:
    def test_extracts_cross_references_from_a_foreword(self):
        text = (
            "0.3 The following Indian Standards may be referred to :\n"
            "IS : 232-1985 Glossary of textile terms - natural fibres\n"
            "IS : 1324-1966 Glossary of textile terms\n"
            "IS : 9603-1980 Glossary of terms pertaining to textile processing\n"
        )
        assert [d.format() for d in find_all(text)] == [
            "IS 232:1985", "IS 1324:1966", "IS 9603:1980",
        ]

    def test_does_not_invent_codes_from_corrupted_ocr(self):
        # `IS 1 113C7 - 1905` is OCR damage. A scanner must not report `IS 1`.
        assert find_all("IS 1 113C7 - 1905") == []

    def test_still_finds_genuinely_short_codes(self):
        assert [d.format() for d in find_all("see IS 1 and IS 2 : 1970")] == ["IS 1", "IS 2:1970"]

    def test_empty(self):
        assert find_all("") == []
