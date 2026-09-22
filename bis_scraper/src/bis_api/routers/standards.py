"""``/api/v1/standards`` -- browse and look up individual standards."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import get_services, require_api_key
from ..models.response import StandardDetailOut
from ..services import AppServices

router = APIRouter(prefix="/api/v1/standards", tags=["standards"])


@router.get("", dependencies=[Depends(require_api_key)],
            summary="List standards, optionally filtered")
async def list_standards(
    division: Optional[str] = Query(None),
    committee: Optional[str] = Query(None),
    current_only: bool = Query(True),
    compulsory_only: bool = Query(False),
    year_from: Optional[int] = Query(None, ge=1900, le=2100),
    year_to: Optional[int] = Query(None, ge=1900, le=2100),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    services: AppServices = Depends(get_services),
) -> dict[str, Any]:
    data = services.require_data()
    rows = data.standards()

    if division:
        wanted = division.strip().lower()
        rows = [r for r in rows if r.division.strip().lower() == wanted]
    if committee:
        wanted = committee.strip().lower()
        rows = [r for r in rows if r.committee.strip().lower() == wanted]
    if current_only:
        rows = [r for r in rows if r.is_current]
    if compulsory_only:
        rows = [r for r in rows if r.is_compulsory]
    if year_from:
        rows = [r for r in rows if r.year and r.year >= year_from]
    if year_to:
        rows = [r for r in rows if r.year and r.year <= year_to]

    total = len(rows)
    page = rows[offset:offset + limit]
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "returned": len(page),
        "facets": {
            "divisions": data.divisions(),
            "committees": data.committees(),
        },
        "standards": [
            {
                "designation": r.designation,
                "canonical": r.canonical,
                "title": r.title,
                "division": r.division,
                "committee": r.committee,
                "year": r.year,
                "is_current": r.is_current,
                "superseded_by": r.superseded_by,
                "is_compulsory": r.is_compulsory,
                "archive_url": r.archive_url,
            }
            for r in page
        ],
    }


@router.get("/{is_number}", response_model=StandardDetailOut,
            dependencies=[Depends(require_api_key)],
            summary="Full detail for one standard, including supersession")
async def get_standard(is_number: str,
                       services: AppServices = Depends(get_services)) -> StandardDetailOut:
    data = services.require_data()
    standard = data.resolve_designation(is_number)

    if standard is None:
        # Try the year-less form: "IS 456" should find IS 456:2000.
        from bis_rag.compliance import _yearless_key

        key = _yearless_key(is_number)
        for candidate in data.standards():
            if _yearless_key(candidate.designation) == key:
                standard = candidate
                break

    if standard is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(f"{is_number!r} is not in this dataset. It holds 197 of archive.org's "
                    f"~22,025 CC0 Indian Standards, so the standard may exist but not be "
                    f"indexed here."),
        )

    payload = standard.as_metadata()
    payload["keywords"] = list(standard.keywords)
    payload["status"] = standard.status
    payload["supersession"] = None

    info = data.supersession(standard.canonical)
    if info is not None:
        payload["supersession"] = info.as_dict()

    # Point at the current edition when the requested one is superseded --
    # returning a withdrawn standard without its replacement is the failure this
    # whole layer exists to prevent.
    if not standard.is_current:
        replacement = data.resolve_designation(standard.superseded_by) if standard.superseded_by else None
        payload["superseded_by"] = replacement.designation if replacement else standard.superseded_by

    related = [
        {
            "designation": r.designation,
            "title": r.title,
            "year": r.year,
            "is_current": r.is_current,
        }
        for r in data.standards()
        if r.division and r.division == standard.division
        and r.canonical != standard.canonical
    ][:10]
    payload["related"] = related
    return StandardDetailOut(**payload)
