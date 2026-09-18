"""Application state: the engine objects, loaded once and shared.

Two rules this module exists to enforce
---------------------------------------
**1. A missing dataset must not stop the service from starting.** The engine
objects are expensive (BM25 indices over 9,043 chunks), so they are built at
startup and shared. But if ``bis_data`` is absent -- a fresh clone, a container
that mounted the wrong volume -- the right behaviour is to boot, report
``degraded`` on ``/health`` with the exact command that fixes it, and return
503 on the endpoints that need data. Crash-looping on startup is the alternative,
and it turns a five-second config fix into a mystery.

**2. Startup failures are recorded, not swallowed.** Every component carries its
own ``error`` string from :meth:`AppServices.describe`, and ``/health`` surfaces
them. An endpoint that quietly fell back to BM25-only because the vector store
was built with a different embedder is a correctness problem, and it has to be
visible without reading the logs.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from bis_rag.compliance import ComplianceChecker, QCODatabase
from bis_rag.data import BisData
from bis_rag.hybrid import HybridSearch, RetrievalConfig
from bis_rag.rag import RAGPipeline
from bis_rag.schema import SchemaError

from .config import Settings

log = logging.getLogger(__name__)

__all__ = ["AppServices", "ComponentStatus", "ServiceUnavailable"]


class ServiceUnavailable(RuntimeError):
    """Raised when an endpoint needs a component that failed to load.

    Carries the fix instructions, because "503 Service Unavailable" on its own
    tells a developer nothing about which file is missing.
    """

    def __init__(self, component: str, detail: str):
        super().__init__(f"{component} is unavailable: {detail}")
        self.component = component
        self.detail = detail


@dataclass
class ComponentStatus:
    name: str
    ok: bool = False
    detail: str = ""
    error: str = ""
    load_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "detail": self.detail,
            "error": self.error,
            "load_ms": round(self.load_ms, 2),
        }


class AppServices:
    """Holds the loaded engine and the status of every component."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.started_at = time.time()
        self.components: dict[str, ComponentStatus] = {}

        self.data: Optional[BisData] = None
        self.search: Optional[HybridSearch] = None
        self.pipeline: Optional[RAGPipeline] = None
        self.checker: Optional[ComplianceChecker] = None
        self.qco: Optional[QCODatabase] = None

        self.data_issues: list[str] = []
        self.startup_ms: float = 0.0

    # ------------------------------------------------------------------
    def load(self) -> None:
        """Load everything, recording failures instead of raising."""
        started = time.perf_counter()

        self._component("data", self._load_data)
        if self.data is not None:
            self._component("retrieval", self._load_retrieval)
            self._component("generation", self._load_generation)
            self._component("compliance", self._load_compliance)

        self.startup_ms = (time.perf_counter() - started) * 1000
        log.info("startup complete in %.0fms: %s", self.startup_ms,
                 ", ".join(f"{k}={'ok' if v.ok else 'FAILED'}"
                           for k, v in self.components.items()))

    def _component(self, name: str, loader) -> None:
        started = time.perf_counter()
        status = ComponentStatus(name=name)
        try:
            status.detail = loader() or ""
            status.ok = True
        except ServiceUnavailable as exc:
            status.error = exc.detail
        except SchemaError as exc:
            status.error = str(exc)
        except Exception as exc:  # pragma: no cover - defensive
            status.error = f"{type(exc).__name__}: {exc}"
            log.exception("failed to load %s", name)
        status.load_ms = (time.perf_counter() - started) * 1000
        self.components[name] = status
        if not status.ok:
            log.warning("component %s unavailable: %s", name, status.error)

    # ------------------------------------------------------------------
    def _load_data(self) -> str:
        # NB: assign to self only after every check passes. Assigning early and
        # then raising leaves a half-built object behind, and the invariant the
        # require_*() accessors rely on -- "not None means usable" -- is then
        # false. That bug made /health 500 on an empty data directory instead of
        # reporting it, which is exactly the case this class exists to handle.
        data = BisData(self.settings.data_dir)

        missing = data.missing()
        self.data_issues = [
            f"{name}: {data.path(name)}"
            for name in missing
            if name in ("chunks", "knowledge_base", "search_corpus", "merged_standards")
        ]
        if not data.exists("chunks") and not any(
                data.exists(k) for k in ("knowledge_base", "search_corpus", "merged_standards")):
            raise ServiceUnavailable(
                "data",
                f"no usable dataset under {data.root}. Expected rag/chunked_documents.jsonl "
                f"and rag/knowledge_base.json.\n"
                f"  bis_data/ is gitignored, so a fresh clone does not include it.\n"
                f"  generate it:  cd bis_scraper && python create_rag_dataset.py\n"
                f"  or point at it:  export BIS_DATA_DIR=/path/to/bis_data",
            )

        summary = data.summary()
        self.data = data
        return (f"{data.root}: {summary['standards']} standards, "
                f"{summary['chunks']} chunks, {summary['divisions']} divisions")

    def _load_retrieval(self) -> str:
        config = RetrievalConfig(top_k=10)
        search = HybridSearch(
            self.data,
            store_dir=str(self.settings.store_dir) if self.settings.store_dir else None,
            embedder=self.settings.embedder,
            config=config,
            reranker=self.settings.reranker,
            backend=self.settings.backend,
        )
        if self.settings.warm_indexes:
            # Building these on first request would blow the /search latency
            # promise on the one request a reviewer is most likely to try.
            search.chunk_index()
            search.standard_index()
        self.search = search   # assigned only once the indices are warm

        dense = search._store("chunks") is not None
        reranker = getattr(search.reranker, "name", "none")
        detail = (f"BM25 over {len(search.chunk_index())} chunks; "
                  f"dense={'on' if dense else 'OFF'}; reranker={reranker}")
        if not dense:
            # Not fatal, but the reason belongs in /health rather than only in
            # the logs -- dense retrieval being off changes answer quality.
            detail += " (run `bis-rag build` to enable dense retrieval)"
        return detail

    def _load_generation(self) -> str:
        pipeline = RAGPipeline(self.data, self.search, generator=self.settings.llm)
        self.pipeline = pipeline
        generator = pipeline.generator
        if getattr(generator, "is_llm", False):
            return f"LLM: {generator.name} ({getattr(generator, 'model', '?')})"
        return ("no LLM configured -- answers will be extractive. Set GROQ_API_KEY, "
                "OPENAI_API_KEY or OLLAMA_HOST for generated prose")

    def _load_compliance(self) -> str:
        self.qco = QCODatabase(self.data)
        self.checker = ComplianceChecker(self.data, self.qco)
        detail = self.qco.describe()
        if not self.qco.verified:
            detail += (" -- run `python -m bis_pipeline mandatory` to replace the seed list "
                       "with BIS's published QCO list")
        return detail

    # ------------------------------------------------------------------
    # accessors that fail loudly with a usable message
    # ------------------------------------------------------------------
    def require_data(self) -> BisData:
        if self.data is None:
            raise ServiceUnavailable("data", self._error("data"))
        return self.data

    def require_search(self) -> HybridSearch:
        if self.search is None:
            self.require_data()
            raise ServiceUnavailable("retrieval", self._error("retrieval"))
        return self.search

    def require_pipeline(self) -> RAGPipeline:
        if self.pipeline is None:
            self.require_data()
            raise ServiceUnavailable("generation", self._error("generation"))
        return self.pipeline

    def require_checker(self) -> ComplianceChecker:
        if self.checker is None:
            self.require_data()
            raise ServiceUnavailable("compliance", self._error("compliance"))
        return self.checker

    def _error(self, name: str) -> str:
        status = self.components.get(name)
        return status.error if status and status.error else "not loaded"

    # ------------------------------------------------------------------
    @property
    def degraded(self) -> bool:
        return any(not status.ok for status in self.components.values())

    def health(self) -> dict[str, Any]:
        corpus: dict[str, Any] = {}
        if self.data is not None:
            try:
                summary = self.data.summary()
                corpus = {
                    "standards": summary["standards"],
                    "chunks": summary["chunks"],
                    "current": summary["current"],
                    "superseded": summary["superseded"],
                    "compulsory": summary["compulsory"],
                    "divisions": summary["divisions"],
                    "year_range": list(summary["year_range"]),
                    "data_dir": str(self.data.root),
                }
            except Exception as exc:  # pragma: no cover - defensive
                corpus = {"error": str(exc)}

        retrieval: dict[str, Any] = {}
        if self.search is not None:
            # Defensive on purpose: /health is the endpoint you call to find out
            # what is broken, so it must not be the endpoint that breaks.
            try:
                store = self.search._store("chunks")
                meta = store.get_meta() if store else {}
                retrieval = {
                    "bm25_chunks": len(self.search.chunk_index()),
                    "bm25_standards": len(self.search.standard_index()),
                    "dense_enabled": store is not None,
                    "vectors": meta.get("count") if store else 0,
                    "embedder": self.settings.embedder,
                    "backends_available": _backends(),
                    "reranker": getattr(self.search.reranker, "name", "none"),
                }
            except Exception as exc:
                retrieval = {"error": str(exc)}

        qco: dict[str, Any] = {}
        if self.qco is not None:
            qco = {
                "entries": len(self.qco),
                "source": self.qco.source,
                "verified": self.qco.verified,
            }

        llm: dict[str, Any] = {}
        if self.pipeline is not None:
            generator = self.pipeline.generator
            llm = {
                "provider": getattr(generator, "name", "unknown"),
                "is_llm": bool(getattr(generator, "is_llm", False)),
            }

        issues = [f"{name}: {status.error}" for name, status in self.components.items()
                  if not status.ok]
        if retrieval.get("dense_enabled") is False:
            issues.append("dense retrieval inactive (no vector store) -- BM25 + TF-IDF only")
        if self.qco is not None and not self.qco.verified:
            issues.append("QCO list is the unverified seed set")

        if not corpus:
            status = "unavailable"
        elif issues:
            status = "degraded"
        else:
            status = "ok"

        return {
            "status": status,
            "version": self.settings.app_version,
            "detail": status,
            "corpus": corpus,
            "retrieval": retrieval,
            "qco": qco,
            "llm": llm,
            "startup_ms": round(self.startup_ms, 2),
            "uptime_s": round(time.time() - self.started_at, 2),
            "issues": issues,
        }

    def describe(self) -> dict[str, Any]:
        return {
            "settings": self.settings.as_dict(),
            "components": {name: status.as_dict()
                           for name, status in self.components.items()},
        }


def _backends() -> list[str]:
    from bis_rag.vectorstore import available_backends

    return available_backends()
