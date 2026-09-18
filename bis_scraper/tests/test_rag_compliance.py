"""Tests for the compliance checker (Part 4).

Two things these tests deliberately do *not* do, because doing them would make
the suite pass while the feature is wrong:

* they do not assert against :data:`~bis_rag.compliance.SEED_QCO` as if it were
  legal data. The seed list is unverified by construction, so what gets tested
  is the *mechanism* -- tier selection, matching, scoring, the mandatory-missing
  cap -- plus the guard that an unverified list cannot yield "fully compliant".
* they do not assert that a mandatory standard is present in the local dataset
  implies compliance, because the dataset holds a subset of BIS's catalogue.

The tests that matter most are
:func:`test_missing_mandatory_caps_the_grade` (compliance is a conjunction) and
:func:`test_seed_data_cannot_claim_full_compliance` (an incomplete list cannot
prove completeness).
"""

from __future__ import annotations

import json

import pytest

from bis_rag.compliance import (
    SEED_QCO,
    SECTOR_RULES,
    ComplianceChecker,
    ComplianceReport,
    QCODatabase,
    QCOEntry,
    _SECTOR_KEYWORDS,
    _yearless_key,
    detect_sector,
    render_html,
)
from bis_rag.data import BisData

from synth_bis_data import make_synth_data


@pytest.fixture(scope="module")
def data_root(tmp_path_factory):
    return make_synth_data(tmp_path_factory.mktemp("bis_data"))


@pytest.fixture(scope="module")
def data(data_root) -> BisData:
    return BisData(data_root)


@pytest.fixture
def checker(data) -> ComplianceChecker:
    """Checker using whatever QCO tier this data directory supports.

    The synthetic corpus carries real ``is_compulsory`` flags, so this resolves
    to tier 2 (``merged``) -- which is the correct behaviour and what the
    integration tests should exercise.
    """
    return ComplianceChecker(data)


@pytest.fixture
def seed_checker(data) -> ComplianceChecker:
    """Checker forced onto tier 3 (the unverified seed list).

    Constructed explicitly rather than by removing files: the point is to pin
    the *behaviour* of the seed tier, and reaching it by deleting data would
    make the test depend on fixture internals.
    """
    return ComplianceChecker(data, QCODatabase(None))


@pytest.fixture
def scraped_data(tmp_path, data_root):
    """A data directory carrying a scraped mandatory.json (tier 1)."""
    import shutil

    root = tmp_path / "with_mandatory"
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(data_root, root)
    (root / "mandatory").mkdir(parents=True, exist_ok=True)
    (root / "mandatory" / "mandatory.json").write_text(json.dumps([
        {"designation": "IS 269:2015", "canonical": "IS|269|None|None|2015|None",
         "title": "ordinary Portland cement", "scheme": "Cement QCO",
         "source_url": "https://www.bis.gov.in/example"},
        {"designation": "IS 1786:2008", "canonical": "IS|1786|None|None|2008|None",
         "title": "deformed steel bars", "scheme": "Steel QCO",
         "source_url": "https://www.bis.gov.in/example2"},
    ]), encoding="utf-8")
    return BisData(root)


# ----------------------------------------------------------------------
# key normalisation
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("IS 269:1989", "is 269"),
    ("is 269", "is 269"),
    ("IS|269|None|None|1989|None", "is 269"),
    ("IS|302|2|None|2009|None", "is 302 (part 2)"),
    ("IS 456:2000", "is 456"),
])
def test_yearless_key_matches_every_shape(text, expected):
    assert _yearless_key(text) == expected


def test_matching_ignores_the_edition():
    """A QCO names a standard, not a year: IS 269 covers whichever edition."""
    db = QCODatabase(None)
    assert db.is_mandatory("IS 269:1989")
    assert db.is_mandatory("IS 269:2015")
    assert db.is_mandatory("IS|269|None|None|2015|None")


def test_unknown_standard_is_not_mandatory():
    db = QCODatabase(None)
    assert db.lookup("IS 99999:2020") is None


# ----------------------------------------------------------------------
# provenance tiers
# ----------------------------------------------------------------------
def test_seed_database_is_marked_unverified():
    db = QCODatabase(None)
    assert db.source == "seed"
    assert db.verified is False
    assert len(db) == len(SEED_QCO)
    assert all(not entry.verified for entry in db.entries.values())
    assert all(entry.qco_year is None for entry in db.entries.values()), \
        "seed entries must not carry notification years we cannot attribute"


