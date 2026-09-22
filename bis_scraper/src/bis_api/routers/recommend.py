"""``/api/v1/recommend`` and ``/api/v1/recommend/pdf``.

The PDF endpoint is the one that needs explaining. Extracting text and using the
whole document as a query performs *worse* than a short query, so the flow is:

1. extract text (and report which extractor ran, and whether it found anything);
2. pull out every IS designation the document mentions -- those are exact hits
   and usually the point of the upload;
3. build a query from the designations plus the head of the document;
4. run the normal RAG pipeline on that.

Refusing an upload with no text layer is deliberate. A scanned PDF returns "",
and searching on "" would retrieve the entire corpus and present it as an
answer. A 422 saying "this looks like a scan" is the correct outcome.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from bis_pipeline import iscode

from ..deps import get_services, require_api_key
from ..models.request import RecommendRequest
from ..models.response import RecommendResponseOut
from ..pdf_text import build_query, extract_text
from ..services import AppServices

def human_size(num_bytes: int) -> str:
    """Format a byte count the way a person would write it.

    ``f"{n / 1e6:.0f} MB"`` renders a 200-byte limit as "0 MB", which tells the
    user nothing -- and the limit is configurable, so small values really occur.
    """
    if num_bytes < 1024:
        return f"{num_bytes} bytes"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} kB"
    return f"{num_bytes / (1024 * 1024):.1f} MB"


router = APIRouter(prefix="/api/v1", tags=["recommend"])


def _payload(answer, *, started: float, include_passages: bool) -> dict:
    payload = answer.as_dict(include_passages=include_passages)
    payload["took_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return payload


@router.post("/recommend", response_model=RecommendResponseOut,
             dependencies=[Depends(require_api_key)],
             summary="Grounded answer with citations")
async def recommend(body: RecommendRequest,
                    services: AppServices = Depends(get_services)) -> RecommendResponseOut:
    started = time.perf_counter()
    pipeline = services.require_pipeline()
    answer = pipeline.answer(body.query, top_k=body.top_k,
                            include_passages=body.include_passages,
                            mode="recommend")
    return RecommendResponseOut(**_payload(answer, started=started,
                                           include_passages=body.include_passages))


@router.post("/recommend/pdf", response_model=RecommendResponseOut,
             dependencies=[Depends(require_api_key)],
             summary="Grounded answer from an uploaded PDF")
async def recommend_pdf(
    file: UploadFile = File(..., description="PDF specification sheet or drawing"),
    top_k: int = 6,
    services: AppServices = Depends(get_services),
) -> RecommendResponseOut:
    started = time.perf_counter()
    settings = services.settings
    pipeline = services.require_pipeline()

    data = await file.read()
    if len(data) > settings.max_pdf_bytes:
        raise HTTPException(
            status_code=413,   # numeric: starlette renamed the constant
            detail=(f"PDF is {human_size(len(data))}; the limit is "
                    f"{human_size(settings.max_pdf_bytes)}. Raise it with "
                    f"BIS_MAX_PDF_BYTES, or send the text of the document instead."),
        )

    extraction = extract_text(data, max_chars=settings.max_pdf_query_chars)
    if not extraction.ok:
        # 422, not 400: the upload was well-formed, its *content* is unusable.
        raise HTTPException(
            status_code=422,   # numeric: starlette renamed the constant
            detail=(f"could not read text from {file.filename or 'the PDF'}: "
                    f"{extraction.reason}"),
        )

    # Designations from the document are exact constraints, so they lead the query.
    designations: list[str] = []
    for parsed in iscode.find_all(extraction.text):
        text = parsed.format()
        if text not in designations:
            designations.append(text)

    query = build_query(extraction.text, max_chars=settings.max_pdf_query_chars)
    if designations:
        query = f"{' '.join(designations)} {query}"

    answer = pipeline.answer(query, top_k=top_k, mode="recommend")
    payload = _payload(answer, started=started, include_passages=False)
    payload["source_document"] = extraction.as_dict()
    payload["detected_designations"] = designations
    payload["question"] = f"[PDF: {file.filename or 'upload'}] {answer.question[:400]}"
    return RecommendResponseOut(**payload)
