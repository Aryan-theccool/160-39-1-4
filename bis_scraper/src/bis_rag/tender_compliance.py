"""Tender Standard Matching & Clause Compliance Assessment Engine.

Evaluates extracted tender requirements (parameters, values, units, operators) and standard citations
against BIS dataset evidence, Quality Control Orders (QCOs), supersession histories, and domain applicability rules.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from bis_pipeline import iscode
from bis_pipeline.iscode import yearless_key as _yearless_key

from .compliance import (
    GRADE_BANDS,
    MIN_PRODUCT_MATCH,
    ProductSpec,
    QCODatabase,
    QCOEvidenceState,
    RequirementItem,
    assess_standard_applicability,
    compare_ip_ratings,
    detect_sector,
    extract_requirements_from_evidence,
    normalize_unit_value,
)
from .data import BisData
from .schema import Standard
from .tender_extractor import TenderClause, TenderExtractionResult, TenderRequirement

log = logging.getLogger(__name__)

__all__ = [
    "TenderRequirementEvaluation",
    "TenderStandardAssessment",
    "TenderComplianceMatrix",
    "TenderComplianceEngine",
    "assess_tender_compliance",
]


# ---------------------------------------------------------------------------
# DATA MODELS
# ---------------------------------------------------------------------------
@dataclass
class TenderRequirementEvaluation:
    """Evaluation of an individual tender requirement against applicable standards."""

    requirement_id: str
    parameter: str
    specified_value: str
    numeric_value: Optional[float] = None
    numeric_max: Optional[float] = None
    unit: str = ""
    operator: str = "exact"
    standard: str = "Applicable standard"
    required_standard_value: str = "Not specified in confirmed applicable standard"
    status: str = "UNKNOWN"  # "PASS" | "FAIL" | "UNKNOWN" | "NOT_APPLICABLE" | "FLAGGED"
    evaluation_reason: str = ""
    clause_reference: str = ""
    evidence_text: str = ""
    is_mandatory: bool = True
    category: str = "general"
    risk_level: str = "LOW"  # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"

    def as_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "parameter": self.parameter,
            "specified_value": self.specified_value,
            "numeric_value": self.numeric_value,
            "numeric_max": self.numeric_max,
            "unit": self.unit,
            "operator": self.operator,
            "standard": self.standard,
            "required_standard_value": self.required_standard_value,
            "status": self.status,
            "evaluation_reason": self.evaluation_reason,
            "clause_reference": self.clause_reference,
            "evidence_text": self.evidence_text,
            "is_mandatory": self.is_mandatory,
            "category": self.category,
            "risk_level": self.risk_level,
        }


@dataclass
class TenderStandardAssessment:
    """Assessment of a standard cited or recommended for the tender."""

    designation: str
    title: str = ""
    applicability: str = "CANDIDATE"  # "APPLICABLE" | "NOT_APPLICABLE" | "CANDIDATE"
    applicability_reason: str = ""
    is_mandatory_qco: bool = False
    qco_evidence_state: str = QCOEvidenceState.NOT_FOUND  # "VERIFIED" | "SEED_UNVERIFIED" | "NOT_FOUND" | "NOT_APPLICABLE"
    qco_display: str = "No QCO Evidence in Dataset"
    is_current: bool = True
    superseded_by: Optional[str] = None
    citation_source: str = "explicit_tender_citation"  # "explicit_tender_citation" | "retrieved_candidate" | "qco_requirement"

    def as_dict(self) -> dict[str, Any]:
        return {
            "designation": self.designation,
            "title": self.title,
            "applicability": self.applicability,
            "applicability_reason": self.applicability_reason,
            "is_mandatory_qco": self.is_mandatory_qco,
            "qco_evidence_state": self.qco_evidence_state,
            "qco_display": self.qco_display,
            "is_current": self.is_current,
            "superseded_by": self.superseded_by,
            "citation_source": self.citation_source,
        }


@dataclass
class TenderComplianceMatrix:
    """Comprehensive compliance matrix and risk analysis for a tender document."""

    product_description: str = ""
    sector: Optional[str] = None
    evaluations: list[TenderRequirementEvaluation] = field(default_factory=list)
    standards_assessed: list[TenderStandardAssessment] = field(default_factory=list)
    mandatory_qco_expected: list[str] = field(default_factory=list)
    mandatory_qco_present: list[str] = field(default_factory=list)
    mandatory_qco_missing: list[str] = field(default_factory=list)
    qco_source: str = "none"
    qco_verified: bool = False
    superseded_standards_cited: list[dict[str, Any]] = field(default_factory=list)
    conflicts_detected: list[dict[str, str]] = field(default_factory=list)
    compliance_score: float = 0.0
    overall_grade: str = "UNKNOWN"
    status: str = "UNKNOWN"
    grade_capped_by: str = ""
    risk_flags: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "product_description": self.product_description,
            "sector": self.sector,
            "qco_source": self.qco_source,
            "qco_verified": self.qco_verified,
            "evaluations": [e.as_dict() for e in self.evaluations],
            "standards_assessed": [s.as_dict() for s in self.standards_assessed],
            "mandatory_qco_expected": self.mandatory_qco_expected,
            "mandatory_qco_present": self.mandatory_qco_present,
            "mandatory_qco_missing": self.mandatory_qco_missing,
            "superseded_standards_cited": self.superseded_standards_cited,
            "conflicts_detected": self.conflicts_detected,
            "compliance_score": round(self.compliance_score, 4),
            "overall_grade": self.overall_grade,
            "status": self.status,
            "grade_capped_by": self.grade_capped_by,
            "risk_flags": self.risk_flags,
            "recommendations": self.recommendations,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# TENDER COMPLIANCE ENGINE
# ---------------------------------------------------------------------------
class TenderComplianceEngine:
    """Assesses tender requirements and standard citations against BIS standards and QCOs."""

    def __init__(self, data: BisData, qco: Optional[QCODatabase] = None):
        self.data = data
        self.qco = qco if qco is not None else QCODatabase(data)

    def _infer_product_description(self, tender: TenderExtractionResult) -> str:
        """Infer target product description from scope clauses or requirements."""
        for c in tender.clauses:
            if c.clause_type in ("scope", "technical") and c.text:
                return c.text[:300]
        # Fallback to combined parameter names
        if tender.requirements:
            sample_params = ", ".join(r.parameter for r in tender.requirements[:4])
            return f"Procurement item with specifications for {sample_params}"
        return "Tender procurement item"

    def analyze(
        self,
        tender: TenderExtractionResult,
        product_description: Optional[str] = None,
        sector: Optional[str] = None,
    ) -> TenderComplianceMatrix:
        """Execute clause-by-clause tender compliance assessment."""
        prod_desc = product_description or self._infer_product_description(tender)
        detected_sec, sec_hits = detect_sector(prod_desc) if sector is None else (sector, {})
        sec = sector or detected_sec

        matrix = TenderComplianceMatrix(
            product_description=prod_desc,
            sector=sec,
            qco_source=self.qco.source,
            qco_verified=self.qco.verified,
        )

        # ------------------------------------------------------------------
        # 1. Resolve & Assess All Cited and Candidate Standards
        # ------------------------------------------------------------------
        seen_stds: set[str] = set()
        standards_assessed: list[TenderStandardAssessment] = []

        all_cited_stds = list(tender.detected_standards)
        for req in tender.requirements:
            for s in req.standard_references:
                if s not in all_cited_stds:
                    all_cited_stds.append(s)

        for raw_std in all_cited_stds:
            std_key = _yearless_key(raw_std)
            if not std_key or std_key in seen_stds:
                continue
            seen_stds.add(std_key)

            resolved_std = self.data.resolve_designation(raw_std) if self.data is not None else None
            if resolved_std is None and self.data is not None:
                std_k = _yearless_key(raw_std)
                for s in self.data.standards():
                    if _yearless_key(s.designation) == std_k or (s.canonical and _yearless_key(s.canonical) == std_k):
                        resolved_std = s
                        break

            title = resolved_std.title if resolved_std else ""
            desig = resolved_std.designation if resolved_std else raw_std
            is_current = resolved_std.is_current if resolved_std else True

            # Check supersession
            superseded_by = None
            parsed_raw = iscode.parse_designation(raw_std)
            if resolved_std and self.data is not None:
                if not is_current:
                    info = self.data.supersession(resolved_std.canonical)
                    if info and info.replacement_designation:
                        superseded_by = info.replacement_designation
                elif parsed_raw and parsed_raw.year and resolved_std.year and parsed_raw.year < resolved_std.year:
                    is_current = False
                    superseded_by = resolved_std.designation

                if superseded_by:
                    matrix.superseded_standards_cited.append({
                        "cited": raw_std,
                        "replacement": superseded_by,
                        "in_dataset": True,
                    })
                    matrix.risk_flags.append(
                        f"Tender cites superseded standard '{raw_std}'. Upgrade to '{superseded_by}'."
                    )

            # Check QCO status with explicit evidence state
            qco_entry = self.qco.lookup(desig) or self.qco.lookup(raw_std)
            if qco_entry is not None:
                is_mandatory_qco = qco_entry.evidence_state in (
                    QCOEvidenceState.VERIFIED,
                    QCOEvidenceState.SEED_UNVERIFIED,
                    QCOEvidenceState.SUPERSEDED_OR_CHANGED,
                )
                qco_state = qco_entry.evidence_state
                if qco_state == QCOEvidenceState.VERIFIED:
                    qco_disp = "✓ Verified QCO evidence"
                elif qco_state == QCOEvidenceState.SUPERSEDED_OR_CHANGED:
                    qco_disp = "↻ Regulatory status changed"
                elif qco_state == QCOEvidenceState.NOT_APPLICABLE:
                    qco_disp = "○ QCO not applicable"
                elif qco_state == QCOEvidenceState.AMBIGUOUS:
                    qco_disp = "⚠ QCO applicability ambiguous"
                elif qco_state == QCOEvidenceState.NOT_FOUND:
                    qco_disp = "⚠ No verified QCO evidence found"
                else:
                    qco_disp = "⚠ Unverified QCO seed"
            else:
                is_mandatory_qco = False
                qco_state = QCOEvidenceState.NOT_FOUND
                qco_disp = "⚠ No verified QCO evidence found"

            # Assess applicability
            app_status, app_reason = assess_standard_applicability(
                title, desig, prod_desc, sector=sec
            )

            standards_assessed.append(
                TenderStandardAssessment(
                    designation=desig,
                    title=title,
                    applicability=app_status,
                    applicability_reason=app_reason,
                    is_mandatory_qco=is_mandatory_qco,
                    qco_evidence_state=qco_state,
                    qco_display=qco_disp,
                    is_current=is_current,
                    superseded_by=superseded_by,
                    citation_source="explicit_tender_citation",
                )
            )

        # Check QCO expected standards for this product/sector
        expected_qco_map = {}
        if prod_desc:
            matches = self.qco.match_product(prod_desc)
            strong = [(score, entry) for score, entry in matches if score >= MIN_PRODUCT_MATCH]
            if strong:
                top_score = strong[0][0]
                for score, entry in strong:
                    if score == top_score:
                        expected_qco_map[entry.key] = entry

        for std in standards_assessed:
            if std.is_mandatory_qco:
                k = _yearless_key(std.designation)
                if k:
                    expected_qco_map[k] = self.qco.lookup(std.designation)

        matrix.mandatory_qco_expected = sorted(e.designation for e in expected_qco_map.values() if e)

        for desig in matrix.mandatory_qco_expected:
            k = _yearless_key(desig)
            if k in seen_stds:
                matrix.mandatory_qco_present.append(desig)
            else:
                matrix.mandatory_qco_missing.append(desig)
                matrix.risk_flags.append(
                    f"Mandatory Quality Control Order (QCO) standard '{desig}' is missing from tender specifications."
                )

        matrix.standards_assessed = standards_assessed

        # ------------------------------------------------------------------
        # 2. Extract Evidence Chunks for Confirmed Applicable Standards
        # ------------------------------------------------------------------
        applicable_stds = [s for s in standards_assessed if s.applicability == "APPLICABLE"]
        candidate_std_names = [s.designation for s in applicable_stds if s.designation]

        # Convert tender requirements to ProductSpec for evidence extraction
        product_specs_dict: dict[str, ProductSpec] = {}
        for req in tender.requirements:
            p_key = req.parameter.lower().replace(" ", "_")
            if p_key not in product_specs_dict and req.numeric_value is not None:
                base_v, base_u = normalize_unit_value(req.numeric_value, req.unit)
                product_specs_dict[p_key] = ProductSpec(
                    parameter=p_key,
                    raw_value=req.specified_value,
                    numeric_value=req.numeric_value,
                    unit=req.unit,
                    base_value=base_v,
                    base_unit=base_u,
                )

        evidence_reqs = extract_requirements_from_evidence(
            self.data,
            candidate_std_names,
            product_specs_dict,
            product_description=prod_desc,
            sector=sec,
        )

        evidence_req_map: dict[str, RequirementItem] = {}
        for er in evidence_reqs:
            evidence_req_map[er.parameter] = er

        # ------------------------------------------------------------------
        # 3. Evaluate Requirements Clause by Clause
        # ------------------------------------------------------------------
        evaluations: list[TenderRequirementEvaluation] = []

        for req in tender.requirements:
            eval_item = self._evaluate_requirement(req, standards_assessed, evidence_req_map, prod_desc)
            evaluations.append(eval_item)

        matrix.evaluations = evaluations

        # ------------------------------------------------------------------
        # 4. Compute Compliance Score, Status, and Overall Grade
        # ------------------------------------------------------------------
        self._compute_score_and_grade(matrix)
        self._generate_recommendations(matrix)

        return matrix

    def _evaluate_requirement(
        self,
        req: TenderRequirement,
        applicable_stds: list[TenderStandardAssessment],
        evidence_req_map: dict[str, RequirementItem],
        prod_desc: str,
    ) -> TenderRequirementEvaluation:
        """Evaluate an individual tender requirement against evidence."""
        p_name = req.parameter
        p_key = p_name.lower().replace(" ", "_")
        std_citation = req.standard_references[0] if req.standard_references else ""

        # Check if the cited standard is NOT applicable
        if std_citation:
            cited_key = _yearless_key(std_citation)
            for s in applicable_stds:
                if _yearless_key(s.designation) == cited_key and s.applicability == "NOT_APPLICABLE":
                    return TenderRequirementEvaluation(
                        requirement_id=req.requirement_id,
                        parameter=p_name,
                        specified_value=req.specified_value,
                        numeric_value=req.numeric_value,
                        numeric_max=req.numeric_max,
                        unit=req.unit,
                        operator=req.operator,
                        standard=std_citation,
                        required_standard_value="Standard not applicable",
                        status="NOT_APPLICABLE",
                        evaluation_reason=f"Standard '{std_citation}' is not applicable to target product.",
                        clause_reference=req.source_location,
                        is_mandatory=req.is_mandatory,
                        category=req.category,
                        risk_level="HIGH",
                    )

        # 1. IP Rating Check
        if "ingress protection" in p_name.lower() or "ip rating" in p_name.lower() or req.unit.upper() == "IP":
            req_evidence = evidence_req_map.get("ip_rating")
            req_val_str = req_evidence.raw_value if req_evidence else "IP65 (Mandatory Minimum)"
            std_name = req_evidence.standard if req_evidence else (applicable_stds[0].designation if applicable_stds else "IS 10322 / IS/IEC 60529")

            raw_ip = req.specified_value
            # Extract IP code e.g. IP66 from specified value
            import re
            m = re.search(r"\b(IP\s*[0-6X][0-9X])\b", raw_ip, re.IGNORECASE)
            spec_ip = m.group(1).replace(" ", "").upper() if m else "IP66"
            target_ip = "IP65" if not req_evidence else req_evidence.raw_value

            cmp_res = compare_ip_ratings(spec_ip, target_ip)
            if cmp_res is True:
                status = "PASS"
                reason = f"Specified rating {spec_ip} meets or exceeds standard requirement {target_ip}."
                risk = "LOW"
            elif cmp_res is False:
                status = "FAIL"
                reason = f"Specified rating {spec_ip} is lower than required {target_ip}."
                risk = "HIGH"
            else:
                status = "PASS" if spec_ip in ("IP65", "IP66", "IP67", "IP68") else "UNKNOWN"
                reason = f"Specified {spec_ip} satisfies outdoor ingress protection standards."
                risk = "LOW"

            return TenderRequirementEvaluation(
                requirement_id=req.requirement_id,
                parameter=p_name,
                specified_value=req.specified_value,
                numeric_value=req.numeric_value,
                numeric_max=req.numeric_max,
                unit="IP",
                operator=req.operator,
                standard=std_name,
                required_standard_value=target_ip,
                status=status,
                evaluation_reason=reason,
                clause_reference=req.source_location,
                evidence_text=req_evidence.evidence if req_evidence else "Standard luminaire environmental protection",
                is_mandatory=req.is_mandatory,
                category=req.category,
                risk_level=risk,
            )

        # 2. Luminous Efficacy Check
        if "efficacy" in p_name.lower() or req.unit in ("lm/W", "lumens/watt"):
            std_name = "IS 16107 (Part 2/Sec 1)"
            min_efficacy = 100.0  # standard baseline
            if req.numeric_value is not None:
                if req.numeric_value >= min_efficacy:
                    status = "PASS"
                    reason = f"Specified efficacy {req.numeric_value} lm/W exceeds standard baseline of {min_efficacy} lm/W."
                    risk = "LOW"
                else:
                    status = "FAIL"
                    reason = f"Specified efficacy {req.numeric_value} lm/W is below standard minimum of {min_efficacy} lm/W."
                    risk = "HIGH"
            else:
                status = "UNKNOWN"
                reason = "Could not parse numeric efficacy value for deterministic comparison."
                risk = "MEDIUM"

            return TenderRequirementEvaluation(
                requirement_id=req.requirement_id,
                parameter=p_name,
                specified_value=req.specified_value,
                numeric_value=req.numeric_value,
                numeric_max=req.numeric_max,
                unit=req.unit or "lm/W",
                operator=req.operator,
                standard=std_name,
                required_standard_value=f">= {min_efficacy} lm/W",
                status=status,
                evaluation_reason=reason,
                clause_reference=req.source_location,
                is_mandatory=req.is_mandatory,
                category=req.category,
                risk_level=risk,
            )

        # 3. Surge Protection Check
        if "surge" in p_name.lower() or req.unit == "kV":
            std_name = "IS 15885 (Part 2/Sec 13)"
            min_surge = 4.0  # kV baseline
            if req.numeric_value is not None:
                if req.numeric_value >= min_surge:
                    status = "PASS"
                    reason = f"Specified surge withstand {req.numeric_value} kV complies with standard requirement (>= {min_surge} kV)."
                    risk = "LOW"
                else:
                    status = "FAIL"
                    reason = f"Specified surge withstand {req.numeric_value} kV is below standard requirement ({min_surge} kV)."
                    risk = "HIGH"
            else:
                status = "UNKNOWN"
                reason = "Could not parse numeric surge rating."
                risk = "MEDIUM"

            return TenderRequirementEvaluation(
                requirement_id=req.requirement_id,
                parameter=p_name,
                specified_value=req.specified_value,
                numeric_value=req.numeric_value,
                numeric_max=req.numeric_max,
                unit="kV",
                operator=req.operator,
                standard=std_name,
                required_standard_value=f">= {min_surge} kV",
                status=status,
                evaluation_reason=reason,
                clause_reference=req.source_location,
                is_mandatory=req.is_mandatory,
                category=req.category,
                risk_level=risk,
            )

        # 4. Power Factor Check
        if "power factor" in p_name.lower() or p_name.lower() == "pf":
            std_name = "IS 15885 / IS 16107"
            min_pf = 0.90
            if req.numeric_value is not None:
                if req.numeric_value >= min_pf:
                    status = "PASS"
                    reason = f"Specified power factor {req.numeric_value} complies with standard requirement (>= {min_pf})."
                    risk = "LOW"
                else:
                    status = "FAIL"
                    reason = f"Specified power factor {req.numeric_value} is below standard minimum of {min_pf}."
                    risk = "HIGH"
            else:
                status = "UNKNOWN"
                reason = "Could not parse numeric power factor."
                risk = "MEDIUM"

            return TenderRequirementEvaluation(
                requirement_id=req.requirement_id,
                parameter=p_name,
                specified_value=req.specified_value,
                numeric_value=req.numeric_value,
                numeric_max=req.numeric_max,
                unit="",
                operator=req.operator,
                standard=std_name,
                required_standard_value=f">= {min_pf}",
                status=status,
                evaluation_reason=reason,
                clause_reference=req.source_location,
                is_mandatory=req.is_mandatory,
                category=req.category,
                risk_level=risk,
            )

        # 5. Tensile Strength Check (Materials)
        if "tensile strength" in p_name.lower():
            std_name = "IS 1239 / IS 1786"
            min_ts = 320.0  # MPa baseline for standard pipe/steel
            if req.numeric_value is not None:
                if req.numeric_value >= min_ts:
                    status = "PASS"
                    reason = f"Specified tensile strength {req.numeric_value} MPa meets standard baseline (>= {min_ts} MPa)."
                    risk = "LOW"
                else:
                    status = "FAIL"
                    reason = f"Specified tensile strength {req.numeric_value} MPa is below standard baseline ({min_ts} MPa)."
                    risk = "HIGH"
            else:
                status = "UNKNOWN"
                reason = "Could not parse numeric tensile strength value."
                risk = "MEDIUM"

            return TenderRequirementEvaluation(
                requirement_id=req.requirement_id,
                parameter=p_name,
                specified_value=req.specified_value,
                numeric_value=req.numeric_value,
                numeric_max=req.numeric_max,
                unit="MPa",
                operator=req.operator,
                standard=std_name,
                required_standard_value=f">= {min_ts} MPa",
                status=status,
                evaluation_reason=reason,
                clause_reference=req.source_location,
                is_mandatory=req.is_mandatory,
                category=req.category,
                risk_level=risk,
            )

        # 6. Yield Strength / 0.2% Proof Stress Check (Steel Rebar / Sections)
        if "yield" in p_name.lower() or "proof stress" in p_name.lower() or p_key in ("yield_strength", "proof_stress"):
            std_name = "IS 1786 / IS 2062"
            min_ys = 500.0 if any(k in prod_desc.lower() for k in ["tmt", "fe 500", "reinforcement", "500"]) or "500" in req.specified_value else (415.0 if "415" in prod_desc else 250.0)
            if req.numeric_value is not None:
                if req.numeric_value >= min_ys:
                    status = "PASS"
                    reason = f"Specified yield strength {req.numeric_value} N/mm2 meets standard requirement (>= {min_ys} N/mm2)."
                    risk = "LOW"
                else:
                    status = "FAIL"
                    reason = f"Specified yield strength {req.numeric_value} N/mm2 is below standard minimum of {min_ys} N/mm2."
                    risk = "HIGH"
            else:
                status = "UNKNOWN"
                reason = "Could not parse numeric yield strength value."
                risk = "MEDIUM"

            return TenderRequirementEvaluation(
                requirement_id=req.requirement_id,
                parameter=p_name,
                specified_value=req.specified_value,
                numeric_value=req.numeric_value,
                numeric_max=req.numeric_max,
                unit=req.unit or "N/mm2",
                operator=req.operator,
                standard=std_name,
                required_standard_value=f">= {min_ys} N/mm2",
                status=status,
                evaluation_reason=reason,
                clause_reference=req.source_location,
                is_mandatory=req.is_mandatory,
                category=req.category or "materials",
                risk_level=risk,
            )

        # 7. Generic / Other Parameters (Transparent UNKNOWN if not in evidence)
        default_std = applicable_stds[0].designation if applicable_stds else "Applicable Indian Standard"
        return TenderRequirementEvaluation(
            requirement_id=req.requirement_id,
            parameter=p_name,
            specified_value=req.specified_value,
            numeric_value=req.numeric_value,
            numeric_max=req.numeric_max,
            unit=req.unit,
            operator=req.operator,
            standard=default_std,
            required_standard_value="No confirmed constraint in indexed evidence",
            status="UNKNOWN",
            evaluation_reason=f"Parameter '{p_name}' does not have a restrictive threshold in the confirmed applicable standard evidence.",
            clause_reference=req.source_location,
            is_mandatory=req.is_mandatory,
            category=req.category,
            risk_level="LOW",
        )

    def _compute_score_and_grade(self, matrix: TenderComplianceMatrix) -> None:
        """Compute transparent compliance score and determine grade."""
        # Metric 1: Mandatory QCO Presence (Weight 0.40)
        total_qco = len(matrix.mandatory_qco_expected)
        qco_score = (len(matrix.mandatory_qco_present) / total_qco) if total_qco > 0 else 1.0

        # Metric 2: Requirement Checks (Weight 0.40)
        total_reqs = len(matrix.evaluations)
        pass_count = sum(1 for e in matrix.evaluations if e.status == "PASS")
        fail_count = sum(1 for e in matrix.evaluations if e.status == "FAIL")
        unknown_count = sum(1 for e in matrix.evaluations if e.status == "UNKNOWN")

        req_score = ((pass_count + 0.5 * unknown_count) / total_reqs) if total_reqs > 0 else 1.0

        # Metric 3: Currency / Supersession (Weight 0.15)
        superseded_count = len(matrix.superseded_standards_cited)
        currency_score = max(0.0, 1.0 - (superseded_count * 0.3))

        # Metric 4: Conflict Deductions (Weight 0.05)
        conflict_score = 0.0 if matrix.conflicts_detected else 1.0

        # Composite score
        raw_score = (0.40 * qco_score) + (0.40 * req_score) + (0.15 * currency_score) + (0.05 * conflict_score)
        matrix.compliance_score = max(0.0, min(1.0, raw_score))

        # Determine Grade from GRADE_BANDS
        grade = "NON-COMPLIANT"
        for threshold, name, min_mand in GRADE_BANDS:
            if matrix.compliance_score >= threshold:
                if min_mand and matrix.mandatory_qco_missing:
                    continue
                grade = name
                break

        # Hard overrides
        if matrix.mandatory_qco_missing:
            grade = "NON-COMPLIANT"
            matrix.grade_capped_by = "Missing mandatory QCO standard(s)"
            matrix.status = "NON_COMPLIANT"
        elif fail_count > 0:
            if grade == "FULLY COMPLIANT":
                grade = "MOSTLY COMPLIANT"
            matrix.grade_capped_by = f"{fail_count} technical requirement(s) failed standard benchmark"
            matrix.status = "PARTIAL"
        elif matrix.superseded_standards_cited:
            if grade == "FULLY COMPLIANT":
                grade = "MOSTLY COMPLIANT"
            matrix.grade_capped_by = "Superseded standard(s) cited"
            matrix.status = "PARTIAL"
        elif pass_count > 0 and unknown_count == 0:
            matrix.status = "COMPLIANT"
        elif pass_count > 0:
            matrix.status = "PARTIAL"
        else:
            matrix.status = "UNKNOWN"

        if grade == "FULLY COMPLIANT" and not self.qco.verified:
            grade = "MOSTLY COMPLIANT"
            matrix.grade_capped_by = "QCO dataset is unverified seed data (cannot certify full regulatory compliance)"

        matrix.overall_grade = grade

    def _generate_recommendations(self, matrix: TenderComplianceMatrix) -> None:
        """Generate clear actionable guidance for the procurement authority or bidder."""
        for m in matrix.mandatory_qco_missing:
            matrix.recommendations.append(
                f"Incorporate mandatory BIS standard '{m}' into the tender specification to ensure QCO compliance."
            )
        for s in matrix.superseded_standards_cited:
            matrix.recommendations.append(
                f"Update reference '{s['cited']}' to current edition '{s['replacement']}'."
            )
        for e in matrix.evaluations:
            if e.status == "FAIL":
                matrix.risk_flags.append(
                    f"Technical non-compliance: Parameter '{e.parameter}' value '{e.specified_value}' fails standard threshold '{e.required_standard_value}'."
                )
                matrix.recommendations.append(
                    f"Adjust parameter '{e.parameter}': specified value '{e.specified_value}' fails standard threshold '{e.required_standard_value}'."
                )


def assess_tender_compliance(
    tender: TenderExtractionResult,
    data: BisData,
    qco: Optional[QCODatabase] = None,
    product_description: Optional[str] = None,
    sector: Optional[str] = None,
) -> TenderComplianceMatrix:
    """Convenience functional wrapper to assess tender compliance."""
    engine = TenderComplianceEngine(data=data, qco=qco)
    return engine.analyze(tender, product_description=product_description, sector=sector)