def test_scraped_data_wins_over_the_seed_list(scraped_data):
    db = QCODatabase(scraped_data)
    assert db.source == "scraped"
    assert db.verified is True
    entry = db.lookup("IS 269")
    assert entry is not None and entry.verified
    assert entry.source_url.startswith("https://www.bis.gov.in/")


def test_merged_flags_are_used_when_mandatory_json_is_absent(data):
    """Tier 2: a data dir whose merged_standards carry is_compulsory."""
    db = QCODatabase(data)
    assert db.source == "merged"
    assert db.verified is True
    assert db.lookup("IS 269") is not None


# ----------------------------------------------------------------------
# sector detection
# ----------------------------------------------------------------------
@pytest.mark.parametrize("description,sector", [
    ("portable submersible pumpset for borewell water", "mechanical"),
    ("PVC insulated electrical cable for household wiring", "electrical"),
    ("bottle of packaged drinking water", "water_supply"),
    ("ordinary portland cement for concrete", "construction"),
    ("TMT steel bar for reinforcement", "construction"),
])
def test_sector_detection(description, sector):
    assert detect_sector(description)[0] == sector


def test_unclassifiable_description_returns_none():
    """No sector is a real answer -- callers must not get a defaulted one."""
    assert detect_sector("a completely unrelated thingamajig") == (None, {})


def test_sector_keywords_belong_to_exactly_one_sector():
    """Overlapping keywords made detection a coin flip before."""
    from collections import Counter

    flat = [k for keywords in _SECTOR_KEYWORDS.values() for k in keywords]
    duplicates = {k for k, n in Counter(flat).items() if n > 1}
    assert not duplicates, f"keyword(s) claimed by two sectors: {sorted(duplicates)}"


def test_sector_rules_reference_real_standard_numbers():
    """Sector hints must be parseable, so they can be resolved or reported missing."""
    from bis_pipeline.iscode import parse_designation

    for sector, numbers in SECTOR_RULES.items():
        for number in numbers:
            assert parse_designation(number) is not None, f"{sector}: {number!r}"


def test_explicit_sector_overrides_detection(checker):
    report = checker.analyze("a vague product", ["IS 269"], sector="electrical")
    assert report.sector == "electrical"


# ----------------------------------------------------------------------
# mandatory present / missing
# ----------------------------------------------------------------------
def test_missing_mandatory_is_detected(checker):
    """A mandatory standard for the product that is not in the supplied list."""
    report = checker.analyze("ordinary portland cement", ["IS 269:1989"])
    assert "IS 269" in report.mandatory_expected[0].designation.upper() or \
        any("269" in e.designation for e in report.mandatory_expected)
    assert report.mandatory_present, "IS 269 was supplied and is mandatory"
    assert not any("269" in m for m in report.mandatory_missing)


def test_missing_mandatory_appears_when_absent(checker):
    """Supplying an unrelated standard leaves the product's QCO unmet."""
    report = checker.analyze("33 grade ordinary Portland cement", ["IS 1786:2008"])
    assert any("269" in m for m in report.mandatory_missing)
    assert any("Obtain and comply with" in a for a in report.action_items)


def test_mandatory_present_and_missing_are_disjoint(checker):
    report = checker.analyze("submersible pumpset", ["IS 14220:2000"])
    assert not set(report.mandatory_present) & set(report.mandatory_missing)


# ----------------------------------------------------------------------
# superseded editions
# ----------------------------------------------------------------------
def test_superseded_standard_reports_its_replacement(checker):
    report = checker.analyze("plain and reinforced concrete", ["IS 456:1978"])
    assert report.superseded_used
    item = report.superseded_used[0]
    assert item["used"] == "IS 456:1978"
    assert item["replace_with"] == "IS 456:2000"
    assert item["replacement_in_dataset"] is True
    assert any("Replace IS 456:1978 with IS 456:2000" in a for a in report.action_items)


def test_current_edition_produces_no_supersession_warning(checker):
    report = checker.analyze("plain and reinforced concrete", ["IS 456:2000"])
    assert report.superseded_used == []


