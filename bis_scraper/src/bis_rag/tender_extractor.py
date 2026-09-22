"""Tender clause segmentation and technical requirement extraction engine.

Extracts structured clauses, technical requirements (parameters, values, units, operators,
categories, mandatory flags), and referenced Indian/international standards from ingested
tender documents (DocumentContent from PDF, DOCX, TXT).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from bis_api.document_reader import (
    DocumentContent,
    DocumentParagraph,
    DocumentSource,
    DocumentTable,
    read_document,
)
from bis_pipeline import iscode

log = logging.getLogger(__name__)

__all__ = [
    "TenderClause",
    "TenderRequirement",
    "TenderExtractionResult",
    "extract_tender_requirements",
    "extract_from_document",
    "extract_requirements_from_text",
    "extract_requirements_from_table",
    "find_standard_references",
    "classify_clause_type",
    "normalize_parameter_name",
    "parse_value_and_unit",
]

# ---------------------------------------------------------------------------
# DATA MODELS
# ---------------------------------------------------------------------------
@dataclass
class TenderClause:
    """A logical clause or section within a tender document."""

    clause_id: str
    title: str
    clause_type: str  # "technical" | "standards" | "commercial" | "scope" | "eligibility" | "general"
    text: str
    page_number: Optional[int] = None
    paragraph_index: Optional[int] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "clause_id": self.clause_id,
            "title": self.title,
            "clause_type": self.clause_type,
            "text": self.text,
            "page_number": self.page_number,
            "paragraph_index": self.paragraph_index,
        }


@dataclass
class TenderRequirement:
    """An individual technical, environmental, or commercial requirement extracted from tender."""

    requirement_id: str
    parameter: str
    specified_value: str
    numeric_value: Optional[float] = None
    numeric_max: Optional[float] = None  # for range requirements (e.g. 4000 to 5000 K)
    unit: str = ""
    operator: str = "exact"  # ">=", "<=", "==", "range", "exact", "min", "max"
    standard_references: list[str] = field(default_factory=list)
    category: str = "general"  # "electrical" | "photometric" | "mechanical" | "environmental" | "safety" | "commercial" | "materials" | "general"
    is_mandatory: bool = True
    source_location: str = ""
    raw_text: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "parameter": self.parameter,
            "specified_value": self.specified_value,
            "numeric_value": self.numeric_value,
            "numeric_max": self.numeric_max,
            "unit": self.unit,
            "operator": self.operator,
            "standard_references": self.standard_references,
            "category": self.category,
            "is_mandatory": self.is_mandatory,
            "source_location": self.source_location,
            "raw_text": self.raw_text,
        }


@dataclass
class TenderExtractionResult:
    """Complete structured extraction result for an ingested tender document."""

    source: DocumentSource
    clauses: list[TenderClause] = field(default_factory=list)
    requirements: list[TenderRequirement] = field(default_factory=list)
    detected_standards: list[str] = field(default_factory=list)
    total_requirements: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.as_dict() if hasattr(self.source, "as_dict") else str(self.source),
            "clauses": [c.as_dict() for c in self.clauses],
            "requirements": [r.as_dict() for r in self.requirements],
            "detected_standards": self.detected_standards,
            "total_requirements": self.total_requirements,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# PARAMETER & CATEGORY MAPPINGS
# ---------------------------------------------------------------------------
PARAMETER_CANONICAL_MAP: dict[str, tuple[str, str]] = {
    # Sorted by descending priority / specificity
    "correlated color temperature": ("Correlated Color Temperature (CCT)", "photometric"),
    "color rendering index": ("Color Rendering Index (CRI)", "photometric"),
    "total harmonic distortion": ("Total Harmonic Distortion (THD)", "electrical"),
    "degree of protection": ("Ingress Protection (IP)", "environmental"),
    "ingress protection": ("Ingress Protection (IP)", "environmental"),
    "protection class": ("Ingress Protection (IP)", "environmental"),
    "luminous efficacy": ("Luminous Efficacy", "photometric"),
    "system efficacy": ("Luminous Efficacy", "photometric"),
    "lumens per watt": ("Luminous Efficacy", "photometric"),
    "color temperature": ("Correlated Color Temperature (CCT)", "photometric"),
    "harmonic distortion": ("Total Harmonic Distortion (THD)", "electrical"),
    "operating voltage": ("Operating Voltage", "electrical"),
    "supply voltage": ("Operating Voltage", "electrical"),
    "rated voltage": ("Operating Voltage", "electrical"),
    "input voltage": ("Operating Voltage", "electrical"),
    "surge protection": ("Surge Protection", "electrical"),
    "power consumption": ("Power", "electrical"),
    "power factor": ("Power Factor", "electrical"),
    "impact resistance": ("Impact Resistance (IK)", "mechanical"),
    "tensile strength": ("Tensile Strength", "materials"),
    "yield strength": ("Yield Strength", "materials"),
    "coating thickness": ("Thickness / Coating", "materials"),
    "zinc coating": ("Galvanization", "materials"),
    "operating life": ("Life Expectancy", "photometric"),
    "life expectancy": ("Life Expectancy", "photometric"),
    "burning hours": ("Life Expectancy", "photometric"),
    "operating temperature": ("Operating Temperature", "environmental"),
    "ambient temperature": ("Operating Temperature", "environmental"),
    "lumen output": ("Luminous Flux", "photometric"),
    "rated power": ("Power", "electrical"),
    "system power": ("Power", "electrical"),
    "surge rating": ("Surge Protection", "electrical"),
    "galvanization": ("Galvanization", "materials"),
    "elongation": ("Elongation", "materials"),
    "thickness": ("Thickness / Coating", "materials"),
    "ip rating": ("Ingress Protection (IP)", "environmental"),
    "ik rating": ("Impact Resistance (IK)", "mechanical"),
    "guarantee": ("Warranty", "commercial"),
    "warranty": ("Warranty", "commercial"),
    "wattage": ("Power", "electrical"),
    "voltage": ("Operating Voltage", "electrical"),
    "efficacy": ("Luminous Efficacy", "photometric"),
    "lumens": ("Luminous Flux", "photometric"),
    "power": ("Power", "electrical"),
    "surge": ("Surge Protection", "electrical"),
    "watt": ("Power", "electrical"),
    "cct": ("Correlated Color Temperature (CCT)", "photometric"),
    "cri": ("Color Rendering Index (CRI)", "photometric"),
    "thd": ("Total Harmonic Distortion (THD)", "electrical"),
    "pf": ("Power Factor", "electrical"),
    "ik": ("Impact Resistance (IK)", "mechanical"),
    "ip": ("Ingress Protection (IP)", "environmental"),
    "ra": ("Color Rendering Index (CRI)", "photometric"),
}


def normalize_parameter_name(raw_param: str) -> tuple[str, str]:
    """Normalize a raw parameter string to (Canonical Parameter Name, Category)."""
    clean = re.sub(r"[:\-_()\[\]/]+", " ", raw_param).lower().strip()
    clean = " ".join(clean.split())

    # 1. Exact alias match
    if clean in PARAMETER_CANONICAL_MAP:
        return PARAMETER_CANONICAL_MAP[clean]

    # 2. Subphrase / word boundary match in descending order of alias length
    for alias, (canon, cat) in sorted(PARAMETER_CANONICAL_MAP.items(), key=lambda kv: len(kv[0]), reverse=True):
        pattern = rf"\b{re.escape(alias)}\b"
        if re.search(pattern, clean):
            return canon, cat

    # Default fallback
    title_case = " ".join(word.capitalize() for word in raw_param.strip().split())
    return title_case, "general"


# ---------------------------------------------------------------------------
# CLAUSE CLASSIFIER
# ---------------------------------------------------------------------------
def classify_clause_type(text: str, title: str = "") -> str:
    """Classify the type of clause based on title and content keywords."""
    combined = f"{title} {text}".lower()

    if any(k in combined for k in ["technical specification", "parameters", "ratings", "performance", "features", "technical requirements"]):
        return "technical"
    if any(k in combined for k in ["standard", "is code", "compliance", "certification", "bis", "iec", "iso standard"]):
        return "standards"
    if any(k in combined for k in ["warranty", "guarantee", "delivery", "payment terms", "penalty", "emd", "commercial", "security deposit"]):
        return "commercial"
    if any(k in combined for k in ["scope of work", "scope of supply", "brief description", "scope of procurement"]):
        return "scope"
    if any(k in combined for k in ["eligibility", "qualification", "turnover", "experience criteria"]):
        return "eligibility"
    return "general"


# ---------------------------------------------------------------------------
# STANDARD REFERENCE DETECTION
# ---------------------------------------------------------------------------
_STANDARDS_EXTENDED_RE = re.compile(
    r"\b((?:IS/IEC|IS/ISO|IS|IEC|ISO|SP)\s*:?\s*\d+(?:\s*[-.\u2013]\s*\d+)*(?:\s*\([^)]+\))?(?:\s*:\s*\d{4})?)",
    re.IGNORECASE,
)


def find_standard_references(text: str) -> list[str]:
    """Extract and canonically format all standard designations mentioned in text."""
    if not text:
        return []

    found: list[str] = []
    seen: set[str] = set()

    # 1. Use iscode parser for standard IS designations
    try:
        desigs = iscode.find_all(text)
        for d in desigs:
            formatted = d.format()
            if formatted not in seen:
                seen.add(formatted)
                found.append(formatted)
    except Exception:
        pass

    # 2. Regex fallback / supplement for international and complex notation
    for match in _STANDARDS_EXTENDED_RE.finditer(text):
        raw_match = match.group(1).strip()
        if len(raw_match) < 4:
            continue
        cleaned = re.sub(r"\s+", " ", raw_match)
        parsed = iscode.parse_designation(cleaned)
        canon = parsed.format() if parsed else cleaned
        if canon not in seen and not any(seen_std.startswith(canon) for seen_std in seen):
            seen.add(canon)
            found.append(canon)

    return found


# ---------------------------------------------------------------------------
# VALUE & OPERATOR PARSER
# ---------------------------------------------------------------------------
def parse_value_and_unit(raw_value: str) -> tuple[Optional[float], Optional[float], str, str]:
    """Parse specified text into (numeric_value, numeric_max, unit, operator)."""
    text = raw_value.strip()
    if not text:
        return None, None, "", "exact"

    # 1. Check for IP rating: IP65, IP66, IP 67
    ip_match = re.search(r"\bIP\s*([0-6X][0-9X])\b", text, re.IGNORECASE)
    if ip_match:
        ip_code = f"IP{ip_match.group(1).upper()}"
        op = ">=" if any(w in text.lower() for w in ["min", "at least", "not less than", ">="]) else "exact"
        return None, None, "IP", op

    # 2. Check for IK rating: IK08, IK10
    ik_match = re.search(r"\bIK\s*0?(\d{1,2})\b", text, re.IGNORECASE)
    if ik_match:
        return float(ik_match.group(1)), None, "IK", ">=" if any(w in text.lower() for w in ["min", "at least", "not less than", ">="]) else "exact"

    # 3. Check for range: e.g. "4000 K - 5000 K" or "4000 to 5000 K" or "140 V - 270 V"
    range_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:[A-Za-z/%]+)?\s*(?:to|-|\u2013)\s*(\d+(?:\.\d+)?)\s*([A-Za-z/%]+)?",
        text,
        re.IGNORECASE,
    )
    if range_match and not re.search(r"^\d{4}-\d{2}-\d{2}", text):  # guard against dates
        v_min = float(range_match.group(1))
        v_max = float(range_match.group(2))
        unit = range_match.group(3) or ""
        return v_min, v_max, unit.strip(), "range"

    # 4. Check for comparison operators: >=, <=, >, <, min, max
    op = "exact"
    if ">=" in text or "≥" in text or re.search(r"\b(min|minimum|at\s+least|not\s+less\s+than)\b", text, re.IGNORECASE):
        op = ">="
    elif "<=" in text or "≤" in text or re.search(r"\b(max|maximum|at\s+most|not\s+more\s+than|not\s+exceeding)\b", text, re.IGNORECASE):
        op = "<="
    elif ">" in text:
        op = ">"
    elif "<" in text:
        op = "<"

    # 5. Extract first number and following unit
    num_match = re.search(r"(\d+(?:\.\d+)?)\s*([A-Za-z/%]+)?", text)
    if num_match:
        val = float(num_match.group(1))
        unit = (num_match.group(2) or "").strip()
        return val, None, unit, op

    return None, None, "", op


# ---------------------------------------------------------------------------
# TABLE REQUIREMENT EXTRACTION
# ---------------------------------------------------------------------------
def extract_requirements_from_table(table: DocumentTable, start_req_id: int = 1) -> list[TenderRequirement]:
    """Extract structured technical requirements from a DocumentTable."""
    requirements: list[TenderRequirement] = []
    if not table.rows or len(table.rows) < 2:
        return requirements

    header = [cell.lower().strip() for cell in table.rows[0]]

    param_col = -1
    val_col = -1
    std_col = -1
    unit_col = -1

    for idx, col in enumerate(header):
        if any(k in col for k in ["parameter", "description", "item", "particular", "feature", "property", "technical requirement", "clause"]):
            if param_col == -1:
                param_col = idx
        elif any(k in col for k in ["requirement", "specified", "specification", "value", "limit", "desired", "ratings"]):
            if val_col == -1:
                val_col = idx
        elif any(k in col for k in ["standard", "is code", "reference", "applicable standard", "bis"]):
            if std_col == -1:
                std_col = idx
        elif any(k in col for k in ["unit", "uom"]):
            if unit_col == -1:
                unit_col = idx

    if param_col == -1 and len(table.rows[0]) >= 2:
        param_col = 0
        val_col = 1
        if len(table.rows[0]) >= 3:
            std_col = 2
    elif val_col == -1 and len(table.rows[0]) >= 2 and param_col != 1:
        val_col = 1

    current_id = start_req_id

    for r_idx, row in enumerate(table.rows[1:], start=1):
        if not any(cell.strip() for cell in row):
            continue

        raw_param = row[param_col].strip() if 0 <= param_col < len(row) else ""
        raw_val = row[val_col].strip() if 0 <= val_col < len(row) else ""
        raw_std = row[std_col].strip() if 0 <= std_col < len(row) else ""
        explicit_unit = row[unit_col].strip() if 0 <= unit_col < len(row) else ""

        if not raw_param and not raw_val:
            continue

        if not raw_param:
            continue

        canon_param, category = normalize_parameter_name(raw_param)

        full_val_str = f"{raw_val} {explicit_unit}".strip() if explicit_unit else raw_val
        num_val, num_max, parsed_unit, op = parse_value_and_unit(full_val_str)

        final_unit = explicit_unit or parsed_unit

        stds = find_standard_references(f"{raw_std} {raw_val} {raw_param}")

        req = TenderRequirement(
            requirement_id=f"REQ-{current_id:03d}",
            parameter=canon_param,
            specified_value=full_val_str or raw_val,
            numeric_value=num_val,
            numeric_max=num_max,
            unit=final_unit,
            operator=op,
            standard_references=stds,
            category=category,
            is_mandatory=True,
            source_location=f"Table {table.table_index}, Row {r_idx}",
            raw_text=f"{raw_param}: {full_val_str} ({raw_std})".strip(),
        )
        requirements.append(req)
        current_id += 1

    return requirements


# ---------------------------------------------------------------------------
# TEXT / PARAGRAPH REQUIREMENT EXTRACTION
# ---------------------------------------------------------------------------
_LINK_PHRASES = r"(?:shall\s+be|shall\s+be\s+minimum|shall\s+not\s+exceed|not\s+less\s+than|minimum\s+of|at\s+least|maximum\s+of|minimum|maximum|of|:|to\s+be|should\s+be)?"

_KEY_PARAM_REGEX_PATTERNS: list[tuple[str, str, str, str]] = [
    # (regex_pattern, canonical_param, category, default_unit)
    (
        rf"(?:power\s+(?:consumption|rating)?|wattage)\s*{_LINK_PHRASES}\s*(?:>=|<=|==|!=|>|<|≤|≥|=)?\s*(\d+(?:\.\d+)?)\s*(W|kW|watts?)\b",
        "Power",
        "electrical",
        "W",
    ),
    (
        rf"(?:luminous\s+efficacy|system\s+efficacy|efficacy)\s*{_LINK_PHRASES}\s*(?:>=|<=|==|!=|>|<|≤|≥|=)?\s*(\d+(?:\.\d+)?)\s*(lm/W|lumens/watt|lumens/W)\b",
        "Luminous Efficacy",
        "photometric",
        "lm/W",
    ),
    (
        r"(?:cct|correlated\s+color\s+temperature|color\s+temperature)\s*(?:shall\s+be|of|:)?\s*(\d{4})\s*(?:K)?\s*(?:to|-|\u2013)\s*(\d{4})\s*(K)?\b",
        "Correlated Color Temperature (CCT)",
        "photometric",
        "K",
    ),
    (
        r"(?:cct|correlated\s+color\s+temperature|color\s+temperature)\s*(?:shall\s+be|of|:)?\s*(\d{4})\s*(K)?\b",
        "Correlated Color Temperature (CCT)",
        "photometric",
        "K",
    ),
    (
        rf"(?:cri|color\s+rendering\s+index|ra)\s*{_LINK_PHRASES}\s*(?:>=|<=|==|!=|>|<|≤|≥|=)?\s*(\d+(?:\.\d+)?)\b",
        "Color Rendering Index (CRI)",
        "photometric",
        "",
    ),
    (
        rf"(?:ingress\s+protection|degree\s+of\s+protection|ip\s+rating|protection\s+level)\s*{_LINK_PHRASES}\s*(?:minimum|at\s+least|not\s+less\s+than)?\s*(IP\s*[0-6X][0-9X])\b",
        "Ingress Protection (IP)",
        "environmental",
        "IP",
    ),
    (
        rf"(?:surge\s+protection|surge\s+rating|surge\s+withstand)\s*{_LINK_PHRASES}\s*(?:>=|<=|==|!=|>|<|≤|≥|=)?\s*(\d+(?:\.\d+)?)\s*(kV|volts?|V)\b",
        "Surge Protection",
        "electrical",
        "kV",
    ),
    (
        rf"(?:rated\s+supply\s+voltage|operating\s+voltage|supply\s+voltage|rated\s+voltage)\s*{_LINK_PHRASES}\s*(\d+(?:\.\d+)?)\s*(?:V|volts?)?\s*(?:to|-|\u2013)\s*(\d+(?:\.\d+)?)\s*(V|kV|volts?)\b",
        "Operating Voltage",
        "electrical",
        "V",
    ),
    (
        rf"(?:rated\s+supply\s+voltage|operating\s+voltage|supply\s+voltage|rated\s+voltage)\s*{_LINK_PHRASES}\s*(\d+(?:\.\d+)?)\s*(V|kV|volts?)(?:\s*(?:AC|DC))?\b",
        "Operating Voltage",
        "electrical",
        "V",
    ),
    (
        rf"(?:power\s+factor|pf)\s*{_LINK_PHRASES}\s*(?:>=|<=|==|!=|>|<|≤|≥|=)?\s*(\d+(?:\.\d+)?)\b",
        "Power Factor",
        "electrical",
        "",
    ),
    (
        rf"(?:total\s+harmonic\s+distortion|thd)\s*{_LINK_PHRASES}\s*(?:>=|<=|==|!=|>|<|≤|≥|=)?\s*(\d+(?:\.\d+)?)\s*%",
        "Total Harmonic Distortion (THD)",
        "electrical",
        "%",
    ),
    (
        rf"(?:tensile\s+strength)\s*{_LINK_PHRASES}\s*(?:>=|<=|==|!=|>|<|≤|≥|=)?\s*(\d+(?:\.\d+)?)\s*(?:MPa|N/mm2|n/mm²)",
        "Tensile Strength",
        "materials",
        "MPa",
    ),
    (
        rf"(?:yield\s+strength)\s*{_LINK_PHRASES}\s*(?:>=|<=|==|!=|>|<|≤|≥|=)?\s*(\d+(?:\.\d+)?)\s*(?:MPa|N/mm2|n/mm²)",
        "Yield Strength",
        "materials",
        "MPa",
    ),
    (
        rf"(?:warranty|guarantee)\s*{_LINK_PHRASES}\s*(?:minimum\s+of)?\s*(\d+)\s*(years?|months?)\b",
        "Warranty",
        "commercial",
        "years",
    ),
    (
        rf"(?:burning\s+hours|operating\s+life|life\s+expectancy|useful\s+life)\s*{_LINK_PHRASES}\s*(?:>=|<=|==|!=|>|<|≤|≥|=)?\s*(\d+(?:,\d+)?)\s*(hours?|hrs)\b",
        "Life Expectancy",
        "photometric",
        "hours",
    ),
    (
        rf"(?:impact\s+resistance|ik\s+rating)\s*{_LINK_PHRASES}\s*(IK\s*0?\d{1,2})\b",
        "Impact Resistance (IK)",
        "mechanical",
        "IK",
    ),
]


def extract_requirements_from_text(
    text: str,
    source_location: str = "",
    start_req_id: int = 1,
) -> list[TenderRequirement]:
    """Extract structured requirements from free text/paragraphs using regex rules."""
    requirements: list[TenderRequirement] = []
    if not text:
        return requirements

    current_id = start_req_id
    seen_params: set[str] = set()

    for pattern, canon_param, category, default_unit in _KEY_PARAM_REGEX_PATTERNS:
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        for m in matches:
            if canon_param in seen_params:
                continue

            raw_snippet = m.group(0).strip()
            num_val, num_max, parsed_unit, op = parse_value_and_unit(raw_snippet)

            start_window = max(0, m.start() - 100)
            end_window = min(len(text), m.end() + 100)
            vicinity_text = text[start_window:end_window]
            stds = find_standard_references(vicinity_text)

            is_mandatory = any(k in text.lower() for k in ["shall", "must", "mandatory", "required", "minimum"])

            req = TenderRequirement(
                requirement_id=f"REQ-{current_id:03d}",
                parameter=canon_param,
                specified_value=raw_snippet,
                numeric_value=num_val,
                numeric_max=num_max,
                unit=parsed_unit or default_unit,
                operator=op,
                standard_references=stds,
                category=category,
                is_mandatory=is_mandatory,
                source_location=source_location,
                raw_text=raw_snippet,
            )
            requirements.append(req)
            seen_params.add(canon_param)
            current_id += 1

    return requirements


# ---------------------------------------------------------------------------
# MAIN TENDER EXTRACTION PIPELINE
# ---------------------------------------------------------------------------
def extract_tender_requirements(doc: DocumentContent | str) -> TenderExtractionResult:
    """Segment clauses and extract all technical requirements and standard references from DocumentContent or raw text."""
    if isinstance(doc, str):
        read_res = read_document(doc.encode("utf-8"), filename="tender_text.txt", media_type="text/plain")
        if not read_res.ok or read_res.document is None:
            source = DocumentSource(filename="tender_text.txt", media_type="text/plain", extension=".txt", source_type="txt")
            return TenderExtractionResult(
                source=source,
                clauses=[],
                requirements=[],
                detected_standards=[],
                total_requirements=0,
                warnings=[read_res.error_message or "Failed to read text."],
            )
        doc = read_res.document

    clauses: list[TenderClause] = []
    requirements: list[TenderRequirement] = []
    all_standards: list[str] = []
    seen_standards: set[str] = set()
    warnings: list[str] = list(doc.warnings)


    req_id_counter = 1

    # 1. Segment Clauses from Paragraphs
    current_clause_type = "general"
    current_clause_title = "General Tender Terms"

    for idx, p in enumerate(doc.paragraphs):
        p_text = p.text.strip()
        if not p_text:
            continue

        is_heading = (
            "Heading" in p.style
            or re.match(r"^(?:Section|Clause|Part|\d+\.0?|\d+\.\d+)\s+", p_text, re.IGNORECASE)
            or (len(p_text) < 80 and p_text.isupper())
        )

        if is_heading:
            current_clause_title = p_text
            current_clause_type = classify_clause_type(p_text, current_clause_title)
            clause_id = f"CL-{len(clauses) + 1:02d}"
            clauses.append(
                TenderClause(
                    clause_id=clause_id,
                    title=current_clause_title,
                    clause_type=current_clause_type,
                    text=p_text,
                    paragraph_index=p.paragraph_index,
                )
            )

        p_stds = find_standard_references(p_text)
        for s in p_stds:
            if s not in seen_standards:
                seen_standards.add(s)
                all_standards.append(s)

        loc_str = f"Paragraph {p.paragraph_index}"
        p_reqs = extract_requirements_from_text(p_text, source_location=loc_str, start_req_id=req_id_counter)
        for r in p_reqs:
            requirements.append(r)
            req_id_counter += 1

    # 2. Extract Requirements from Tables
    for tbl in doc.tables:
        tbl_reqs = extract_requirements_from_table(tbl, start_req_id=req_id_counter)
        for r in tbl_reqs:
            requirements.append(r)
            req_id_counter += 1
            for s in r.standard_references:
                if s not in seen_standards:
                    seen_standards.add(s)
                    all_standards.append(s)

    # 3. Global scan over full_text for any remaining standard citations
    full_stds = find_standard_references(doc.full_text)
    for s in full_stds:
        if s not in seen_standards:
            seen_standards.add(s)
            all_standards.append(s)

    if not requirements:
        warnings.append("No structured technical requirements could be extracted from the document.")

    return TenderExtractionResult(
        source=doc.source,
        clauses=clauses,
        requirements=requirements,
        detected_standards=all_standards,
        total_requirements=len(requirements),
        warnings=warnings,
    )


def extract_from_document(
    data: bytes,
    filename: str = "",
    media_type: str = "",
) -> TenderExtractionResult:
    """Convenience helper reading raw document bytes and extracting tender requirements."""
    read_res = read_document(data, filename=filename, media_type=media_type)
    if not read_res.ok or read_res.document is None:
        source = DocumentSource(filename=filename, media_type=media_type)
        return TenderExtractionResult(
            source=source,
            clauses=[],
            requirements=[],
            detected_standards=[],
            total_requirements=0,
            warnings=[read_res.error_message or "Failed to read document."],
        )
    return extract_tender_requirements(read_res.document)
