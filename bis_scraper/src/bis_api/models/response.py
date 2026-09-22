"""Response models.

These mirror what the engine already returns (``SearchResponse.as_dict``,
``RAGAnswer.as_dict``, ``ComplianceReport.as_dict``) with the fields the API
promises. They are declared rather than passed through as raw dicts so that the
OpenAPI schema at ``/docs`` is accurate -- a schema that says ``object`` is not
documentation.

``extra="allow"`` on the pass-through models is deliberate: the engine may add
fields (a new warning category, another provenance key), and dropping them here
would silently remove information a client could use.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "CitationOut", "ResultOut", "SearchResponseOut", "RecommendResponseOut",
    "ComplianceResponseOut", "StandardDetailOut", "HealthOut", "FeedbackOut",
    "PdfExtractionOut", "ErrorOut", "ProductUnderstandingOut",
    "ApplicableStandardOut", "RelatedStandardOut", "EvidenceItemOut",
    "StructuredReportOut",
]


class CitationOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    designation: str = ""
    title: str = ""
    canonical: str = ""
    is_current: bool = True
    superseded_by: str = ""
    archive_url: str = ""


class ResultOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = ""
    designation: str = ""
    title: str = ""
    division: str = ""
    year: Optional[int] = None
    is_current: bool = True
    score: float = 0.0
    rerank_score: Optional[float] = None
    #: retriever name -> rank. Which retrievers found this result.
    found_by: dict[str, int] = Field(default_factory=dict)
    archive_url: str = ""
    text: str = ""


class SearchResponseOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    query: str
    intent: str = ""
    filter: Optional[dict[str, Any]] = None
    reranker: str = ""
    notes: list[str] = Field(default_factory=list)
    supersession_warnings: list[dict[str, Any]] = Field(default_factory=list)
    results: list[ResultOut] = Field(default_factory=list)
    #: Server-side duration, so a client can verify the fast path itself.
    took_ms: float = 0.0


class PdfExtractionOut(BaseModel):
    extractor: str = "none"
    pages: int = 0
    chars: int = 0
    ok: bool = False
    reason: str = ""
    warnings: list[str] = Field(default_factory=list)


class ProductUnderstandingOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    product: str = ""
    application: str = ""
    specifications: dict[str, str] = Field(default_factory=dict)


class ApplicableStandardOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    designation: str = ""
    title: str = ""
    relevance: str = "Applicable"
    reason: str = ""
    status: str = "current"


class RelatedStandardOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    designation: str = ""
    title: str = ""
    relationship: str = "Related"


class EvidenceItemOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    designation: str = ""
    chunk_id: str = ""
    reason: str = ""


class StructuredReportOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    summary: str = ""
    product_understanding: ProductUnderstandingOut = Field(default_factory=ProductUnderstandingOut)
    applicable_standards: list[ApplicableStandardOut] = Field(default_factory=list)
    related_standards: list[RelatedStandardOut] = Field(default_factory=list)
    compliance_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItemOut] = Field(default_factory=list)


class RecommendResponseOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    question: str
    answer: str
    #: ``"llm"`` when a model wrote the prose, ``"extractive"`` when the answer
    #: was assembled from retrieved passages without one.
    mode: str = "extractive"
    generator: str = ""
    intent: str = ""
    #: False when the answer cited a standard that was never retrieved.
    grounded: bool = True
    citations: list[CitationOut] = Field(default_factory=list)
    unsupported_citations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    compliance: Optional[dict[str, Any]] = None
    report: Optional[StructuredReportOut] = None
    passages: Optional[list[ResultOut]] = None
    #: Present only on the PDF endpoint.
    source_document: Optional[PdfExtractionOut] = None
    #: IS designations found inside the uploaded document.
    detected_designations: Optional[list[str]] = None
    took_ms: float = 0.0


class ComplianceResponseOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    product_description: str = ""
    sector: Optional[str] = None
    compliance_status: str = ""
    grade: str = ""
    compliance_score: float = 0.0
    qco_source: str = ""
    qco_verified: bool = False
    mandatory_expected: list[str] = Field(default_factory=list)
    mandatory_present: list[str] = Field(default_factory=list)
    mandatory_missing: list[str] = Field(default_factory=list)
    mandatory_candidates: list[str] = Field(default_factory=list)
    sector_candidates: list[str] = Field(default_factory=list)
    superseded_used: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    product_specifications: dict[str, Any] = Field(default_factory=dict)
    specification_checks: list[dict[str, Any]] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    took_ms: float = 0.0


class StandardDetailOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    designation: str = ""
    canonical: str = ""
    title: str = ""
    division: str = ""
    committee: str = ""
    year: Optional[int] = None
    is_current: bool = True
    status: str = ""
    superseded_by: str = ""
    is_compulsory: bool = False
    keywords: list[str] = Field(default_factory=list)
    archive_url: str = ""
    #: Present when this standard has been replaced.
    supersession: Optional[dict[str, Any]] = None
    #: Other standards in the same division.
    related: list[dict[str, Any]] = Field(default_factory=list)


class HealthOut(BaseModel):
    status: str = "ok"
    version: str = ""
    #: ``ok`` | ``degraded`` | ``unavailable``
    detail: str = ""
    corpus: dict[str, Any] = Field(default_factory=dict)
    retrieval: dict[str, Any] = Field(default_factory=dict)
    qco: dict[str, Any] = Field(default_factory=dict)
    llm: dict[str, Any] = Field(default_factory=dict)
    startup_ms: float = 0.0
    uptime_s: float = 0.0
    issues: list[str] = Field(default_factory=list)


class FeedbackOut(BaseModel):
    saved: bool = False
    path: str = ""
    message: str = ""


class ErrorOut(BaseModel):
    """Every error response has this shape. Clients should not have to parse prose."""

    error: str
    detail: str = ""
    request_id: str = ""
    status_code: int = 500


# ----------------------------------------------------------------------
# Tender Analysis & Compliance Models
# ----------------------------------------------------------------------
class TenderClauseOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    clause_id: str = ""
    title: str = ""
    clause_type: str = "general"
    text: str = ""
    page_number: Optional[int] = None
    paragraph_index: Optional[int] = None


class TenderRequirementOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    requirement_id: str = ""
    parameter: str = ""
    specified_value: str = ""
    numeric_value: Optional[float] = None
    numeric_max: Optional[float] = None
    unit: str = ""
    operator: str = "exact"
    standard_references: list[str] = Field(default_factory=list)
    category: str = "general"
    is_mandatory: bool = True
    source_location: str = ""
    raw_text: str = ""


class TenderStandardAssessmentOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    designation: str = ""
    title: str = ""
    applicability: str = "CANDIDATE"
    applicability_reason: str = ""
    is_mandatory_qco: bool = False
    is_current: bool = True
    superseded_by: Optional[str] = None
    citation_source: str = "explicit_tender_citation"


class TenderRequirementEvaluationOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    requirement_id: str = ""
    parameter: str = ""
    specified_value: str = ""
    numeric_value: Optional[float] = None
    numeric_max: Optional[float] = None
    unit: str = ""
    operator: str = "exact"
    standard: str = ""
    required_standard_value: str = ""
    status: str = "UNKNOWN"
    evaluation_reason: str = ""
    clause_reference: str = ""
    evidence_text: str = ""
    is_mandatory: bool = True
    category: str = "general"
    risk_level: str = "LOW"


class TenderComplianceMatrixOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    product_description: str = ""
    sector: Optional[str] = None
    evaluations: list[TenderRequirementEvaluationOut] = Field(default_factory=list)
    standards_assessed: list[TenderStandardAssessmentOut] = Field(default_factory=list)
    mandatory_qco_expected: list[str] = Field(default_factory=list)
    mandatory_qco_present: list[str] = Field(default_factory=list)
    mandatory_qco_missing: list[str] = Field(default_factory=list)
    superseded_standards_cited: list[dict[str, Any]] = Field(default_factory=list)
    conflicts_detected: list[dict[str, str]] = Field(default_factory=list)
    compliance_score: float = 0.0
    overall_grade: str = "UNKNOWN"
    status: str = "UNKNOWN"
    grade_capped_by: str = ""
    risk_flags: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class TenderAnalysisResponseOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    filename: str = ""
    media_type: str = ""
    source_type: str = ""
    character_count: int = 0
    page_count: int = 0
    clauses: list[TenderClauseOut] = Field(default_factory=list)
    requirements: list[TenderRequirementOut] = Field(default_factory=list)
    detected_standards: list[str] = Field(default_factory=list)
    compliance_matrix: TenderComplianceMatrixOut
    took_ms: float = 0.0
    warnings: list[str] = Field(default_factory=list)