# ----------------------------------------------------------------------
# conflicts
# ----------------------------------------------------------------------
def test_two_editions_of_one_standard_conflict(checker):
    report = checker.analyze("concrete", ["IS 456:1978", "IS 456:2000"])
    types = {c["type"] for c in report.conflicts}
    assert "multiple_editions" in types
    conflict = next(c for c in report.conflicts if c["type"] == "multiple_editions")
    assert "1978" in conflict["standards"] and "2000" in conflict["standards"]


def test_distinct_standards_do_not_conflict(checker):
    report = checker.analyze("concrete", ["IS 456:2000", "IS 1786:2008"])
    assert report.conflicts == []


# ----------------------------------------------------------------------
# scoring and grading
# ----------------------------------------------------------------------
def test_score_is_bounded_and_weights_sum_to_one(checker):
    report = checker.analyze("ordinary portland cement", ["IS 269:2015"])
    assert 0.0 <= report.compliance_score <= 1.0
    assert abs(sum(report.weights.values()) - 1.0) < 1e-9


def test_all_mandatory_present_and_current_scores_highest(checker):
    good = checker.analyze("ordinary portland cement", ["IS 269:2015"])
    bad = checker.analyze("ordinary portland cement", ["IS 1239:2004"])
    assert good.compliance_score > bad.compliance_score


def test_missing_mandatory_caps_the_grade(checker):
    """Compliance is a conjunction: missing one mandatory standard is a fail."""
    report = checker.analyze("ordinary portland cement", ["IS 1786:2008"])
    assert report.mandatory_missing
    assert report.grade != "FULLY COMPLIANT"
    assert report.grade != "MOSTLY COMPLIANT"
    assert report.grade_capped_by
    assert "mandatory" in report.grade_capped_by.lower()
    assert "PARTIALLY COMPLIANT" in report.grade_capped_by


@pytest.mark.parametrize("score,expected", [
    (1.00, "FULLY COMPLIANT"),
    (0.90, "FULLY COMPLIANT"),
    (0.89, "MOSTLY COMPLIANT"),
    (0.70, "MOSTLY COMPLIANT"),
    (0.69, "PARTIALLY COMPLIANT"),
    (0.50, "PARTIALLY COMPLIANT"),
    (0.49, "NON-COMPLIANT"),
    (0.00, "NON-COMPLIANT"),
])
def test_grade_bands_are_applied_at_the_boundaries(checker, score, expected):
    report = ComplianceReport(product_description="x")
    report.compliance_score = score
    report.mandatory_expected = [QCOEntry(key="is 1", designation="IS 1")]
    report.mandatory_present = ["IS 1"]     # so the cap does not interfere
    assert checker._grade(report) == expected


def test_no_mandatory_identified_redistributes_weights_rather_than_scoring_zero(checker):
    """0/0 must not read as 'non-compliant' -- it means 'no QCO row for this'."""
    report = checker.analyze("a completely unrelated thingamajig", [])
    assert report.total_mandatory == 0
    assert report.weights_redistributed is True
    assert report.weights["mandatory"] == 0.0
    assert abs(sum(report.weights.values()) - 1.0) < 1e-9
    assert report.grade != "NON-COMPLIANT" or not report.standards
    assert any("redistributed" in n for n in report.notes)


def test_seed_data_cannot_claim_full_compliance(seed_checker):
    """An unverified, possibly incomplete list cannot prove completeness."""
    assert seed_checker.qco.verified is False
    report = seed_checker.analyze("ordinary portland cement", ["IS 269:2015"])
    assert report.grade != "FULLY COMPLIANT"
    assert report.grade_capped_by
    assert "seed" in report.grade_capped_by


def test_scraped_data_may_grade_fully_compliant(scraped_data):
    checker = ComplianceChecker(scraped_data)
    assert checker.qco.verified is True
    report = checker.analyze("cement", ["IS 269:2015"])
    assert report.qco_verified is True
    assert report.grade in ("FULLY COMPLIANT", "MOSTLY COMPLIANT")


# ----------------------------------------------------------------------
# report shape and HTML
# ----------------------------------------------------------------------
def test_report_dict_matches_the_agreed_shape(checker):
    report = checker.analyze("ordinary portland cement", ["IS 269:1989"])
    payload = report.as_dict()
    for key in ("compliance_status", "mandatory_present", "mandatory_missing",
                "superseded_used", "compliance_score", "grade", "action_items",
                "qco_source", "qco_verified", "conflicts", "limitations"):
        assert key in payload, f"missing {key}"
    assert isinstance(payload["action_items"], list)
    assert json.dumps(payload)          # must be JSON-serialisable


