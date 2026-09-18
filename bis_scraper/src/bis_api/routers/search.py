"""``/api/v1/search`` -- retrieval only, no LLM.

This is the latency-sensitive endpoint: no generation, no compliance scoring,
just hybrid retrieval. It exists separately from ``/recommend`` because the
frontend needs instant results-as-you-type, and a RAG call (which may wait on a
remote LLM for seconds) is the wrong primitive for that.
"""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, Query

from bis_rag.query_processor import Intent

from ..deps import get_services, require_api_key
from ..models.response import SearchResponseOut
from ..services import AppServices

router = APIRouter(prefix="/api/v1", tags=["search"])


def _run(services: AppServices, query: str, top_k: int, division: Optional[str],
         committee: Optional[str], include_superseded: bool,
         intent: Optional[str]) -> SearchResponseOut:
    started = time.perf_counter()
    search = services.require_search()

    processed = search._processor().process(query)
    # Filters come from the caller, not only from the query text: the frontend
    # has facet dropdowns, and a selected value should not have to be spelled
    # out in the search box to take effect.
    if division:
        processed.divisions = [division]
    if committee:
        processed.committees = [committee]
    if include_superseded:
        processed.current_only = False
    if intent:
        processed.intent = Intent(intent)

    response = search.search(processed, top_k=top_k)
    payload = response.as_dict()
    payload["took_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return SearchResponseOut(**payload)


@router.get("/search", response_model=SearchResponseOut,
            dependencies=[Depends(require_api_key)],
            summary="Retrieval-only search (no LLM)")
async def search_get(
    q: str = Query(..., min_length=1, max_length=1000, description="Search query"),
    limit: int = Query(10, ge=1, le=50),
    domain: Optional[str] = Query(None, description="BIS division filter"),
    committee: Optional[str] = Query(None),
    include_superseded: bool = Query(False),
    intent: Optional[str] = Query(None, description="Override intent detection"),
    services: AppServices = Depends(get_services),
) -> SearchResponseOut:
    return _run(services, q, limit, domain, committee, include_superseded, intent)
