"""``/api/v1/compliance`` -- QCO check and printable gap report."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from bis_rag.compliance import render_html

from ..deps import get_services, require_api_key
from ..models.request import ComplianceRequest
from ..models.response import ComplianceResponseOut
from ..services import AppServices

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])


@router.post("/check", response_model=ComplianceResponseOut,
             dependencies=[Depends(require_api_key)],
             summary="Check standards against the QCO mandatory list")
async def check(body: ComplianceRequest,
                services: AppServices = Depends(get_services)) -> ComplianceResponseOut:
    started = time.perf_counter()
    checker = services.require_checker()
    report = checker.analyze(body.product_description, body.standards, sector=body.sector)
    payload = report.as_dict()
    payload["took_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return ComplianceResponseOut(**payload)


def _report_for(services: AppServices, product: str, standards: list[str], sector):
    checker = services.require_checker()
    if not standards:
        # No explicit list: recommend standards for the product, then check
        # those. This is the "am I compliant?" flow, and it is what a user who
        # does not know which standards apply actually needs.
        search = services.require_search()
        response = search.search(product, top_k=8)
        standards = [r.designation for r in response.results if r.designation]
    return checker.analyze(product, standards, sector=sector)


@router.get("/report", response_class=HTMLResponse,
            dependencies=[Depends(require_api_key)],
            summary="Printable HTML gap report")
async def report(
    product: str = Query(..., min_length=1, max_length=500),
    standard: list[str] = Query(default_factory=list,
                                description="Repeat for each standard in use"),
    sector: str | None = Query(None),
    services: AppServices = Depends(get_services),
) -> HTMLResponse:
    try:
        result = _report_for(services, product, list(standard), sector)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500,
                            detail=f"could not build the report: {exc}") from exc
    return HTMLResponse(content=render_html(result),
                        headers={"Content-Disposition":
                                 'inline; filename="bis_compliance_report.html"'})
