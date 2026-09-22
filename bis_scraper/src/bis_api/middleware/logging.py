"""Request logging, request ids, and response timing.

The ``X-Request-ID`` header is the useful part. A standards answer is something
users argue with, and "feedback: this was wrong" is only actionable if the
report can be joined to the exact request that produced it -- which is why
``/api/v1/feedback`` accepts a ``request_id``. A client-supplied id is honoured
(correlation across services), but validated: an id echoed into a log line
unchecked is log injection.
"""

from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

__all__ = ["RequestContextMiddleware", "REQUEST_ID_HEADER", "TIMING_HEADER"]

REQUEST_ID_HEADER = "X-Request-ID"
TIMING_HEADER = "X-Response-Time-Ms"

_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")

log = logging.getLogger("bis_api.access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request id, time the request, log one line per request."""

    def __init__(self, app, *, log_requests: bool = True):
        super().__init__(app)
        self.log_requests = log_requests

    async def dispatch(self, request: Request, call_next):
        raw = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = raw if _SAFE_ID.match(raw or "") else uuid.uuid4().hex[:16]
        request.state.request_id = request_id

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Let the exception handlers produce the response; still record the
            # timing and the id so the error body and the log agree.
            elapsed_ms = (time.perf_counter() - started) * 1000
            log.exception("unhandled error request_id=%s %s %s (%.1fms)",
                          request_id, request.method, request.url.path, elapsed_ms)
            raise

        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[TIMING_HEADER] = f"{elapsed_ms:.1f}"
        # Timing a response the client cannot see is pointless when the point is
        # verifying the "fast path" claim, so expose it to browser JS too.
        response.headers.setdefault("Access-Control-Expose-Headers",
                                    f"{REQUEST_ID_HEADER}, {TIMING_HEADER}")

        if self.log_requests:
            log.info("%s %s -> %d (%.1fms) request_id=%s",
                     request.method, request.url.path, response.status_code,
                     elapsed_ms, request_id)
        return response


def client_ip(request: Request, *, trust_proxy: bool = False) -> str:
    """Best-effort client address for rate limiting.

    ``X-Forwarded-For`` is only consulted when explicitly trusted. Any client
    can send that header, and honouring it unconditionally would give every
    request its own rate-limit bucket -- an accidental bypass, not a feature.
    """
    if trust_proxy:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