def test_html_report_contains_the_required_sections(checker):
    report = checker.analyze("ordinary portland cement", ["IS 269:1989"])
    page = render_html(report)
    for heading in ("Executive summary", "Mandatory standards status",
                    "Superseded standards warning", "Action items", "References"
                    if False else "Limitations"):
        assert heading in page
    assert page.startswith("<!DOCTYPE html>")
    assert "</html>" in page.strip()


def test_html_report_escapes_caller_supplied_text(checker):
    """The product description is free text and is attacker-controlled on the web."""
    hostile = "<script>alert('xss')</script>"
    report = checker.analyze(hostile, ["IS 269:2015"])
    page = render_html(report)
    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page


def test_html_warns_when_running_on_seed_data(seed_checker):
    report = seed_checker.analyze("cement", ["IS 269:2015"])
    page = render_html(report)
    assert "Unverified mandatory list" in page
    assert "bis_pipeline mandatory" in page


def test_html_omits_the_seed_banner_on_scraped_data(scraped_data):
    report = ComplianceChecker(scraped_data).analyze("cement", ["IS 269:2015"])
    assert "Unverified mandatory list" not in render_html(report)


def test_limitations_are_always_stated(checker):
    """A verdict without its limitations invites over-trust."""
    report = checker.analyze("cement", ["IS 269:2015"])
    joined = " ".join(report.limitations).lower()
    assert "not legal advice" in joined
    assert "subset" in joined


# ----------------------------------------------------------------------
# RAG integration
# ----------------------------------------------------------------------
def test_compliance_answer_carries_a_compliance_block(data, tmp_path):
    from bis_rag.build_vector_store import BuildConfig, build
    from bis_rag.hybrid import HybridSearch, LexicalReranker
    from bis_rag.rag import ExtractiveGenerator, RAGPipeline

    store = tmp_path / "store"
    build(BuildConfig(data_dir=data.root, store_dir=store, backend="json",
                      embedder="hash", batch_size=8, verify=False))
    search = HybridSearch(data, store_dir=store, embedder="hash",
                          reranker=LexicalReranker())
    pipeline = RAGPipeline(data, search, generator=ExtractiveGenerator())
    answer = pipeline.answer("Is cement covered under mandatory BIS certification?",
                             top_k=4)
    assert answer.compliance is not None
    assert "grade" in answer.compliance
    assert "mandatory_missing" in answer.compliance
    assert answer.as_dict()["compliance"]["qco_source"] in ("seed", "merged", "scraped")


def test_non_compliance_answers_are_not_audited(data, tmp_path):
    """Scoring every topic query would add noise nobody asked for."""
    from bis_rag.build_vector_store import BuildConfig, build
    from bis_rag.hybrid import HybridSearch, LexicalReranker
    from bis_rag.rag import ExtractiveGenerator, RAGPipeline

    store = tmp_path / "store2"
    build(BuildConfig(data_dir=data.root, store_dir=store, backend="json",
                      embedder="hash", batch_size=8, verify=False))
    search = HybridSearch(data, store_dir=store, embedder="hash",
                          reranker=LexicalReranker())
    pipeline = RAGPipeline(data, search, generator=ExtractiveGenerator())
    answer = pipeline.answer("what is the maximum chloride limit?", top_k=3)
    assert answer.compliance is None


def test_ambiguous_product_description_asserts_nothing(seed_checker):
    """The same class of bug as the sector one, one level down.

    "ordinary portland cement" is IS 269 (33 grade), IS 8112 (43 grade) and
    IS 12269 (53 grade). Guessing would report two false compliance failures.
    """
    report = seed_checker.analyze("ordinary portland cement", [])
    assert report.mandatory_expected == []
    assert report.mandatory_missing == []
    assert len(report.mandatory_candidates) >= 2
    assert any("equally well" in n for n in report.notes)


@pytest.mark.parametrize("description,expected_number", [
    ("33 grade ordinary Portland cement", "269"),
    ("53 grade ordinary Portland cement", "12269"),
    ("rapid hardening Portland cement", "8041"),
])
def test_grade_in_the_description_disambiguates(seed_checker, description, expected_number):
    """Numbers survive tokenisation precisely so grades stay distinguishable."""
    report = seed_checker.analyze(description, [])
    assert [e.designation for e in report.mandatory_expected] == [f"IS {expected_number}"]


