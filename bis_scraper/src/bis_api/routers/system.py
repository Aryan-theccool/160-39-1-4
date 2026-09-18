"""``/api/v1/health`` and ``/api/v1/feedback``.

Feedback is appended to ``feedback.jsonl`` as one JSON object per line. JSONL
rather than a database because the useful thing to do with this data is read it
with ``pandas``/``grep`` and turn it into a test case -- the ``correct_is`` field
is how a wrong answer becomes a regression test, which is the only reason to
collect feedback at all.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from ..deps import get_services, require_api_key
from ..models.request import FeedbackRequest
from ..models.response import FeedbackOut, HealthOut
from ..services import AppServices

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/health", response_model=HealthOut,
            summary="System status, corpus size and component health")
async def health(services: AppServices = Depends(get_services)) -> HealthOut:
    # Returns 200 even when degraded: the body says what is wrong, and a
    # monitor that only looks at the status code would otherwise treat
    # "dense retrieval is off" the same as "the process is dead".
    return HealthOut(**services.health())


@router.post("/feedback", response_model=FeedbackOut,
             dependencies=[Depends(require_api_key)],
             summary="Record whether an answer was helpful")
async def feedback(body: FeedbackRequest,
                   services: AppServices = Depends(get_services)) -> FeedbackOut:
    path: Path = services.settings.resolved_feedback_path()
    record: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "query": body.query,
        "helpful": body.helpful,
        "correct_is": body.correct_is,
        "comment": body.comment,
        "request_id": body.request_id,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        # A read-only volume must not turn a "thanks" into a 500. The feedback
        # is lost either way; saying so honestly beats pretending it saved.
        log.warning("could not write feedback to %s: %s", path, exc)
        return FeedbackOut(saved=False, path=str(path),
                           message=f"could not persist feedback: {exc}")
    return FeedbackOut(saved=True, path=str(path), message="thank you -- recorded")
