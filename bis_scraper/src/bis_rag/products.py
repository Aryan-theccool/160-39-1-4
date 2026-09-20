"""Product-to-standards recommendation engine for procurement.

Deterministic (no ML, no fine-tuning). Reuses hybrid search and compliance checking.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

from .compliance import ComplianceChecker, QCODatabase, detect_sector
from .data import BisData
from .hybrid import HybridSearch, SearchResult
from .schema import Standard

log = logging.getLogger(__name__)

__all__ = [
    "ProductDescriptor",
    "normalize_product",
    "classify_role",
    "ProductRecommendation",
    "RecommendationRow",
    "recommend_for_product",
    "load_product_aliases",
]


@dataclass
class ProductDescriptor:
    """Parsed product description."""
    raw: str
    normalized: str
    attributes: dict[str, list[str]]
    aliases_matched: list[tuple[str, list[str]]]  # (alias, designations)
    sector: Optional[str]
    sector_hits: dict[str, int]


@dataclass
class RecommendationRow:
    """A single recommended standard with evidence."""
    designation: str
    title: str
    is_current: bool
    is_mandatory: bool
    mandatory_order: Optional[str]
    role: str  # "product_standard" | "test_method" | "code_of_practice" | "packaging_marking" | "other"
    score: float
    why: str  # evidence: "alias:ordinary portland cement" | "title:cement" | "hybrid:0.87"


@dataclass
class ProductRecommendation:
    """Output of recommend_for_product."""
    product: ProductDescriptor
    primary: list[RecommendationRow]
    related: list[RecommendationRow]
    mandatory: dict[str, list[str]]  # designation -> [order, date]
    checklist: list[dict[str, Any]]  # for CSV download
    coverage: dict[str, Any]  # {has_alias_hit: bool, has_title_match: bool, warnings: [...]}
    took_ms: float


def load_product_aliases(data_dir: Path) -> dict[str, dict[str, Any]]:
    """Load product_aliases.json."""
    aliases_path = data_dir / "product_aliases.json"
    if not aliases_path.exists():
        log.warning(f"product_aliases.json not found at {aliases_path}")
        return {}
    
    with open(aliases_path) as f:
        data = json.load(f)
    
    # Build a map: alias/phrase -> designations
    lookup = {}
    for product in data.get("products", []):
        phrase = product["phrase"].lower()
        designations = product.get("designations", [])
        
        lookup[phrase] = {
            "designations": designations,
            "aliases": product.get("aliases", []),
            "sector": product.get("sector"),
            "attributes": product.get("attributes", {}),
        }
        
        # Also index by each alias
        for alias in product.get("aliases", []):
            lookup[alias.lower()] = {
                "designations": designations,
                "primary_phrase": phrase,
                "sector": product.get("sector"),
            }
    
    return lookup


def normalize_product(text: str, aliases: dict[str, dict[str, Any]]) -> ProductDescriptor:
    """Parse a product description.
    
    - Lowercase
    - Expand aliases from product_aliases.json
    - Extract grade/size attributes
    - Detect sector
    """
    raw = text.strip()
    normalized = raw.lower()
    
    # Extract grade attributes (e.g., "43 grade", "m25", "m20")
    attributes = {}
    
    grade_pattern = r'\b(33|43|53)\s+grade\b'
    grades = re.findall(grade_pattern, normalized)
    if grades:
        attributes["grade"] = grades
    
    concrete_grade_pattern = r'\b(m\d{2}|m\d{3})\b'
    concrete_grades = re.findall(concrete_grade_pattern, normalized)
    if concrete_grades:
        attributes["concrete_grade"] = concrete_grades
    
    size_pattern = r'\b(\d+)\s*mm\b'
    sizes = re.findall(size_pattern, normalized)
    if sizes:
        attributes["size"] = sizes
    
    # Match against aliases
    aliases_matched = []
    for phrase, data in aliases.items():
        if phrase in normalized:
            aliases_matched.append((phrase, data.get("designations", [])))
    
    # Sort by length (longest first, to avoid partial matches)
    aliases_matched.sort(key=lambda x: len(x[0]), reverse=True)
    
    # Detect sector
    sector, sector_hits = detect_sector(raw)
    
    return ProductDescriptor(
        raw=raw,
        normalized=normalized,
        attributes=attributes,
        aliases_matched=aliases_matched,
        sector=sector,
        sector_hits=sector_hits,
    )


def classify_role(title: str) -> str:
    """Classify a standard by its role from the title.
    
    Rules (deterministic, not guessing):
    - "Methods of test" / "Method of test" -> test_method
    - "Code of practice" -> code_of_practice
    - "Packaging" / "Marking" / "Marking and labelling" -> packaging_marking
    - Otherwise -> product_standard or other
    """
    title_lower = title.lower()
    
    if "method" in title_lower and "test" in title_lower:
        return "test_method"
    
    if "code of practice" in title_lower:
        return "code_of_practice"
    
    if any(w in title_lower for w in ["packaging", "marking", "labelling"]):
        return "packaging_marking"
    
    if "specification" in title_lower or "requirement" in title_lower:
        return "product_standard"
    
    return "other"


def recommend_for_product(
    data: BisData,
    search: HybridSearch,
    description: str,
    limit: int = 8,
    aliases: Optional[dict[str, dict[str, Any]]] = None,
    qco_db: Optional[QCODatabase] = None,
) -> ProductRecommendation:
    """Recommend standards for a product description.
    
    Algorithm:
    1. Normalize product
    2. Find alias hits (highest confidence)
    3. Hybrid search for the product phrase
    4. Classify role of each result
    5. Overlay QCO mandatory status
    6. Rank and cap primary at 5
    7. Return with full evidence
    """
    import time
    started = time.perf_counter()
    
    if not aliases:
        aliases = load_product_aliases(data.root)
    
    if not qco_db:
        try:
            qco_db = QCODatabase(data)
        except Exception as e:
            log.warning(f"Could not load QCO database: {e}")
            qco_db = None
    
    # Normalize
    product = normalize_product(description, aliases)
    
    # Gather candidates: (designation, title, source, score)
    candidates_by_designation = {}
    
    # 1. Alias hits (highest confidence)
    for alias, designations in product.aliases_matched:
        for designation in designations:
            # Verify designation exists in corpus
            std = data.resolve_designation(designation)
            if std:
                if designation not in candidates_by_designation:
                    candidates_by_designation[designation] = {
                        "standard": std,
                        "score": 1.0,
                        "why": f"alias:{alias}",
                    }
    
    # 2. Hybrid search for the product phrase
    search_result = search.search(description, top_k=20, mode="recommend")
    
    for result in search_result.results:
        designation = result.designation
        if designation not in candidates_by_designation:
            candidates_by_designation[designation] = {
                "standard": result,
                "score": result.score,
                "why": f"hybrid:{result.score:.2f}",
            }
        # Prefer alias hit, but keep hybrid score as fallback
        elif result.score > candidates_by_designation[designation]["score"]:
            candidates_by_designation[designation]["score"] = result.score
    
    # 3. Convert to rows with role classification and QCO overlay
    rows = []
    mandatory_set = set()
    
    for designation, data_dict in candidates_by_designation.items():
        std = data_dict["standard"]
        score = data_dict["score"]
        why = data_dict["why"]
        
        role = classify_role(std.title)
        
        # QCO overlay
        is_mandatory = False
        order = None
        if qco_db:
            is_mandatory = qco_db.is_mandatory(designation)
            if is_mandatory:
                entry = qco_db.lookup(designation)
                order = f"{entry.sector} (source: {entry.source})" if entry else "Mandatory"
        if is_mandatory:
            mandatory_set.add(designation)
        
        # Build row
        row = RecommendationRow(
            designation=designation,
            title=std.title,
            is_current=std.is_current,
            is_mandatory=is_mandatory,
            mandatory_order=order,
            role=role,
            score=score,
            why=why,
        )
        rows.append(row)
    
    # 4. Rank: mandatory first, then by score, cap primary at 5
    rows.sort(key=lambda r: (-r.is_mandatory, -r.score))
    
    primary = [r for r in rows if r.role == "product_standard"][:5]
    related = [r for r in rows if r.role != "product_standard"][:10]
    
    # 5. Check coverage
    has_alias_hit = len(product.aliases_matched) > 0
    has_title_match = len([r for r in rows if "hybrid" in r.why]) > 0
    
    warnings = []
    if not has_alias_hit and not has_title_match:
        warnings.append("No direct product match found. Try more specific terms or check related standards.")
    
    if not primary:
        warnings.append("No primary product standards found. Check 'Related standards' for test methods or codes of practice.")
    
    coverage = {
        "has_alias_hit": has_alias_hit,
        "has_title_match": has_title_match,
        "warnings": warnings,
    }
    
    # 6. Build checklist for download
    checklist = []
    for r in primary + related:
        checklist.append({
            "designation": r.designation,
            "title": r.title,
            "role": r.role,
            "mandatory": "Yes" if r.is_mandatory else "No",
            "current": "Yes" if r.is_current else "No",
            "why": r.why,
        })
    
    # 7. Build mandatory dict
    mandatory_dict = {}
    for r in primary + related:
        if r.is_mandatory:
            mandatory_dict[r.designation] = r.mandatory_order or "Mandatory (source unknown)"
    
    took_ms = (time.perf_counter() - started) * 1000
    
    return ProductRecommendation(
        product=product,
        primary=primary,
        related=related,
        mandatory=mandatory_dict,
        checklist=checklist,
        coverage=coverage,
        took_ms=took_ms,
    )
