"""Per-IP rate limiting: a fixed-window counter in memory.

Scope, stated plainly
---------------------
This limits **one worker process**. Run ``uvicorn --workers 4`` and the effective
limit is 4x the configured value, because each worker keeps its own counters.
For a hackathon deployment behind a single process that is exactly right; for
anything else, put a shared limiter (nginx, or Redis-backed slowapi) in front.
Saying so here because a rate limiter that silently does not work is worse than
none -- the operator believes they are protected.

``/health`` is exempt: a monitoring probe that gets rate limited reports the
service as down, and an orchestrator will restart-loop on it.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .logging import client_ip

log = logging.getLogger(__name__)

__all__ = ["RateLimitMiddleware", "RateLimiter", "RATE_LIMIT_HEADERS"]


RATE_LIMIT_HEADERS = ("X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After")


@dataclass
class RateLimiter:
    """Sliding-window counter, keyed by client.

    Sliding rather than fixed window: a fixed window lets a client send the full
    quota at the end of one window and again at the start of the next, which is
    a burst of 2x that the limit was supposed to prevent.
    """

    limit: int = 100
    window_s: int = 60
    _hits: dict[str, deque] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def check(self, key: str) -> tuple[bool, int, float]:
        """Record a hit. Returns ``(allowed, remaining, retry_after_s)``."""
        now = time.monotonic()
        cutoff = now - self.window_s
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] < cutoff:
                hits.popleft()

            if len(hits) >= self.limit:
                retry_after = max(0.0, self.window_s - (now - hits[0]))
                return False, 0, retry_after

            hits.append(now)
            remaining = self.limit - len(hits)

            # Opportunistic cleanup: without it the dict grows one entry per
            # distinct IP forever, which is a slow memory leak on a public
            # endpoint.
            if len(self._hits) > 4096:
                self._prune(cutoff)
            return True, remaining, 0.0

    def _prune(self, cutoff: float) -> None:
        """Drop clients whose window has fully expired. Caller holds the lock."""
        stale = [key for key, hits in self._hits.items()
                 if not hits or hits[-1] < cutoff]
        for key in stale:
            self._hits.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, limiter: RateLimiter,
                 exempt_paths: Iterable[str] = ("/api/v1/health", "/health"),
                 trust_proxy: bool = False, enabled: bool = True):
        super().__init__(app)
        self.limiter = limiter
        self.exempt = set(exempt_paths)
        self.trust_proxy = trust_proxy
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next):
        if not self.enabled or request.url.path in self.exempt:
            return await call_next(request)

        key = client_ip(request, trust_proxy=self.trust_proxy)
        allowed, remaining, retry_after = self.limiter.check(key)

        if not allowed:
            request_id = getattr(request.state, "request_id", "")
            log.warning("rate limited %s on %s", key, request.url.path)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "detail": (f"{self.limiter.limit} requests per "
                               f"{self.limiter.window_s}s exceeded. Retry in "
                               f"{retry_after:.0f}s."),
                    "request_id": request_id,
                    "status_code": 429,
                },
                headers={
                    "X-RateLimit-Limit": str(self.limiter.limit),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(int(retry_after) + 1),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.limiter.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
