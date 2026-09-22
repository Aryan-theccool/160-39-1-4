"""``/api/v1/tender`` -- Multi-Format Tender Ingestion, Requirement Extraction, Compliance Matrix, and Report Export."""

from __future__ import annotations

import datetime
import time
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile

from bis_api.document_reader import read_document

from ..deps import get_services, require_api_key
from ..models.request import TenderAnalyzeTextRequest, TenderReportExportRequest
from ..models.response import (
    TenderAnalysisResponseOut,
    TenderClauseOut,
    TenderComplianceMatrixOut,
    TenderRequirementEvaluationOut,
    TenderRequirementOut,
    TenderStandardAssessmentOut,
)
from ..services import AppServices

router = APIRouter(prefix="/api/v1/tender", tags=["tender"])

MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_PDF = "application/pdf"


@router.post(
    "/analyze/file",
    response_model=TenderAnalysisResponseOut,
    dependencies=[Depends(require_api_key)],
    summary="Upload and analyze tender RFP document (PDF, DOCX, TXT) against BIS standards",
)
async def analyze_tender_file(
    file: UploadFile = File(..., description="Tender RFP document (PDF, DOCX, or TXT)"),
    product_description: Optional[str] = Form(None, description="Target product description (optional)"),
    sector: Optional[str] = Form(None, description="Procurement sector override (optional)"),
    services: AppServices = Depends(get_services),
) -> TenderAnalysisResponseOut:
    """Ingest tender document, extract clauses and technical requirements, and assess BIS compliance."""
    started = time.perf_counter()

    try:
        content_bytes = await file.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read uploaded file stream: {exc}") from exc

    if not content_bytes:
        raise HTTPException(status_code=422, detail="Uploaded tender file is empty.")

    # Ingest document
    read_res = read_document(
        content_bytes,
        filename=file.filename or "uploaded_tender",
        media_type=file.content_type or "",
    )

    if not read_res.ok or read_res.document is None:
        error_msg = read_res.error_message or "Failed to parse document content."
        raise HTTPException(status_code=422, detail=error_msg)

    doc = read_res.document

    from bis_rag.tender_compliance import assess_tender_compliance
    from bis_rag.tender_extractor import extract_tender_requirements

    # Extract clauses and technical requirements
    tender_extracted = extract_tender_requirements(doc)

    # Assess tender compliance against BIS standards and QCOs
    matrix = assess_tender_compliance(
        tender_extracted,
        data=services.data,
        qco=services.qco,
        product_description=product_description,
        sector=sector,
    )

    took_ms = round((time.perf_counter() - started) * 1000, 2)

    return TenderAnalysisResponseOut(
        filename=doc.source.filename,
        media_type=doc.source.media_type,
        source_type=doc.source.source_type,
        character_count=doc.character_count,
        page_count=doc.page_count,
        clauses=[TenderClauseOut(**c.as_dict()) for c in tender_extracted.clauses],
        requirements=[TenderRequirementOut(**r.as_dict()) for r in tender_extracted.requirements],
        detected_standards=tender_extracted.detected_standards,
        compliance_matrix=TenderComplianceMatrixOut(**matrix.as_dict()),
        took_ms=took_ms,
        warnings=tender_extracted.warnings,
    )


@router.post(
    "/analyze/text",
    response_model=TenderAnalysisResponseOut,
    dependencies=[Depends(require_api_key)],
    summary="Analyze tender RFP clauses or specification text directly",
)
async def analyze_tender_text(
    body: TenderAnalyzeTextRequest,
    services: AppServices = Depends(get_services),
) -> TenderAnalysisResponseOut:
    """Analyze raw tender specification text or pasted RFP clauses."""
    started = time.perf_counter()

    text_bytes = body.text.encode("utf-8")
    read_res = read_document(
        text_bytes,
        filename=f"{body.title or 'tender_spec'}.txt",
        media_type="text/plain",
    )

    if not read_res.ok or read_res.document is None:
        raise HTTPException(status_code=422, detail=read_res.error_message or "Failed to read text.")

    doc = read_res.document

    from bis_rag.tender_compliance import assess_tender_compliance
    from bis_rag.tender_extractor import extract_tender_requirements

    tender_extracted = extract_tender_requirements(doc)

    matrix = assess_tender_compliance(
        tender_extracted,
        data=services.data,
        qco=services.qco,
        product_description=body.product_description,
        sector=body.sector,
    )

    took_ms = round((time.perf_counter() - started) * 1000, 2)

    return TenderAnalysisResponseOut(
        filename=doc.source.filename,
        media_type=doc.source.media_type,
        source_type=doc.source.source_type,
        character_count=doc.character_count,
        page_count=doc.page_count,
        clauses=[TenderClauseOut(**c.as_dict()) for c in tender_extracted.clauses],
        requirements=[TenderRequirementOut(**r.as_dict()) for r in tender_extracted.requirements],
        detected_standards=tender_extracted.detected_standards,
        compliance_matrix=TenderComplianceMatrixOut(**matrix.as_dict()),
        took_ms=took_ms,
        warnings=tender_extracted.warnings,
    )


@router.post(
    "/report/docx",
    response_class=Response,
    dependencies=[Depends(require_api_key)],
    summary="Export downloadable Word (.docx) Tender Compliance Assessment Report",
)
async def export_tender_report_docx(body: TenderReportExportRequest) -> Response:
    """Generate and return a professional Microsoft Word document for the tender compliance matrix."""
    from bis_rag.tender_report_builder import build_tender_report_docx
    try:
        buf = build_tender_report_docx(body)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"tender_compliance_report_{timestamp}.docx"
        return Response(
            content=buf.getvalue(),
            media_type=MIME_DOCX,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate tender DOCX report: {exc}") from exc


@router.post(
    "/report/pdf",
    response_class=Response,
    dependencies=[Depends(require_api_key)],
    summary="Export downloadable PDF Tender Compliance Assessment Report",
)
async def export_tender_report_pdf(body: TenderReportExportRequest) -> Response:
    """Generate and return a publication-grade PDF document for the tender compliance matrix."""
    from bis_rag.tender_report_builder import build_tender_report_pdf
    try:
        buf = build_tender_report_pdf(body)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"tender_compliance_report_{timestamp}.pdf"
        return Response(
            content=buf.getvalue(),
            media_type=MIME_PDF,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate tender PDF report: {exc}") from exc
