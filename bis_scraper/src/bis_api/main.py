"""FastAPI application for the BIS Standards assistant.

    uvicorn bis_api.main:app --reload --port 8000

    PYTHONPATH=src uvicorn bis_api.main:app --host 0.0.0.0 --port 8000

Boots with or without a dataset. Without one it serves ``/docs`` and
``/api/v1/health`` -- which explains exactly what is missing and how to fix it --
and returns 503 from the data endpoints. See ``services.py`` for why that beats
crash-looping.

Exception handling
------------------
Every error leaves as :class:`~bis_api.models.response.ErrorOut`: ``error``,
``detail``, ``request_id``, ``status_code``. FastAPI's default 422 body is a
nested list that varies by Pydantic version, and the default 500 body is
``Internal Server Error`` with the traceback only in the logs. A client should
be able to show the user something true in both cases.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import Settings, settings_from_env
from .middleware.logging import RequestContextMiddleware
from .middleware.rate_limit import RateLimitMiddleware, RateLimiter
from .routers import compliance as compliance_router
from .routers import demo as demo_router
from .routers import recommend as recommend_router
from .routers import search as search_router
from .routers import standards as standards_router
from .routers import system as system_router
from .services import AppServices, ServiceUnavailable

log = logging.getLogger("bis_api")

__all__ = ["create_app", "app"]

DESCRIPTION = """\
Retrieval-augmented assistant over Indian Standards (BIS / IS codes).

Built on `bis_rag`: a persistent vector store, hybrid BM25 + TF-IDF + dense
retrieval fused with reciprocal rank fusion, and grounded answers whose citations
are verified against what was actually retrieved.

**Answer quality depends on configuration.** `GET /api/v1/health` reports which
of these are active, and it is worth reading before trusting a result:

* **Embedder** -- the default is a hashing embedder, which is *lexical, not
  semantic*. `bis-rag build --embedder st:BAAI/bge-large-en-v1.5` or
  `api:<model>` gives real semantic retrieval.
* **Generator** -- with no `GROQ_API_KEY` / `OPENAI_API_KEY` / `OLLAMA_HOST`,
  answers are extractive: assembled from retrieved passages without a language
  model, and labelled `mode: "extractive"` in every response.
* **QCO data** -- compliance verdicts use the scraped QCO list when present, and
  an unverified built-in seed list otherwise. On the seed tier a "fully
  compliant" verdict is impossible by design.
"""


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Build the application. Safe to call more than once (the tests do)."""
    settings = settings or settings_from_env()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        services = AppServices(settings)
        application.state.services = services
        # `load()` records failures rather than raising, so the app always
        # starts; /health is where the truth is reported.
        services.load()
        if services.degraded:
            log.warning("starting in a degraded state -- see GET /api/v1/health")
        yield

    application = FastAPI(
        title="BIS Standards AI API",
        description=DESCRIPTION,
        version=settings.app_version,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
        contact={"name": "PS 26108 -- BIS Standards AI"},
    )

    # --- middleware -----------------------------------------------------
    # Order matters. Starlette runs `add_middleware` in reverse, so the last one
    # added is the outermost: CORS must be outermost to decorate error
    # responses from every other layer, and request context must wrap the rate
    # limiter so a 429 still carries a request id and a timing header.
    limiter = RateLimiter(limit=settings.rate_limit_requests,
                          window_s=settings.rate_limit_window_s)
    application.state.rate_limiter = limiter

    application.add_middleware(
        RateLimitMiddleware,
        limiter=limiter,
        exempt_paths=("/api/v1/health", "/health", "/", "/docs", "/openapi.json"),
        trust_proxy=settings.trust_proxy_headers,
        enabled=settings.rate_limit_enabled,
    )
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        # "*" by default: the hackathon frontend runs on a different origin and
        # there are no cookies or credentials here, so the usual reason to pin
        # origins does not apply. Set BIS_CORS_ORIGINS before exposing the API
        # to the internet.
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Response-Time-Ms",
                        "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )

    # --- error handling --------------------------------------------------
    def error_body(request: Request, *, error: str, detail: str, code: int) -> dict[str, Any]:
        return {
            "error": error,
            "detail": detail,
            "request_id": getattr(request.state, "request_id", ""),
            "status_code": code,
        }

    @application.exception_handler(ServiceUnavailable)
    async def _unavailable(request: Request, exc: ServiceUnavailable) -> JSONResponse:
        # 503 rather than 500: the request was fine, the server is not ready,
        # and the detail tells the operator how to make it ready.
        log.warning("service unavailable (%s): %s", exc.component, exc.detail)
        return JSONResponse(
            status_code=503,
            content=error_body(request, error="service_unavailable",
                               detail=str(exc), code=503),
        )

    @application.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        problems = []
        for item in exc.errors():
            location = ".".join(str(part) for part in item.get("loc", ()))
            problems.append(f"{location}: {item.get('msg', 'invalid')}")
        return JSONResponse(
            status_code=422,   # numeric: starlette renamed the constant
            content=error_body(request, error="validation_error",
                               detail="; ".join(problems) or "invalid request", code=422),
        )

    @application.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(request, error=_slug(exc.status_code),
                               detail=str(exc.detail), code=exc.status_code),
            headers=getattr(exc, "headers", None),
        )

    @application.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "")
        # Full traceback to the log, nothing but the request id to the client:
        # a traceback in a response body is an information leak, and the id is
        # enough to find the log line.
        log.exception("unhandled exception request_id=%s", request_id)
        return JSONResponse(
            status_code=500,
            content=error_body(
                request, error="internal_error",
                detail=f"an unexpected error occurred; quote request_id {request_id!r} "
                       f"when reporting it",
                code=500),
        )

    # --- routes ----------------------------------------------------------
    application.include_router(system_router.router)
    application.include_router(search_router.router)
    application.include_router(recommend_router.router)
    application.include_router(compliance_router.router)
    application.include_router(standards_router.router)
    application.include_router(demo_router.router)

    @application.get("/health", include_in_schema=False)
    async def health_alias(request: Request) -> JSONResponse:
        """Unversioned alias for probes that expect ``/health``."""
        services: AppServices = request.app.state.services
        return JSONResponse(content=services.health())

    return application


def _slug(code: int) -> str:
    return {
        400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found",
        405: "method_not_allowed", 413: "payload_too_large",
        422: "unprocessable_entity", 429: "rate_limit_exceeded",
        500: "internal_error", 503: "service_unavailable",
    }.get(code, "http_error")


#: ASGI entry point for `uvicorn bis_api.main:app`.
app = create_app()
