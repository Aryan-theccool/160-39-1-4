"""``/api/v1/report`` -- Professional Downloadable Procurement Report Export (DOCX and PDF)."""

from __future__ import annotations

import datetime
from fastapi import APIRouter, Depends, HTTPException, Response

from bis_rag.report_builder import build_report_docx, build_report_pdf

from ..deps import require_api_key
from ..models.request import ReportExportRequest

router = APIRouter(prefix="/api/v1/report", tags=["report"])

MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_PDF = "application/pdf"


@router.post("/docx", response_class=Response,
             dependencies=[Depends(require_api_key)],
             summary="Generate and download a professional Word (.docx) procurement report")
async def export_docx(body: ReportExportRequest) -> Response:
    """Generate a Microsoft Word (.docx) document from structured recommendation report data."""
    try:
        buf = build_report_docx(body)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"bis_standards_report_{timestamp}.docx"
        return Response(
            content=buf.getvalue(),
            media_type=MIME_DOCX,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Access-Control-Expose-Headers": "Content-Disposition",
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"could not generate DOCX report: {exc}") from exc


@router.post("/pdf", response_class=Response,
             dependencies=[Depends(require_api_key)],
             summary="Generate and download a professional PDF procurement report")
async def export_pdf(body: ReportExportRequest) -> Response:
    """Generate a valid PDF document from structured recommendation report data."""
    try:
        buf = build_report_pdf(body)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"bis_standards_report_{timestamp}.pdf"
        return Response(
            content=buf.getvalue(),
            media_type=MIME_PDF,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Access-Control-Expose-Headers": "Content-Disposition",
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"could not generate PDF report: {exc}") from exc
