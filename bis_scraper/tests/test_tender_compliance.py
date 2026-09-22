"""Unit and integration tests for Tender Standard Matching & Compliance Assessment Engine."""

import pytest
from pathlib import Path

from bis_rag.data import BisData
from bis_rag.tender_compliance import (
    TenderComplianceEngine,
    TenderComplianceMatrix,
    TenderRequirementEvaluation,
    TenderStandardAssessment,
    assess_tender_compliance,
)
from bis_rag.tender_extractor import (
    TenderClause,
    TenderExtractionResult,
    TenderRequirement,
    extract_from_document,
)


from synth_bis_data import make_synth_data


@pytest.fixture(scope="module")
def bis_data(tmp_path_factory):
    """Load synthetic BisData for deterministic tests."""
    data_path = make_synth_data(tmp_path_factory.mktemp("bis_data"))
    return BisData(data_path)


# ---------------------------------------------------------------------------
# TEST 1: LED Street Lighting Tender Assessment (PASSING CASE)
# ---------------------------------------------------------------------------
def test_street_lighting_tender_compliance(bis_data):
    """Verify compliant LED street light tender passes applicable benchmarks."""
    tender = TenderExtractionResult(
        source=None,
        clauses=[
            TenderClause(
                clause_id="CL-01",
                title="Scope of Supply",
                clause_type="scope",
                text="Supply and installation of 90W LED street lighting luminaires for municipal roads.",
            )
        ],
        requirements=[
            TenderRequirement(
                requirement_id="REQ-001",
                parameter="Ingress Protection (IP)",
                specified_value="IP66",
                unit="IP",
                operator="exact",
                standard_references=["IS 10322 (Part 5/Sec 3)", "IS/IEC 60529"],
                category="environmental",
                is_mandatory=True,
            ),
            TenderRequirement(
                requirement_id="REQ-002",
                parameter="Luminous Efficacy",
                specified_value=">= 120 lm/W",
                numeric_value=120.0,
                unit="lm/W",
                operator=">=",
                standard_references=["IS 16107 (Part 2/Sec 1)"],
                category="photometric",
                is_mandatory=True,
            ),
            TenderRequirement(
                requirement_id="REQ-003",
                parameter="Surge Protection",
                specified_value="10 kV",
                numeric_value=10.0,
                unit="kV",
                operator="exact",
                standard_references=["IS 15885 (Part 2/Sec 13)"],
                category="electrical",
                is_mandatory=True,
            ),
        ],
        detected_standards=["IS 10322 (Part 5/Sec 3)", "IS 16107 (Part 2/Sec 1)", "IS/IEC 60529"],
        total_requirements=3,
    )

    matrix = assess_tender_compliance(tender, bis_data, product_description="LED street lighting luminaire")

    assert len(matrix.evaluations) == 3

    ip_eval = next(e for e in matrix.evaluations if e.parameter == "Ingress Protection (IP)")
    assert ip_eval.status == "PASS"

    eff_eval = next(e for e in matrix.evaluations if e.parameter == "Luminous Efficacy")
    assert eff_eval.status == "PASS"

    surge_eval = next(e for e in matrix.evaluations if e.parameter == "Surge Protection")
    assert surge_eval.status == "PASS"

    assert matrix.compliance_score > 0.70
    assert matrix.overall_grade in ("FULLY COMPLIANT", "MOSTLY COMPLIANT")


# ---------------------------------------------------------------------------
# TEST 2: Superseded Standard Detection in Tender
# ---------------------------------------------------------------------------
def test_superseded_standard_detection_in_tender(bis_data):
    """Verify tender citing superseded standard (e.g. IS 269:1989) is flagged with replacement."""
    tender = TenderExtractionResult(
        source=None,
        clauses=[
            TenderClause(
                clause_id="CL-01",
                title="Specification",
                clause_type="technical",
                text="Supply of 33 grade ordinary Portland cement complying with IS 269:1989.",
            )
        ],
        requirements=[
            TenderRequirement(
                requirement_id="REQ-001",
                parameter="Compressive Strength",
                specified_value="33 MPa",
                numeric_value=33.0,
                unit="MPa",
                standard_references=["IS 269:1989"],
            )
        ],
        detected_standards=["IS 269:1989"],
        total_requirements=1,
    )

    matrix = assess_tender_compliance(tender, bis_data, product_description="33 grade ordinary Portland cement")

    assert len(matrix.superseded_standards_cited) >= 1
    superseded_entry = matrix.superseded_standards_cited[0]
    assert "IS 269" in superseded_entry["cited"]
    assert "2015" in superseded_entry["replacement"]
    assert any("superseded" in flag.lower() for flag in matrix.risk_flags)


# ---------------------------------------------------------------------------
# TEST 3: Missing Mandatory QCO Standard Detection
# ---------------------------------------------------------------------------
def test_missing_mandatory_qco_detection(bis_data):
    """Verify omission of mandatory QCO standard caps overall grade at NON-COMPLIANT."""
    # Tender for cement cites only steel pipe standard IS 1239
    tender = TenderExtractionResult(
        source=None,
        clauses=[
            TenderClause(
                clause_id="CL-01",
                title="Procurement Notice",
                clause_type="scope",
                text="Procurement of 33 grade ordinary Portland cement for construction.",
            )
        ],
        requirements=[
            TenderRequirement(
                requirement_id="REQ-001",
                parameter="Packaging",
                specified_value="50 kg HDPE bags",
                standard_references=["IS 1239"],
            )
        ],
        detected_standards=["IS 1239"],
        total_requirements=1,
    )

    matrix = assess_tender_compliance(tender, bis_data, product_description="33 grade ordinary Portland cement")

    assert len(matrix.mandatory_qco_missing) >= 1
    assert any("IS 269" in m for m in matrix.mandatory_qco_missing)
    assert matrix.overall_grade == "NON-COMPLIANT"
    assert "Missing mandatory QCO" in matrix.grade_capped_by