def test_weak_match_is_offered_not_asserted(seed_checker):
    """"electrical cable" shares one word with the IS 302 title; not identification."""
    report = seed_checker.analyze("electrical cable", [])
    assert report.mandatory_expected == []
    assert report.mandatory_candidates


def test_specific_description_asserts_its_match(seed_checker):
    report = seed_checker.analyze("household electrical appliance", [])
    assert [e.designation for e in report.mandatory_expected] == ["IS 302"]
    assert report.mandatory_candidates == []


def test_sector_entries_are_suggestions_not_missing_mandatory(seed_checker):
    """Regression: a sector list is not a product-specific requirement.

    Treating every sector QCO entry as "expected" claimed a cement product was
    failing 15 standards, including bricks (IS 1077) and flooring tiles (IS 6003).
    """
    report = seed_checker.analyze("ordinary portland cement", ["IS 269:2015"])
    assert report.mandatory_missing == []
    assert report.sector_candidates, "other construction QCOs should still be surfaced"
    assert not set(report.sector_candidates) & set(report.mandatory_missing)
    assert "IS 1077" in report.sector_candidates
    assert any("sector" in a.lower() and "worth checking" in a.lower()
               for a in report.action_items)


def test_sector_candidates_exclude_what_was_supplied(seed_checker):
    report = seed_checker.analyze("ordinary portland cement", ["IS 269:2015", "IS 383:2016"])
    # Exact comparison, not substring: "IS 12269" contains "269" and is a
    # different standard that legitimately remains a candidate.
    assert "IS 269" not in report.sector_candidates
    assert "IS 383" not in report.sector_candidates
    assert "IS 12269" in report.sector_candidates


def test_html_lists_sector_suggestions(seed_checker):
    report = seed_checker.analyze("ordinary portland cement", ["IS 269:2015"])
    page = render_html(report)
    assert "Sector suggestions" in page
    assert "product-specific requirement" in page


def test_merged_entries_get_a_sector_where_the_division_is_unambiguous(data):
    """Without this, sector suggestions silently return nothing on tier 2."""
    db = QCODatabase(data)
    assert db.source == "merged"
    sectors = {e.sector for e in db.entries.values()}
    assert "construction" in sectors          # Civil Engineering maps
    assert "electrical" in sectors            # Electrical maps
    assert "" in sectors                       # Chemical Engineering is not guessed
    assert db.for_sector("construction")


def test_ambiguous_divisions_are_not_guessed(data):
    """"Chemical Engineering" spans water and food; a wrong sector beats none."""
    from bis_rag.compliance import _DIVISION_TO_SECTOR

    assert "chemical engineering" not in _DIVISION_TO_SECTOR
    assert "textiles" not in _DIVISION_TO_SECTOR


def test_supplying_one_standard_many_times_yields_one_finding(checker):
    """Callers pass one entry per retrieved passage, not per standard."""
    report = checker.analyze("plain and reinforced concrete",
                             ["IS 456:1978"] * 5)
    assert len(report.superseded_used) == 1
    assert len(report.standards) == 1


def test_answer_warnings_are_not_repeated(data, tmp_path):
    from bis_rag.build_vector_store import BuildConfig, build
    from bis_rag.hybrid import HybridSearch, LexicalReranker
    from bis_rag.rag import ExtractiveGenerator, RAGPipeline

    store = tmp_path / "store3"
    build(BuildConfig(data_dir=data.root, store_dir=store, backend="json",
                      embedder="hash", batch_size=8, verify=False))
    search = HybridSearch(data, store_dir=store, embedder="hash",
                          reranker=LexicalReranker())
    pipeline = RAGPipeline(data, search, generator=ExtractiveGenerator())
    answer = pipeline.answer("Is cement covered under mandatory BIS certification?",
                            top_k=5)
    assert len(answer.warnings) == len(set(answer.warnings)), answer.warnings


def test_dedupe_keeps_distinct_editions_so_conflicts_still_surface(checker):
    """Deduping by the year-less key would hide the conflict it must detect."""
    report = checker.analyze("concrete", ["IS 456:1978", "IS 456:2000", "IS 456:1978"])
    assert len(report.standards) == 2
    assert any(c["type"] == "multiple_editions" for c in report.conflicts)
