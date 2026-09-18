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
    "PdfExtractionOut", "ErrorOut",
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
