"""Comprehensive Step QCO-3 Safety and Verification Integration Tests.

Validates:
A. VERIFIED QCO -> authoritative regulatory evidence allowed
B. SEED_UNVERIFIED -> cannot produce authoritative PASS
C. NOT_FOUND -> cannot produce authoritative PASS
D. AMBIGUOUS -> cannot produce authoritative PASS
E. SUPERSEDED_OR_CHANGED -> warning, not automatic current applicability
F. NOT_APPLICABLE -> correctly represented
G. Effective date handling (future vs past dates)
H. QCO source citation & statutory provenance
I. Product -> IS -> QCO relationship
J. Technical PASS + QCO UNKNOWN/UNVERIFIED must not become FULLY COMPLIANT
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from bis_rag.compliance import (
    ComplianceChecker,
    ComplianceReport,
    QCODatabase,
    QCOEntry,
    QCOEvidenceState,
    ResolvedStandard,
    SpecificationCheck,
)
from bis_rag.data import BisData
from synth_bis_data import make_synth_data


@pytest.fixture(scope="module")
def workspace_data_dir() -> Path:
    """Find data/qco_verified_database.json in the workspace."""
    cand = Path("data/qco_verified_database.json")
    if cand.exists():
        return cand
    cand2 = Path(__file__).resolve().parents[2] / "data" / "qco_verified_database.json"
    if cand2.exists():
        return cand2
    cand3 = Path(__file__).resolve().parents[3] / "data" / "qco_verified_database.json"
    if cand3.exists():
        return cand3
    raise FileNotFoundError("Could not find data/qco_verified_database.json")


@pytest.fixture(scope="module")
def verified_qco_db(workspace_data_dir) -> QCODatabase:
    """QCODatabase loaded directly from official verified database."""
    return QCODatabase(qco_path=workspace_data_dir)


@pytest.fixture(scope="module")
def synth_data(tmp_path_factory) -> BisData:
    root = make_synth_data(tmp_path_factory.mktemp("bis_data_qco"))
    return BisData(root)


# ==============================================================================
# A. VERIFIED QCO -> authoritative regulatory evidence allowed
# ==============================================================================
def test_verified_qco_authoritative_allowed(verified_qco_db):
    """33 verified records must be marked verified and authoritative."""
    assert verified_qco_db.source == "verified_db"
    assert verified_qco_db.verified is True
    assert len(verified_qco_db) == 44

    # IS 269 is verified ordinary portland cement
    entry_269 = verified_qco_db.lookup("IS 269")
    assert entry_269 is not None
    assert entry_269.evidence_state == QCOEvidenceState.VERIFIED
    assert entry_269.verified is True
    assert entry_269.is_effective is True
    assert entry_269.is_authoritative is True
    assert "S.O. 191(E)" in entry_269.notification_number
    assert "Ministry of Commerce and Industry" in entry_269.issuing_ministry


# ==============================================================================
# B. SEED_UNVERIFIED -> cannot produce authoritative PASS
# ==============================================================================
def test_seed_unverified_cannot_produce_authoritative_pass(synth_data):
    """Seed unverified entries must not be authoritative."""
    seed_db = QCODatabase(data=None)
    assert seed_db.source == "seed"
    assert seed_db.verified is False

    entry = seed_db.lookup("IS 269")
    assert entry is not None
    assert entry.evidence_state == QCOEvidenceState.SEED_UNVERIFIED
    assert entry.verified is False
    assert entry.is_authoritative is False

    checker = ComplianceChecker(synth_data, seed_db)
    report = checker.analyze("ordinary portland cement", ["IS 269:2015"])
    assert report.grade != "FULLY COMPLIANT"
    assert report.grade == "MOSTLY COMPLIANT"
    assert "unverified" in report.grade_capped_by.lower()


# ==============================================================================
# C. NOT_FOUND -> cannot produce authoritative PASS
# ==============================================================================
def test_not_found_cannot_produce_authoritative_pass(verified_qco_db):
    """NOT_FOUND entries (e.g. IS 1077, IS 4707) have no active QCO."""
    entry_1077 = verified_qco_db.lookup("IS 1077")
    assert entry_1077 is not None
    assert entry_1077.evidence_state == QCOEvidenceState.NOT_FOUND
    assert entry_1077.verified is False
    assert entry_1077.is_authoritative is False

    assert verified_qco_db.lookup_state("IS 99999") == QCOEvidenceState.NOT_FOUND


# ==============================================================================
# D. AMBIGUOUS -> cannot produce authoritative PASS
# ==============================================================================
def test_ambiguous_cannot_produce_authoritative_pass(verified_qco_db):
    """AMBIGUOUS entries (IS 1536) must remain non-authoritative."""
    entry_1536 = verified_qco_db.lookup("IS 1536")
    assert entry_1536 is not None
    assert entry_1536.evidence_state == QCOEvidenceState.AMBIGUOUS
    assert entry_1536.verified is False
    assert entry_1536.is_authoritative is False


# ==============================================================================
# E. SUPERSEDED_OR_CHANGED -> warning, not automatic current applicability
# ==============================================================================
def test_superseded_or_changed_handling(verified_qco_db):
    """IS 8112 and IS 12269 must show regulatory status changed pointing to IS 269."""
    entry_8112 = verified_qco_db.lookup("IS 8112")
    assert entry_8112 is not None
    assert entry_8112.evidence_state == QCOEvidenceState.SUPERSEDED_OR_CHANGED
    assert entry_8112.verified is False
    assert entry_8112.is_authoritative is False
    assert "IS 269:2015" in entry_8112.evidence_notes

    entry_12269 = verified_qco_db.lookup("IS 12269")
    assert entry_12269 is not None
    assert entry_12269.evidence_state == QCOEvidenceState.SUPERSEDED_OR_CHANGED
    assert entry_12269.verified is False
    assert entry_12269.is_authoritative is False
    assert "IS 269:2015" in entry_12269.evidence_notes


# ==============================================================================
# F. NOT_APPLICABLE -> correctly represented
# ==============================================================================
def test_not_applicable_correctly_represented(verified_qco_db):
    """Aggregates (IS 383), EMC test (IS 14700), pumps test (IS 5120), etc. are NOT_APPLICABLE."""
    for desig in ["IS 383", "IS 14700", "IS 5120", "IS 1479", "IS 7215", "IS 121"]:
        entry = verified_qco_db.lookup(desig)
        assert entry is not None, f"Expected {desig} in verified database"
        assert entry.evidence_state == QCOEvidenceState.NOT_APPLICABLE
        assert entry.verified is False
        assert entry.is_authoritative is False


# ==============================================================================
# G. Effective date handling
# ==============================================================================
def test_effective_date_handling():
    """Future effective dates are not authoritative until effective date arrives."""
    future_date = (date.today() + timedelta(days=90)).isoformat()
    past_date = (date.today() - timedelta(days=90)).isoformat()

    future_entry = QCOEntry(
        key="is 9999",
        designation="IS 9999",
        verified=True,
        evidence_state=QCOEvidenceState.VERIFIED,
        effective_date=future_date,
    )
    assert future_entry.is_effective is False
    assert future_entry.is_authoritative is False

    past_entry = QCOEntry(
        key="is 9998",
        designation="IS 9998",
        verified=True,
        evidence_state=QCOEvidenceState.VERIFIED,
        effective_date=past_date,
    )
    assert past_entry.is_effective is True
    assert past_entry.is_authoritative is True


# ==============================================================================
# H. QCO source citation & statutory provenance
# ==============================================================================
def test_qco_source_citation_and_fields(verified_qco_db):
    """Verified QCO entries must populate all statutory metadata fields."""
    entry = verified_qco_db.lookup("IS 694")
    assert entry is not None
    assert entry.evidence_state == QCOEvidenceState.VERIFIED
    assert entry.qco_title != ""
    assert entry.notification_number != ""
    assert entry.issuing_ministry != ""
    assert entry.notification_date != ""
    assert entry.effective_date != ""
    assert entry.source_document != ""
    assert entry.verification_date != ""


# ==============================================================================
# I. Product -> IS -> QCO relationship
# ==============================================================================
def test_product_is_qco_relationship(verified_qco_db):
    """Product matching correctly finds mandatory standards."""
    matched = verified_qco_db.for_product("ordinary portland cement")
    assert matched
    assert any("269" in e.designation for e in matched)


# ==============================================================================
# J. Technical PASS + QCO UNKNOWN/UNVERIFIED must not become FULLY COMPLIANT
# ==============================================================================
def test_technical_pass_with_unverified_qco_capped(synth_data):
    """Even if technical specs pass 100%, unverified QCO caps grade at MOSTLY COMPLIANT."""
    checker = ComplianceChecker(synth_data, QCODatabase(data=None))
    report = ComplianceReport(product_description="ordinary portland cement")
    report.compliance_score = 1.0
    report.mandatory_expected = [
        QCOEntry(key="is 269", designation="IS 269:2015", verified=False, evidence_state=QCOEvidenceState.SEED_UNVERIFIED)
    ]
    report.mandatory_present = ["IS 269:2015"]
    report.specification_checks = [
        SpecificationCheck(
            parameter="compressive_strength",
            product_value="43 MPa",
            required_value="33 MPa",
            operator="minimum",
            unit="MPa",
            status="PASS",
        )
    ]
    grade = checker._grade(report)
    assert grade != "FULLY COMPLIANT"
    assert grade == "MOSTLY COMPLIANT"
    assert "unverified" in report.grade_capped_by.lower()