# ---------------------------------------------------------------------------
# TEST 4: Domain Applicability Isolation
# ---------------------------------------------------------------------------
def test_domain_applicability_isolation(bis_data):
    """Verify unrelated domain standards (e.g. Transformers IS 10028) do not cause false failures for lighting."""
    tender = TenderExtractionResult(
        source=None,
        clauses=[
            TenderClause(
                clause_id="CL-01",
                title="Street Lighting Scope",
                clause_type="scope",
                text="Procurement of LED street light fixtures. Transformer installation guide IS 10028 (Part 2) referenced in general index.",
            )
        ],
        requirements=[
            TenderRequirement(
                requirement_id="REQ-001",
                parameter="Ingress Protection (IP)",
                specified_value="IP66",
                unit="IP",
                standard_references=["IS 10028 (Part 2)"],  # cross-domain transformer standard
            )
        ],
        detected_standards=["IS 10028 (Part 2)"],
        total_requirements=1,
    )

    matrix = assess_tender_compliance(tender, bis_data, product_description="LED street light luminaire")

    # The transformer standard must be classified as NOT_APPLICABLE
    std_assessment = next(s for s in matrix.standards_assessed if "10028" in s.designation)
    assert std_assessment.applicability == "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# TEST 5: Technical Parameter Failure
# ---------------------------------------------------------------------------
def test_technical_parameter_failure(bis_data):
    """Verify sub-standard technical parameter is evaluated as FAIL with HIGH risk."""
    tender = TenderExtractionResult(
        source=None,
        clauses=[],
        requirements=[
            TenderRequirement(
                requirement_id="REQ-001",
                parameter="Luminous Efficacy",
                specified_value="70 lm/W",  # below 100 lm/W standard baseline
                numeric_value=70.0,
                unit="lm/W",
                operator="exact",
                standard_references=["IS 16107 (Part 2/Sec 1)"],
                category="photometric",
            )
        ],
        detected_standards=["IS 16107 (Part 2/Sec 1)"],
        total_requirements=1,
    )

    matrix = assess_tender_compliance(tender, bis_data, product_description="LED street lighting luminaire")

    assert len(matrix.evaluations) == 1
    eval_item = matrix.evaluations[0]
    assert eval_item.status == "FAIL"
    assert eval_item.risk_level == "HIGH"
    assert any("fails standard threshold" in r for r in matrix.recommendations)


# ---------------------------------------------------------------------------
# TEST 6: Serialization
# ---------------------------------------------------------------------------
def test_compliance_matrix_serialization(bis_data):
    """Verify dictionary serialization for API and report layers."""
    tender = TenderExtractionResult(
        source=None,
        clauses=[],
        requirements=[
            TenderRequirement(
                requirement_id="REQ-001",
                parameter="Ingress Protection (IP)",
                specified_value="IP66",
                unit="IP",
            )
        ],
        detected_standards=["IS 10322 (Part 5/Sec 3)"],
        total_requirements=1,
    )

    matrix = assess_tender_compliance(tender, bis_data, product_description="LED street luminaire")
    d = matrix.as_dict()

    assert "evaluations" in d
    assert "standards_assessed" in d
    assert "compliance_score" in d
    assert "overall_grade" in d
    assert "qco_source" in d
    assert "qco_verified" in d
    assert isinstance(d["compliance_score"], float)
    assert len(d["evaluations"]) == 1


# ---------------------------------------------------------------------------
# TEST 7: Step C Tender QCO Evidence State & Safety
# ---------------------------------------------------------------------------
def test_tender_qco_evidence_states(bis_data):
    """Verify QCO evidence states in tender assessment."""
    from bis_rag.compliance import QCODatabase, QCOEvidenceState

    tender = TenderExtractionResult(
        source=None,
        clauses=[],
        requirements=[],
        detected_standards=["IS 269:2015", "IS 10322 (Part 5/Sec 3)"],
        total_requirements=0,
    )

    # 1. With seed database (data=None)
    seed_qco = QCODatabase(data=None)
    matrix_seed = assess_tender_compliance(tender, data=None, qco=seed_qco, product_description="Cement procurement")
    std_269_seed = next(s for s in matrix_seed.standards_assessed if "269" in s.designation)
    assert std_269_seed.is_mandatory_qco is True
    assert std_269_seed.qco_evidence_state == QCOEvidenceState.SEED_UNVERIFIED
    assert "Unverified QCO seed" in std_269_seed.qco_display

    # 2. With merged/scraped database (bis_data)
    matrix = assess_tender_compliance(tender, bis_data, product_description="Cement procurement")
    std_269 = next(s for s in matrix.standards_assessed if "269" in s.designation)
    assert std_269.is_mandatory_qco is True
    assert std_269.qco_evidence_state in (QCOEvidenceState.VERIFIED, QCOEvidenceState.SEED_UNVERIFIED)
    assert "QCO" in std_269.qco_display

    # IS 10322 is not in QCO -> NOT_FOUND (never "Voluntary")
    std_10322 = next(s for s in matrix.standards_assessed if "10322" in s.designation)
    assert std_10322.is_mandatory_qco is False
    assert std_10322.qco_evidence_state == QCOEvidenceState.NOT_FOUND
    assert "No verified QCO evidence found" in std_10322.qco_display

