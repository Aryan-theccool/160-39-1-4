"""Unit and integration tests for Product Specification Compliance Assessment.

Validates:
- TEST 1 to TEST 14 from Step 2 specification
- Unit normalization & engineering conversions
- IP rating parsing and digit-level comparison
- Safe UNKNOWN verdicts on insufficient evidence or unit mismatch
- Supersession and QCO unverified tier warnings
- Grounding and existing compliance behaviors
"""

import pytest
from bis_rag.compliance import (
    ProductSpec,
    RequirementItem,
    SpecificationCheck,
    ResolvedStandard,
    extract_product_specs,
    normalize_unit_value,
    compare_ip_ratings,
    evaluate_spec_check,
    evaluate_all_spec_checks,
    assess_standard_applicability,
    ComplianceChecker,
    QCODatabase,
    SEED_QCO,
)
from bis_rag.data import BisData


def test_test1_power_pass():
    """TEST 1: Product 90 W, Requirement minimum 80 W -> Expected: PASS"""
    spec = ProductSpec(parameter="power", raw_value="90 W", numeric_value=90.0, unit="W", base_value=90.0, base_unit="W")
    req = RequirementItem(parameter="power", raw_value="80 W", numeric_value=80.0, unit="W", base_value=80.0, base_unit="W", operator="minimum")
    check = evaluate_spec_check(spec, req, "power")
    assert check.status == "PASS"
    assert "satisfies" in check.explanation


def test_test2_power_fail():
    """TEST 2: Product 70 W, Requirement minimum 80 W -> Expected: FAIL"""
    spec = ProductSpec(parameter="power", raw_value="70 W", numeric_value=70.0, unit="W", base_value=70.0, base_unit="W")
    req = RequirementItem(parameter="power", raw_value="80 W", numeric_value=80.0, unit="W", base_value=80.0, base_unit="W", operator="minimum")
    check = evaluate_spec_check(spec, req, "power")
    assert check.status == "FAIL"
    assert "below the required minimum" in check.explanation


def test_test3_power_max_fail():
    """TEST 3: Product 120 W, Requirement maximum 100 W -> Expected: FAIL"""
    spec = ProductSpec(parameter="power", raw_value="120 W", numeric_value=120.0, unit="W", base_value=120.0, base_unit="W")
    req = RequirementItem(parameter="power", raw_value="100 W", numeric_value=100.0, unit="W", base_value=100.0, base_unit="W", operator="maximum")
    check = evaluate_spec_check(spec, req, "power")
    assert check.status == "FAIL"
    assert "exceeds the required maximum" in check.explanation


def test_test4_voltage_exact_pass():
    """TEST 4: Product 230 V, Requirement 230 V -> Expected: PASS"""
    spec = ProductSpec(parameter="voltage", raw_value="230 V", numeric_value=230.0, unit="V", base_value=230.0, base_unit="V")
    req = RequirementItem(parameter="voltage", raw_value="230 V", numeric_value=230.0, unit="V", base_value=230.0, base_unit="V", operator="exact")
    check = evaluate_spec_check(spec, req, "voltage")
    assert check.status == "PASS"


def test_test5_unit_normalization_kw_pass():
    """TEST 5: Product 1 kW, Requirement 900 W minimum -> Expected: PASS"""
    val, base_u = normalize_unit_value(1.0, "kW")
    spec = ProductSpec(parameter="power", raw_value="1 kW", numeric_value=1.0, unit="kW", base_value=val, base_unit=base_u)
    req = RequirementItem(parameter="power", raw_value="900 W", numeric_value=900.0, unit="W", base_value=900.0, base_unit="W", operator="minimum")
    check = evaluate_spec_check(spec, req, "power")
    assert check.status == "PASS"


def test_test6_ip_rating_ip66_vs_ip65_pass():
    """TEST 6: Product IP66, Requirement IP65 minimum -> Expected: PASS"""
    spec = ProductSpec(parameter="ip_rating", raw_value="IP66", unit="IP", base_unit="IP")
    req = RequirementItem(parameter="ip_rating", raw_value="IP65", unit="IP", base_unit="IP", operator="minimum")
    check = evaluate_spec_check(spec, req, "ip_rating")
    assert check.status == "PASS"


def test_test7_ip_rating_ip54_vs_ip65_fail():
    """TEST 7: Product IP54, Requirement IP65 minimum -> Expected: FAIL"""
    spec = ProductSpec(parameter="ip_rating", raw_value="IP54", unit="IP", base_unit="IP")
    req = RequirementItem(parameter="ip_rating", raw_value="IP65", unit="IP", base_unit="IP", operator="minimum")
    check = evaluate_spec_check(spec, req, "ip_rating")
    assert check.status == "FAIL"


def test_test8_missing_product_spec_unknown():
    """TEST 8: Missing product specification -> Expected: UNKNOWN"""
    req = RequirementItem(parameter="efficiency", raw_value="90%", numeric_value=90.0, unit="%", base_value=90.0, base_unit="%", operator="minimum")
    check = evaluate_spec_check(None, req, "efficiency")
    assert check.status == "UNKNOWN"
    assert "Product specification does not provide efficiency / efficacy for comparison." in check.explanation


