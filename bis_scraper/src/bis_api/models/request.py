"""Request models.

Validation lives here rather than in the handlers so that a bad request is
rejected with a field-level 422 before any work happens -- including before a
rate-limit slot is consumed by a request that could never have succeeded.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "RecommendRequest", "SearchRequest", "ComplianceRequest", "FeedbackRequest",
    "ReportExportRequest",
]


class RecommendRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000,
                       description="Natural-language question about Indian Standards",
                       examples=["What standard covers drinking water quality?"])
    top_k: int = Field(6, ge=1, le=20, description="Number of passages to retrieve")
    include_passages: bool = Field(
        False, description="Include the retrieved passages in the response")
    sector: Optional[str] = Field(
        None, description="Override sector detection for the compliance section")

    @field_validator("query")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value.strip()


class SearchRequest(BaseModel):
    """Body form of ``/search``. The query-string form is on ``GET /search``."""

    q: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(10, ge=1, le=50)
    division: Optional[str] = Field(None, description="Filter by BIS division")
    committee: Optional[str] = None
    include_superseded: bool = Field(
        False, description="Include superseded editions (off by default)")


class ComplianceRequest(BaseModel):
    product_description: str = Field("", max_length=2000,
                                     description="What the product is, in words")
    standards: list[str] = Field(
        default_factory=list, max_length=100,
        description="Standards in use, e.g. ['IS 302', 'IS 694:2010']")
    sector: Optional[str] = Field(None, description="Override sector detection")

    @field_validator("standards")
    @classmethod
    def _clean(cls, values: list[str]) -> list[str]:
        out: list[str] = []
        for value in values:
            text = (value or "").strip()
            if not text:
                continue
            if len(text) > 200:
                raise ValueError(f"standard designation too long: {text[:40]!r}...")
            out.append(text)
        return out


class FeedbackRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    helpful: bool
    correct_is: Optional[str] = Field(
        None, max_length=200,
        description="The designation the user expected, if the answer was wrong")
    comment: Optional[str] = Field(None, max_length=2000)
    #: Echoed back from a response's ``X-Request-ID`` so feedback can be joined
    #: to the exact answer it is about.
    request_id: Optional[str] = Field(None, max_length=64)


class ReportExportRequest(BaseModel):
    """Payload for generating downloadable DOCX and PDF procurement reports."""
    model_config = ConfigDict(extra="allow")

    question: str = Field("", description="Original query or procurement specification")
    answer: str = Field("", description="Generated or extracted prose answer")
    mode: str = Field("llm", description="'llm' or 'extractive'")
    generator: str = Field("", description="Generator provider name")
    grounded: bool = Field(True, description="Whether citations are grounded in evidence")
    report: Optional[dict[str, Any]] = Field(None, description="Structured procurement report dictionary")
    citations: list[dict[str, Any]] = Field(default_factory=list, description="List of standard citations")
    unsupported_citations: list[str] = Field(default_factory=list, description="Ungrounded citation designations")
    warnings: list[str] = Field(default_factory=list, description="Supersession and compliance warnings")


class TenderAnalyzeTextRequest(BaseModel):
    """Payload for analyzing direct tender text/prose."""
    model_config = ConfigDict(extra="allow")

    text: str = Field(..., min_length=1, max_length=500_000, description="Tender RFP text or specification clauses")
    title: Optional[str] = Field(None, max_length=500, description="Optional tender title or identifier")
    product_description: Optional[str] = Field(None, max_length=2000, description="Target product description")
    sector: Optional[str] = Field(None, description="Procurement sector override")

    @model_validator(mode="before")
    @classmethod
    def _remap_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "text" not in data and "tender_text" in data:
                data["text"] = data["tender_text"]
            if "product_description" not in data and "product_type" in data:
                data["product_description"] = data["product_type"]
        return data


class TenderReportExportRequest(BaseModel):
    """Payload for exporting tender compliance assessment reports to DOCX or PDF."""
    model_config = ConfigDict(extra="allow")

    tender_title: str = Field("Tender Compliance Assessment Report", description="Title of the tender document")
    product_description: str = Field("", description="Procurement item or product description")
    sector: Optional[str] = Field(None, description="Procurement sector")
    compliance_matrix: dict[str, Any] = Field(default_factory=dict, description="Compliance matrix result dictionary")
    clauses: list[dict[str, Any]] = Field(default_factory=list, description="Extracted tender clauses")
    requirements: list[dict[str, Any]] = Field(default_factory=list, description="Extracted requirements")
    detected_standards: list[str] = Field(default_factory=list, description="Detected standard designations")
    warnings: list[str] = Field(default_factory=list, description="Warnings and risk flags")


