"""Read ``bis_data/`` as one consistent object.

Layout this expects (all paths relative to ``--data-dir``)::

    bis_data/
    ├── rag/
    │   ├── chunked_documents.jsonl     9,043 chunks      -> chunk collection
    │   ├── knowledge_base.json         197 standards     -> standards collection
    │   └── search_corpus.jsonl         197 w/ snippets   -> summary text + BM25
    ├── semantic/
    │   ├── category_hierarchy.json     divisions/committees -> query routing
    │   ├── cross_references.json       17 supersession chains -> compliance
    │   ├── domain_ontology.json        domains + concepts -> query expansion
    │   ├── temporal_index.json         year/decade stats
    │   └── search_facets.json          filter values for the UI
    ├── merged/merged_standards.json    24-field records, QCO flags
    └── index/search_index.json         the existing TF-IDF index

Nothing here is required to *be* present: :meth:`BisData.availability` reports
what is and is not on disk, and every accessor that needs a missing file fails
with the command that would create it. The point is that a half-populated data
directory produces "run `bis-pipeline merge` next", not a ``KeyError`` from
four frames deep inside a loader.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from bis_pipeline import iscode
from bis_pipeline.index import SearchIndex

from .schema import (
    Chunk,
    FieldCoverage,
    SchemaError,
    Standard,
    dedupe_standards,
    load_chunks,
    load_json,
    load_jsonl,
)

log = logging.getLogger(__name__)

__all__ = ["BisData", "Supersession", "FileStatus", "default_data_dir"]


#: key -> path relative to the data root. Order matters for the build: the
#: first two feed the vector collections.
FILES: dict[str, str] = {
    "chunks": "rag/chunked_documents.jsonl",
    "knowledge_base": "rag/knowledge_base.json",
    "search_corpus": "rag/search_corpus.jsonl",
    "category_hierarchy": "semantic/category_hierarchy.json",
    "cross_references": "semantic/cross_references.json",
    "domain_ontology": "semantic/domain_ontology.json",
    "temporal_index": "semantic/temporal_index.json",
    "search_facets": "semantic/search_facets.json",
    "merged_standards": "merged/merged_standards.json",
    "search_index": "index/search_index.json",
    # QCO compulsory-certification list. Tier 1 source of truth for compliance
    # checks; absent when `bis-pipeline mandatory` has not been run.
    "mandatory": "mandatory/mandatory.json",
}

#: Files without which the vector store cannot be built at all.
REQUIRED_FOR_BUILD = ("chunks",)

#: Command that regenerates each file, for error messages.
REGEN_HINTS: dict[str, str] = {
    "chunks": "python create_rag_dataset.py      (in bis_scraper/)",
    "knowledge_base": "python create_rag_dataset.py",
    "search_corpus": "python create_rag_dataset.py",
    "search_index": "python -m bis_pipeline index",
    "merged_standards": "python -m bis_pipeline merge",
    "category_hierarchy": "python create_semantic_index.py",
    "cross_references": "python create_semantic_index.py",
    "domain_ontology": "python create_semantic_index.py",
    "temporal_index": "python create_semantic_index.py",
    "search_facets": "python create_semantic_index.py",
    "mandatory": "python -m bis_pipeline mandatory",
}


def default_data_dir() -> Path:
    """``$BIS_DATA_DIR``, else ``bis_scraper/bis_data`` next to the package."""
    env = os.environ.get("BIS_DATA_DIR")
    if env:
        return Path(env).expanduser()
    # .../landing-page/bis_scraper/src/bis_rag/data.py -> .../landing-page/bis_scraper/bis_data
    return Path(__file__).resolve().parents[2] / "bis_data"


@dataclass(frozen=True)
class FileStatus:
    key: str
    path: Path
    exists: bool
    size: int = 0
    detail: str = ""

    def __str__(self) -> str:
        if not self.exists:
            return f"MISSING  {self.key:<18} {self.path}"
        size = self.size
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                break
            size /= 1024
        return f"ok       {self.key:<18} {self.path}  ({size:.1f} {unit}) {self.detail}"


@dataclass(frozen=True)
class Supersession:
    """One link in a supersession chain.

    ``replacement_designation`` is what a human wants to read; ``replacement_canonical``
    is what the rest of the system can join on. Both are populated when the
    replacement is present in the dataset -- and the replacement often is not,
    because ``bis_data`` holds 197 of archive.org's 22,025 standards. In that
    case we still report the designation so the user can see that a newer
    edition exists and go find it.

    Why this is not just a dict lookup: ``cross_references.json`` maps
    ``old_canonical -> "IS 302 (Part 1):2009"``, a *designation string*, not a
    canonical id (see ``merger.resolve_editions``, which sets
    ``superseded_by = newest.designation``). Treating that string as an id
    yields a silent miss on every lookup.
    """

    canonical: str
    designation: str
    replacement_designation: str
    replacement_canonical: str = ""
    replacement_year: Optional[int] = None
    in_dataset: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonical": self.canonical,
            "designation": self.designation,
            "replacement_designation": self.replacement_designation,
            "replacement_canonical": self.replacement_canonical,
            "replacement_year": self.replacement_year,
            "in_dataset": self.in_dataset,
        }


class BisData:
    """Lazy, cached access to every file listed in :data:`FILES`."""

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root).expanduser() if root else default_data_dir()
        self._cache: dict[str, Any] = {}
        self._coverage: dict[str, list[FieldCoverage]] = {}

    # ------------------------------------------------------------------
    # paths and availability
    # ------------------------------------------------------------------
    def path(self, key: str) -> Path:
        try:
            return self.root / FILES[key]
        except KeyError:
            raise SchemaError(f"unknown data file key {key!r}") from None

    def exists(self, key: str) -> bool:
        return self.path(key).exists()

    def availability(self) -> list[FileStatus]:
        """Report every expected file. Used by ``bis-rag doctor``."""
        out: list[FileStatus] = []
        for key in FILES:
            path = self.path(key)
            if path.exists():
                out.append(FileStatus(key, path, True, path.stat().st_size))
            else:
                out.append(FileStatus(key, path, False,
                                      detail=f"regenerate: {REGEN_HINTS.get(key, '?')}"))
        return out

    def missing(self) -> list[str]:
        return [s.key for s in self.availability() if not s.exists]

    def require(self, key: str) -> Path:
        path = self.path(key)
        if not path.exists():
            hint = REGEN_HINTS.get(key, "")
            raise SchemaError(
                f"{path} not found.\n"
                f"  bis_data/ is gitignored by bis_scraper/.gitignore, so a fresh "
                f"clone does not have it -- it must be generated or copied in.\n"
                f"  regenerate with:  {hint}\n"
                f"  or point elsewhere:  export BIS_DATA_DIR=/path/to/bis_data\n"
                f"  present files:  {', '.join(k for k in FILES if self.exists(k)) or 'none'}"
            )
        return path

    # ------------------------------------------------------------------
    # chunks
    # ------------------------------------------------------------------
    def chunks(self) -> list[Chunk]:
        if "chunks" not in self._cache:
            path = self.require("chunks")
            chunks, report = load_chunks(path)
            self._cache["chunks"] = chunks
            self._coverage["chunks"] = report
            log.info("loaded %d chunks from %s", len(chunks), path)
        return self._cache["chunks"]

    def chunk_coverage(self) -> list[FieldCoverage]:
        self.chunks()
        return self._coverage.get("chunks", [])

    # ------------------------------------------------------------------
    # standards: three overlapping files, merged into one row per IS code
    # ------------------------------------------------------------------
    def standards(self) -> list[Standard]:
        """One :class:`Standard` per canonical id, from every file that has them.

        ``knowledge_base.json`` supplies keywords, ``search_corpus.jsonl``
        supplies summary text, ``merged_standards.json`` supplies the QCO flag
        and the authoritative ``is_current``. None of the three is complete on
        its own, so all available ones are folded together.
        """
        if "standards" in self._cache:
            return self._cache["standards"]

        collected: list[Standard] = []
        sources: list[str] = []

        if self.exists("knowledge_base"):
            t0 = len(collected)
            collected += [Standard.from_record(r) for r in load_json(self.path("knowledge_base"))]
            sources.append(f"knowledge_base.json (+{len(collected) - t0})")
        if self.exists("search_corpus"):
            t0 = len(collected)
            collected += [Standard.from_record(r) for r in load_jsonl(self.path("search_corpus"))]
            sources.append(f"search_corpus.jsonl (+{len(collected) - t0})")
        if self.exists("merged_standards"):
            t0 = len(collected)
            payload = load_json(self.path("merged_standards"))
            rows = payload.values() if isinstance(payload, dict) else payload
            collected += [Standard.from_record(r) for r in rows]
            sources.append(f"merged_standards.json (+{len(collected) - t0})")

        if not collected:
            raise SchemaError(
                f"{self.root}: no standards found. Need at least one of "
                f"rag/knowledge_base.json, rag/search_corpus.jsonl, "
                f"merged/merged_standards.json.\n"
                f"  regenerate with: {REGEN_HINTS['knowledge_base']}"
            )

        merged = dedupe_standards(collected)
        self._cache["standards"] = merged
        self._cache["standard_sources"] = sources
        log.info("merged %d rows into %d standards from %s",
                 len(collected), len(merged), ", ".join(sources))
        return merged

    def standard_sources(self) -> list[str]:
        self.standards()
        return self._cache.get("standard_sources", [])

    def standards_by_canonical(self) -> dict[str, Standard]:
        if "by_canonical" not in self._cache:
            self._cache["by_canonical"] = {s.canonical: s for s in self.standards() if s.canonical}
        return self._cache["by_canonical"]

    def _designation_lookup(self) -> dict[str, str]:
        """designation (as written, and as re-parsed) -> canonical id."""
        if "by_designation" in self._cache:
            return self._cache["by_designation"]
        lookup: dict[str, str] = {}
        for std in self.standards():
            if not std.canonical:
                continue
            if std.designation:
                lookup[std.designation.strip().lower()] = std.canonical
                parsed = iscode.parse_designation(std.designation)
                if parsed:
                    lookup[parsed.canonical] = std.canonical
        self._cache["by_designation"] = lookup
        return lookup

    def resolve_designation(self, text: str) -> Optional[Standard]:
        """Find the standard a free-text designation refers to.

        Handles both ``"IS 302 (Part 1):2009"`` (exact, as stored) and
        ``"is 302 part 1 2009"`` / ``"IS 302-1:2009"`` (re-parsed canonical).
        """
        if not text:
            return None
        by_canonical = self.standards_by_canonical()
        lookup = self._designation_lookup()
        key = text.strip()
        if key.lower() in lookup:
            return by_canonical.get(lookup[key.lower()])
        parsed = iscode.parse_designation(key)
        if parsed:
            canonical = lookup.get(parsed.canonical)
            if canonical:
                return by_canonical.get(canonical)
        return None

    # ------------------------------------------------------------------
    # supersession / compliance chains
    # ------------------------------------------------------------------
    def supersession(self, canonical: str) -> Optional[Supersession]:
        """Return the replacement edition for ``canonical``, if one is known."""
        std = self.standards_by_canonical().get(canonical)
        if std is None:
            return None
        raw = std.superseded_by
        if not raw:
            chains = self._supersession_chains()
            raw = chains.get(canonical, "")
        if not raw:
            return None

        replacement = self.resolve_designation(raw)
        return Supersession(
            canonical=canonical,
            designation=std.designation,
            replacement_designation=replacement.designation if replacement else raw,
            replacement_canonical=replacement.canonical if replacement else "",
            replacement_year=replacement.year if replacement else None,
            in_dataset=replacement is not None,
        )

    def _supersession_chains(self) -> dict[str, str]:
        if "chains" not in self._cache:
            chains: dict[str, str] = {}
            if self.exists("cross_references"):
                payload = load_json(self.path("cross_references")) or {}
                chains = dict(payload.get("supersession_chains") or {})
            self._cache["chains"] = chains
        return self._cache["chains"]

    def superseded_standards(self) -> list[Standard]:
        return [s for s in self.standards() if not s.is_current]

    # ------------------------------------------------------------------
    # semantic indices
    # ------------------------------------------------------------------
    def category_hierarchy(self) -> dict:
        return self._json_cached("category_hierarchy", {})

    def cross_references(self) -> dict:
        return self._json_cached("cross_references", {})

    def domain_ontology(self) -> dict:
        return self._json_cached("domain_ontology", {})

    def temporal_index(self) -> dict:
        return self._json_cached("temporal_index", {})

    def search_facets(self) -> dict:
        return self._json_cached("search_facets", {})

    def _json_cached(self, key: str, default: Any) -> Any:
        if key not in self._cache:
            if self.exists(key):
                self._cache[key] = load_json(self.path(key))
            else:
                log.debug("%s absent; using default", key)
                self._cache[key] = default
        return self._cache[key]

    # ------------------------------------------------------------------
    # the pre-existing TF-IDF index
    # ------------------------------------------------------------------
    def tfidf_index(self) -> Optional[SearchIndex]:
        """Load ``index/search_index.json``, the 4.86 MB index already built.

        Reused verbatim rather than rebuilt: it is the sparse retrieval layer of
        the hybrid search, and rebuilding it here would duplicate logic that is
        already tested (``tests/test_merger_index.py``).
        """
        if "tfidf" not in self._cache:
            if not self.exists("search_index"):
                log.warning("index/search_index.json absent; sparse layer will use BM25 only")
                self._cache["tfidf"] = None
            else:
                index = SearchIndex.load(self.path("search_index"))
                log.info("loaded TF-IDF index: %d docs, dense=%s", len(index.docs), index.dense)
                self._cache["tfidf"] = index
        return self._cache["tfidf"]

    # ------------------------------------------------------------------
    # derived helpers used by the query processor
    # ------------------------------------------------------------------
    def divisions(self) -> list[str]:
        return sorted({s.division for s in self.standards() if s.division})

    def committees(self) -> list[str]:
        return sorted({s.committee for s in self.standards() if s.committee})

    def year_range(self) -> tuple[Optional[int], Optional[int]]:
        years = [s.year for s in self.standards() if s.year]
        return (min(years), max(years)) if years else (None, None)

    def concepts(self, *, min_standards: int = 2, limit: int = 5000) -> dict[str, list[str]]:
        """``concept -> [canonical, ...]`` from ``domain_ontology.json``.

        The generator keeps only concepts attached to more than one standard,
        which is exactly right for query expansion: a word that names a single
        standard is not a useful synonym trigger.
        """
        ontology = self.domain_ontology() or {}
        concepts = ontology.get("concepts") or {}
        if not concepts:
            # Fall back to keywords on the knowledge base, which carry the same
            # signal with coarser granularity.
            out: dict[str, list[str]] = {}
            for std in self.standards():
                for keyword in std.keywords:
                    out.setdefault(keyword.lower(), []).append(std.canonical)
            return {k: v for k, v in out.items() if len(v) >= min_standards}
        return {k: v for k, v in concepts.items() if len(v) >= min_standards}

    def summary(self) -> dict[str, Any]:
        """Counts for the CLI banner. Cheap: reads only what is cached/present."""
        info: dict[str, Any] = {
            "root": str(self.root),
            "standards": len(self.standards()) if any(
                self.exists(k) for k in ("knowledge_base", "search_corpus", "merged_standards")
            ) else 0,
            "chunks": len(self.chunks()) if self.exists("chunks") else 0,
        }
        info["divisions"] = len(self.divisions())
        info["current"] = sum(1 for s in self.standards() if s.is_current)
        info["superseded"] = info["standards"] - info["current"]
        info["compulsory"] = sum(1 for s in self.standards() if s.is_compulsory)
        info["year_range"] = self.year_range()
        info["tfidf"] = "present" if self.exists("search_index") else "absent"
        return info