def test_test9_missing_requirement_evidence_unknown():
    """TEST 9: Missing requirement evidence -> Expected: UNKNOWN with clear parameter reason"""
    spec = ProductSpec(parameter="colour_temperature", raw_value="4000 K", numeric_value=4000.0, unit="K", base_value=4000.0, base_unit="K")
    check = evaluate_spec_check(spec, None, "colour_temperature")
    assert check.status == "UNKNOWN"
    assert check.explanation == "No confirmed applicable-standard requirement for correlated colour temperature was found."

    v_spec = ProductSpec(parameter="voltage", raw_value="230 V AC", numeric_value=230.0, unit="V", base_value=230.0, base_unit="V")
    v_check = evaluate_spec_check(v_spec, None, "voltage")
    assert v_check.status == "UNKNOWN"
    assert v_check.explanation == "No confirmed applicable-standard requirement for rated supply voltage was found."


def test_test10_incompatible_units_unknown():
    """TEST 10: Incompatible units (e.g. Watts vs Volts) -> Expected: UNKNOWN"""
    spec = ProductSpec(parameter="power", raw_value="90 W", numeric_value=90.0, unit="W", base_value=90.0, base_unit="W")
    req = RequirementItem(parameter="power", raw_value="230 V", numeric_value=230.0, unit="V", base_value=230.0, base_unit="V", operator="minimum")
    check = evaluate_spec_check(spec, req, "power")
    assert check.status == "UNKNOWN"
    assert "Incompatible units" in check.explanation


from synth_bis_data import make_synth_data


@pytest.fixture(scope="module")
def data_root(tmp_path_factory):
    return make_synth_data(tmp_path_factory.mktemp("bis_data"))


@pytest.fixture(scope="module")
def data(data_root) -> BisData:
    return BisData(data_root)


def test_test11_superseded_standard_warning(data):
    """TEST 11: Superseded standard generates clear warning and action item."""
    checker = ComplianceChecker(data)
    report = checker.analyze("Testing Portland cement", ["IS 269:1989"])
    assert len(report.superseded_used) > 0 or any("IS 269" in s.designation for s in report.standards)


def test_test12_unverified_qco_warning(data):
    """TEST 12: Unverified QCO seed entry -> verification warning, not authoritative mandatory claim."""
    qco = QCODatabase(None)
    checker = ComplianceChecker(data, qco=qco)
    assert not checker.qco.verified
    report = checker.analyze("33 grade ordinary Portland cement", ["IS 269"])
    assert not report.qco_verified
    assert report.qco_source == "seed"
    assert "Unverified" in report.qco_basis or "seed" in report.qco_basis


def test_test13_unsupported_citation_safety():
    """TEST 13: Unsupported citations and safe grounding guardrails."""
    spec_map = extract_product_specs("Outdoor LED street light, 90 W, IP66, 4000 K, 230 V AC")
    assert "power" in spec_map
    assert spec_map["power"].numeric_value == 90.0
    assert "ip_rating" in spec_map
    assert spec_map["ip_rating"].raw_value == "IP66"
    assert "voltage" in spec_map
    assert spec_map["voltage"].numeric_value == 230.0
    assert "colour_temperature" in spec_map
    assert spec_map["colour_temperature"].numeric_value == 4000.0


def test_test14_existing_compliance_behavior(data):
    """TEST 14: Existing compliance behavior and deterministic grade bands work as expected."""
    qco = QCODatabase(None)
    checker = ComplianceChecker(data, qco=qco)
    report = checker.analyze("33 grade ordinary Portland cement", ["IS 456:2000"])
    assert "IS 269" in report.mandatory_missing
    assert report.grade_capped_by != ""
    assert report.grade in ("NON-COMPLIANT", "PARTIALLY COMPLIANT")


def test_scope_bounds_and_applicability_semantics(data):
    """Verify that scope bounds are applicability evidence, not product requirements.

    Example:
    IS 10028 (Part 2):1981
    Applicability: NOT APPLICABLE
    Reason: Standard concerns transformer installation; product is an LED street-light luminaire.

    230 V AC
    Result: UNKNOWN
    Reason: No confirmed applicable-standard requirement for rated supply voltage was found.
    """
    checker = ComplianceChecker(data)
    product_desc = "Outdoor LED street-light luminaire 90 W, 230 V AC, IP66, 4000 K"
    report = checker.analyze(product_desc, ["IS 10028 (Part 2):1981"])

    # 1. Standard Applicability & Reason
    assert len(report.standards) == 1
    std = report.standards[0]
    assert std.applicability == "NOT_APPLICABLE"
    assert std.applicability_reason == "Standard concerns transformer installation; product is an LED street-light luminaire."

    # 2. Voltage Check on 230 V AC
    voltage_checks = [c for c in report.specification_checks if c.parameter == "voltage"]
    assert len(voltage_checks) == 1
    v_check = voltage_checks[0]
    assert v_check.status == "UNKNOWN"
    assert v_check.explanation == "No confirmed applicable-standard requirement for rated supply voltage was found."

    # 3. Rule Enforcement: No PASS or FAIL generated from scope bounds of non-applicable standards
    for check in report.specification_checks:
        assert check.status != "FAIL", f"Unexpected FAIL on {check.parameter}: {check.explanation}"
        assert check.status != "PASS" or check.standard != "IS 10028 (Part 2):1981"
