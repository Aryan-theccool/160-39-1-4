"""Settings for the BIS API, read from the environment.

Deliberately a dataclass rather than ``pydantic-settings``: add one dependency
and it is one more thing that can fail to install in a constrained environment,
for a dozen fields. Everything here has a working default, so
``create_app()`` with no environment at all still boots (and reports what it
could not load, rather than pretending to be healthy).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

__all__ = ["Settings", "settings_from_env"]


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class Settings:
    """Every knob the service has, with the environment variable that sets it."""

    # -- data / retrieval ------------------------------------------------
    #: bis_data directory. ``None`` -> BisData's own default ($BIS_DATA_DIR or
    #: bis_scraper/bis_data).
    data_dir: Optional[Path] = None
    #: Vector store directory. ``None`` -> ``<data_dir>/vector_store``.
    store_dir: Optional[Path] = None
    embedder: str = "hash"
    backend: str = "auto"
    reranker: str = "auto"
    #: Build the BM25 indices during startup instead of on first request.
    #: Default on: the first ``/search`` would otherwise take seconds, and the
    #: endpoint promises a fast path.
    warm_indexes: bool = True

    # -- generation ------------------------------------------------------
    #: ``auto`` | ``groq`` | ``openai`` | ``ollama`` | ``extractive``
    llm: Optional[str] = None
    generator_timeout_s: float = 120.0

    # -- HTTP ------------------------------------------------------------
    #: Optional shared secret. When set, all ``/api/v1`` routes except
    #: ``/health`` require a matching ``X-API-Key`` header.
    api_key: Optional[str] = None
    #: CORS. Defaults to ``*`` because this is a hackathon deployment and the
    #: frontend runs on a different origin; see the note in ``main.py``.
    cors_origins: tuple[str, ...] = ("*",)
    #: Trust ``X-Forwarded-For`` when rate limiting. Only enable behind a proxy
    #: you control -- a client can otherwise spoof the header and get a fresh
    #: rate-limit bucket per request.
    trust_proxy_headers: bool = False

    # -- rate limiting ---------------------------------------------------
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100
    rate_limit_window_s: int = 60

    # -- limits ----------------------------------------------------------
    max_pdf_bytes: int = 10 * 1024 * 1024
    #: Characters of extracted PDF text handed to the retriever. A whole spec
    #: sheet as a query buries its own signal.
    max_pdf_query_chars: int = 4000
    max_query_chars: int = 1000

    # -- persistence -----------------------------------------------------
    feedback_path: Optional[Path] = None

    # -- misc ------------------------------------------------------------
    docs_enabled: bool = True
    app_version: str = "0.1.0"

    #: Where things came from, for ``/health``.
    notes: list[str] = field(default_factory=list)

    def resolved_feedback_path(self) -> Path:
        if self.feedback_path:
            return Path(self.feedback_path)
        base = Path(self.data_dir) if self.data_dir else Path.cwd()
        return base / "feedback.jsonl"

    def as_dict(self) -> dict:
        return {
            "data_dir": str(self.data_dir) if self.data_dir else None,
            "store_dir": str(self.store_dir) if self.store_dir else None,
            "embedder": self.embedder,
            "backend": self.backend,
            "reranker": self.reranker,
            "llm": self.llm or "auto",
            "warm_indexes": self.warm_indexes,
            "api_key_required": bool(self.api_key),
            "cors_origins": list(self.cors_origins),
            "rate_limit": (f"{self.rate_limit_requests}/{self.rate_limit_window_s}s"
                           if self.rate_limit_enabled else "disabled"),
            "max_pdf_bytes": self.max_pdf_bytes,
            "feedback_path": str(self.resolved_feedback_path()),
        }


def settings_from_env() -> Settings:
    origins = os.environ.get("BIS_CORS_ORIGINS", "*")
    data_dir = os.environ.get("BIS_DATA_DIR")
    store_dir = os.environ.get("BIS_STORE_DIR")
    feedback = os.environ.get("BIS_FEEDBACK_PATH")
    embedder = os.environ.get("BIS_RAG_EMBEDDER", "hash")

    return Settings(
        data_dir=Path(data_dir).expanduser() if data_dir else None,
        store_dir=Path(store_dir).expanduser() if store_dir else None,
        embedder=embedder,
        backend=os.environ.get("BIS_BACKEND", "auto"),
        reranker=os.environ.get("BIS_RERANKER", "auto"),
        warm_indexes=_flag("BIS_WARM_INDEXES", True),
        llm=os.environ.get("BIS_RAG_LLM"),
        api_key=os.environ.get("BIS_API_KEY") or None,
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()) or ("*",),
        trust_proxy_headers=_flag("BIS_TRUST_PROXY_HEADERS", False),
        rate_limit_enabled=_flag("BIS_RATE_LIMIT", True),
        rate_limit_requests=_int("BIS_RATE_LIMIT_REQUESTS", 100),
        rate_limit_window_s=_int("BIS_RATE_LIMIT_WINDOW", 60),
        max_pdf_bytes=_int("BIS_MAX_PDF_BYTES", 10 * 1024 * 1024),
        feedback_path=Path(feedback).expanduser() if feedback else None,
        docs_enabled=_flag("BIS_DOCS", True),
    )
