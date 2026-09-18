"""Persistent vector stores: ChromaDB when available, a portable fallback always.

Two backends, one interface
---------------------------
``chroma``
    A real ChromaDB ``PersistentClient``. This is what the plan asks for and it
    is the right answer when it installs -- HNSW indexing, metadata filtering
    and a well-known on-disk format.

``json``
    ``records.jsonl`` + ``vectors.npy`` + ``meta.json``. Brute-force cosine over
    a memory-mapped float32 matrix. For 9,043 chunks at 1,024 dimensions that is
    a 37 MB file and a ~4 ms scan, which is fast enough that the honest
    engineering answer is "do not add a dependency to save 4 ms". It also means
    the pipeline runs on a machine where ``chromadb`` will not install, which is
    the exact situation the repository's own ``index.py`` was written for.

Both backends enforce the same two invariants, because both are silent-corruption
risks otherwise:

1. **The embedder must match.** A query embedded by model A against vectors
   built by model B returns a ranked list of plausible nonsense. The store
   records an :func:`~bis_rag.embeddings.embedder_fingerprint` and refuses to
   serve a mismatched query.
2. **The width must match.** Same problem, caught earlier, with a clearer error.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

from .embeddings import Embedder, EmbedderMismatch
from .schema import SchemaError

log = logging.getLogger(__name__)

__all__ = ["Hit", "VectorStore", "ChromaVectorStore", "JsonVectorStore", "open_store",
           "available_backends", "distance_to_similarity",
           "CHUNK_COLLECTION", "STANDARD_COLLECTION", "COLLECTION_FOR", "detect_backend"]

META_FILE = "store_meta.json"

#: Collection names, defined once. The build script writes them and the search
#: layer reads them; when these disagreed (``bis_chunks`` vs ``chunks``) dense
#: retrieval silently disabled itself and search quietly fell back to BM25 only.
CHUNK_COLLECTION = "bis_chunks"
STANDARD_COLLECTION = "bis_standards"

#: Retrieval level -> collection name.
COLLECTION_FOR: dict[str, str] = {
    "chunks": CHUNK_COLLECTION,
    "standards": STANDARD_COLLECTION,
}


# ----------------------------------------------------------------------
# results
# ----------------------------------------------------------------------
@dataclass
class Hit:
    """One retrieved item, already normalised to a similarity in [-1, 1]."""

    id: str
    text: str
    metadata: dict[str, Any]
    score: float
    #: Which collection answered: ``chunks`` or ``standards``.
    collection: str = ""

    @property
    def designation(self) -> str:
        return str(self.metadata.get("designation") or self.metadata.get("canonical") or "")

    @property
    def title(self) -> str:
        return str(self.metadata.get("title") or "")

    @property
    def is_current(self) -> bool:
        value = self.metadata.get("is_current", True)
        return bool(value) if isinstance(value, bool) else str(value).lower() == "true"

    @property
    def canonical(self) -> str:
        return str(self.metadata.get("standard_id") or self.metadata.get("canonical") or "")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "score": round(self.score, 4),
            "designation": self.designation,
            "title": self.title,
            "is_current": self.is_current,
            "collection": self.collection,
            "metadata": self.metadata,
            "text": self.text,
        }


def distance_to_similarity(distance: float, *, metric: str = "cosine") -> float:
    """Convert a backend distance to a similarity.

    ChromaDB's cosine *distance* is ``1 - cosine_similarity``, but it clamps to
    ``[0, 2]`` and returns ``1 - sim`` rounded to float32, so a "perfect" match
    comes back as ``0.0`` and an orthogonal one as ``1.0``. Reporting raw
    distance as if it were a percentage is the single most common way these
    dashboards end up showing "0.7% match" for an exact hit.
    """
    if metric != "cosine":
        return 1.0 / (1.0 + max(0.0, distance))
    return 1.0 - distance


# ----------------------------------------------------------------------
# interface
# ----------------------------------------------------------------------
class VectorStore:
    """Minimal contract both backends honour."""

    backend: str = "base"

    def __init__(self, path: Path, name: str, *, dim: Optional[int] = None,
                 fingerprint: str = "", metric: str = "cosine"):
        self.path = Path(path)
        self.name = name
        self.dim = dim
        self.fingerprint = fingerprint
        self.metric = metric

    # -- writes -------------------------------------------------------
    def add(self, *, ids: Sequence[str], texts: Sequence[str],
            metadatas: Sequence[dict], embeddings: Sequence[Sequence[float]]) -> None:
        raise NotImplementedError

    def finalize(self) -> None:
        """Flush and write metadata. Called once after all ``add`` calls."""

    # -- reads --------------------------------------------------------
    def query(self, vector: Sequence[float], *, n_results: int = 10,
              where: Optional[dict] = None) -> list[Hit]:
        raise NotImplementedError

    def count(self) -> int:
        raise NotImplementedError

    def get_meta(self) -> dict:
        raise NotImplementedError

    # -- shared guards ------------------------------------------------
    def assert_compatible(self, embedder: Embedder) -> None:
        """Fail loudly rather than return meaningless neighbours."""
        stored = self.get_meta().get("embedder", {})
        stored_fp = stored.get("fingerprint") or self.fingerprint
        if stored_fp and embedder.fingerprint != stored_fp:
            raise EmbedderMismatch(
                f"store {self.name!r} was built with {stored.get('name', '?')} "
                f"(fingerprint {stored_fp}), but the query embedder is "
                f"{embedder.name} (fingerprint {embedder.fingerprint}).\n"
                f"  Cosine between vectors from different models is meaningless -- "
                f"the results would look plausible and be wrong.\n"
                f"  Rebuild the store with the same embedder:\n"
                f"      bis-rag build --embedder {embedder.name}\n"
                f"  or query with the embedder the store was built with:\n"
                f"      bis-rag query --embedder {stored.get('spec', 'hash')}"
            )
        stored_dim = stored.get("dim") or self.dim
        if stored_dim and embedder.dim and int(stored_dim) != int(embedder.dim):
            raise EmbedderMismatch(
                f"store {self.name!r} holds {stored_dim}-dimensional vectors but "
                f"{embedder.name} produces {embedder.dim}"
            )

    def describe(self) -> str:
        meta = self.get_meta()
        embedder = meta.get("embedder", {})
        return (f"{self.backend}://{self.path.name}/{self.name} "
                f"[{self.count()} vectors, embedder={embedder.get('name', '?')}]")


def _sanitize_metadata(meta: dict) -> dict:
    """Coerce to the types both backends accept, dropping ``None``.

    ChromaDB rejects ``None`` outright and (before 0.5) rejected empty lists.
    Numbers stay numbers so that ``{"year": {"$gte": 2010}}`` works: storing
    years as strings makes that filter match everything or nothing depending on
    lexicographic luck.
    """
    out: dict[str, Any] = {}
    for key, value in meta.items():
        if value is None:
            continue
        if isinstance(value, bool):
            out[key] = value
        elif isinstance(value, (int, float)):
            out[key] = value
        elif isinstance(value, str):
            out[key] = value
        elif isinstance(value, (list, tuple)):
            out[key] = ", ".join(str(v) for v in value)
        else:
            out[key] = str(value)
    return out


def _matches(meta: dict, where: Optional[dict]) -> bool:
    """Subset of Chroma's ``where`` grammar, for the JSON backend.

    Supports ``{"field": value}``, ``{"field": {"$eq|$ne|$gt|$gte|$lt|$lte|$in": v}}``
    and top-level ``$and`` / ``$or``.
    """
    if not where:
        return True
    for key, condition in where.items():
        if key == "$and":
            if not all(_matches(meta, clause) for clause in condition):
                return False
            continue
        if key == "$or":
            if not any(_matches(meta, clause) for clause in condition):
                return False
            continue
        value = meta.get(key)
        if isinstance(condition, dict):
            for op, operand in condition.items():
                if op == "$eq" and value != operand:
                    return False
                if op == "$ne" and value == operand:
                    return False
                if op == "$gt" and not (value is not None and value > operand):
                    return False
                if op == "$gte" and not (value is not None and value >= operand):
                    return False
                if op == "$lt" and not (value is not None and value < operand):
                    return False
                if op == "$lte" and not (value is not None and value <= operand):
                    return False
                if op == "$in" and value not in operand:
                    return False
        elif value != condition:
            return False
    return True


# ----------------------------------------------------------------------
# ChromaDB
# ----------------------------------------------------------------------
class ChromaVectorStore(VectorStore):
    backend = "chroma"

    def __init__(self, path: Path, name: str, *, dim: Optional[int] = None,
                 fingerprint: str = "", metric: str = "cosine",
                 embedder_name: str = "", create: bool = True):
        super().__init__(path, name, dim=dim, fingerprint=fingerprint, metric=metric)
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError as exc:  # pragma: no cover
            raise SchemaError(
                "chromadb is not installed. Install it with:\n"
                "    pip install chromadb\n"
                "or use the dependency-free backend:  --backend json"
            ) from exc

        self.path.mkdir(parents=True, exist_ok=True)
        # anonymized_telemetry off: this runs in offline/proctored environments
        # where a failed beacon adds seconds to every start-up.
        self._client = chromadb.PersistentClient(
            path=str(self.path),
            settings=Settings(anonymized_telemetry=False, allow_reset=True),
        )
        if create:
            self._collection = self._client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": metric},
                embedding_function=None,   # we always pass vectors explicitly
            )
        else:
            try:
                self._collection = self._client.get_collection(name=name,
                                                               embedding_function=None)
            except Exception as exc:
                raise SchemaError(
                    f"collection {name!r} not found in {self.path}. "
                    f"Run `bis-rag build` first."
                ) from exc
        self._embedder_name = embedder_name or self._read_meta().get("embedder", {}).get("name", "")
        self._write_meta()

    # -- meta ---------------------------------------------------------
    def _meta_path(self) -> Path:
        return self.path / META_FILE

    def _read_meta(self) -> dict:
        if self._meta_path().exists():
            try:
                return json.loads(self._meta_path().read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def _write_meta(self) -> None:
        meta = self._read_meta()
        meta.setdefault("backend", self.backend)
        meta["collections"] = sorted(set(meta.get("collections", [])) | {self.name})
        if self.fingerprint:
            meta["embedder"] = {"fingerprint": self.fingerprint, "name": self._embedder_name,
                                "dim": self.dim}
        self._meta_path().write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def get_meta(self) -> dict:
        meta = self._read_meta()
        embedder = meta.get("embedder")
        if not embedder and self._collection.metadata:
            # fall back to whatever the collection itself remembers
            embedder = {"fingerprint": self._collection.metadata.get("embedder_fp", ""),
                        "name": self._collection.metadata.get("embedder_name", ""),
                        "dim": self._collection.metadata.get("dim")}
        return {"backend": self.backend, "embedder": embedder or {}, "count": self.count()}

    # -- io -----------------------------------------------------------
    def add(self, *, ids: Sequence[str], texts: Sequence[str],
            metadatas: Sequence[dict], embeddings: Sequence[Sequence[float]]) -> None:
        if not ids:
            return
        self._collection.add(
            ids=list(ids),
            documents=list(texts),
            metadatas=[_sanitize_metadata(m) for m in metadatas],
            embeddings=[list(map(float, v)) for v in embeddings],
        )

    def finalize(self) -> None:
        self._write_meta()

    def count(self) -> int:
        return int(self._collection.count())

    def query(self, vector: Sequence[float], *, n_results: int = 10,
              where: Optional[dict] = None) -> list[Hit]:
        if self.count() == 0:
            return []
        result = self._collection.query(
            query_embeddings=[list(map(float, vector))],
            n_results=min(n_results, self.count()),
            where=where or None,
            include=["metadatas", "documents", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        hits: list[Hit] = []
        for i, item_id in enumerate(ids):
            hits.append(Hit(
                id=str(item_id),
                text=(docs[i] if i < len(docs) else "") or "",
                metadata=dict(metas[i] or {}) if i < len(metas) else {},
                score=distance_to_similarity(float(dists[i]) if i < len(dists) else 1.0,
                                             metric=self.metric),
                collection=self.name,
            ))
        return hits


# ----------------------------------------------------------------------
# portable fallback
# ----------------------------------------------------------------------
class JsonVectorStore(VectorStore):
    """``records.jsonl`` + ``vectors.npy``. No third-party dependency at all.

    Vectors live in a float32 ``.npy`` and are scored by a single
    ``matrix @ query``. That is exact cosine -- not an approximation -- so the
    only thing given up versus HNSW is speed on corpora far larger than this
    one (approximately 10^7 vectors before the linear scan stops being
    instantaneous).
    """

    backend = "json"

    def __init__(self, path: Path, name: str, *, dim: Optional[int] = None,
                 fingerprint: str = "", metric: str = "cosine",
                 embedder_name: str = "", create: bool = True):
        super().__init__(path, name, dim=dim, fingerprint=fingerprint, metric=metric)
        self.dir = Path(path) / name
        self.records_path = self.dir / "records.jsonl"
        self.vectors_path = self.dir / "vectors.npy"
        self.meta_path = self.dir / META_FILE
        self._embedder_name = embedder_name
        self._pending: list[dict] = []
        self._pending_vectors: list[list[float]] = []
        self._matrix = None
        self._records: list[dict] = []

        if create:
            self.dir.mkdir(parents=True, exist_ok=True)
        elif not self.records_path.exists():
            raise SchemaError(
                f"collection {name!r} not found in {self.dir}. Run `bis-rag build` first."
            )

    # -- meta ---------------------------------------------------------
    def _read_meta(self) -> dict:
        if self.meta_path.exists():
            try:
                return json.loads(self.meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def _write_meta(self) -> None:
        meta = self._read_meta()
        meta.update({
            "backend": self.backend,
            "collection": self.name,
            "count": self._total_count(),
            "metric": self.metric,
        })
        if self.fingerprint:
            meta["embedder"] = {"fingerprint": self.fingerprint, "name": self._embedder_name,
                                "dim": self.dim}
        self.dir.mkdir(parents=True, exist_ok=True)
        self.meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def get_meta(self) -> dict:
        meta = self._read_meta()
        meta.setdefault("backend", self.backend)
        meta["count"] = self._total_count()
        return meta

    # -- io -----------------------------------------------------------
    def add(self, *, ids: Sequence[str], texts: Sequence[str],
            metadatas: Sequence[dict], embeddings: Sequence[Sequence[float]]) -> None:
        for i, item_id in enumerate(ids):
            self._pending.append({
                "id": str(item_id),
                "text": texts[i] if i < len(texts) else "",
                "metadata": _sanitize_metadata(metadatas[i] if i < len(metadatas) else {}),
            })
            self._pending_vectors.append(list(map(float, embeddings[i])))
        if self.dim is None and self._pending_vectors:
            self.dim = len(self._pending_vectors[0])

    def _total_count(self) -> int:
        if self._pending:
            return len(self._pending)
        if self.records_path.exists():
            return sum(1 for line in self.records_path.open(encoding="utf-8") if line.strip())
        return 0

    def finalize(self) -> None:
        if not self._pending:
            return
        import numpy as np

        self.dir.mkdir(parents=True, exist_ok=True)
        # Rewrite wholesale: a partial append of vectors to an existing matrix
        # is the kind of bug that only shows up as slightly-wrong scores.
        existing_records = self._read_records() if self.records_path.exists() else []
        with open(self.records_path, "w", encoding="utf-8") as fh:
            for record in existing_records + self._pending:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")

        new_matrix = np.asarray(self._pending_vectors, dtype=np.float32)
        if self.vectors_path.exists() and existing_records:
            old = np.load(self.vectors_path)
            new_matrix = np.vstack([old, new_matrix]) if old.size else new_matrix
        np.save(self.vectors_path, new_matrix)

        self._pending = []
        self._pending_vectors = []
        self._matrix = None
        self._records = []
        self._write_meta()

    def _read_records(self) -> list[dict]:
        if self._records:
            return self._records
        out: list[dict] = []
        with open(self.records_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        self._records = out
        return out

    def _load_matrix(self):
        if self._matrix is None:
            import numpy as np

            if not self.vectors_path.exists():
                self._matrix = np.zeros((0, self.dim or 0), dtype=np.float32)
            else:
                self._matrix = np.load(self.vectors_path)
                norms = np.linalg.norm(self._matrix, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                self._matrix = self._matrix / norms
        return self._matrix

    def count(self) -> int:
        return self._total_count()

    def query(self, vector: Sequence[float], *, n_results: int = 10,
              where: Optional[dict] = None) -> list[Hit]:
        import numpy as np

        matrix = self._load_matrix()
        if matrix.size == 0:
            return []
        query = np.asarray(vector, dtype=np.float32)
        norm = float(np.linalg.norm(query)) or 1.0
        query = query / norm
        if query.shape[0] != matrix.shape[1]:
            raise EmbedderMismatch(
                f"query vector has {query.shape[0]} dimensions but the store holds "
                f"{matrix.shape[1]}"
            )
        scores = matrix @ query
        records = self._read_records()

        # Rank first, filter after -- but over-fetch so that a selective filter
        # does not empty the result set.
        order = np.argsort(-scores)
        hits: list[Hit] = []
        scanned = 0
        for idx in order:
            if scanned > max(n_results * 50, 200):
                break
            scanned += 1
            record = records[int(idx)]
            if not _matches(record.get("metadata", {}), where):
                continue
            hits.append(Hit(
                id=record["id"],
                text=record.get("text", ""),
                metadata=dict(record.get("metadata", {})),
                score=float(scores[int(idx)]),
                collection=self.name,
            ))
            if len(hits) >= n_results:
                break
        return hits


# ----------------------------------------------------------------------
# factory
# ----------------------------------------------------------------------
def available_backends() -> list[str]:
    """Backends importable right now, best first.

    Used by ``doctor`` and by the ``auto`` preference order, so it must not
    import chromadb just to answer -- ``find_spec`` is a metadata lookup.
    """
    import importlib.util

    backends = ["json"]
    if importlib.util.find_spec("chromadb") is not None:
        backends.insert(0, "chroma")
    return backends


def detect_backend(path: Path | str, name: str) -> Optional[str]:
    """Work out which backend wrote a store directory.

    Needed because ``auto`` cannot simply prefer ChromaDB: a store built with
    ``--backend json`` and then queried with ``auto`` on a machine that happens
    to have chromadb installed would look in the wrong place, find nothing, and
    silently disable dense retrieval. The directory says what it is, so ask it.
    """
    path = Path(path)
    # The JSON backend keeps its data in a per-collection subdirectory.
    if (path / name / "records.jsonl").exists():
        return "json"
    meta_file = path / META_FILE
    if meta_file.exists():
        try:
            backend = json.loads(meta_file.read_text(encoding="utf-8")).get("backend")
            if backend:
                return str(backend)
        except (json.JSONDecodeError, OSError):
            pass
    if (path / "chroma.sqlite3").exists():
        return "chroma"
    return None


def open_store(path: Path | str, name: str, *, backend: str = "auto",
               dim: Optional[int] = None, fingerprint: str = "",
               embedder_name: str = "", metric: str = "cosine",
               create: bool = True) -> VectorStore:
    """Open (or create) a collection, choosing a backend.

    ``auto`` prefers ChromaDB when importable and falls back to ``json`` with a
    warning, so a build never fails just because an optional dependency is
    missing -- it just gets slower and says so.
    """
    path = Path(path)
    if backend == "auto":
        # An existing store wins over the preference order; only a fresh build
        # gets to choose, and there it prefers the better backend.
        backend = detect_backend(path, name) or (
            "chroma" if "chroma" in available_backends() else "json")
    kwargs = dict(dim=dim, fingerprint=fingerprint, metric=metric,
                  embedder_name=embedder_name, create=create)
    if backend == "chroma":
        return ChromaVectorStore(path, name, **kwargs)
    if backend == "json":
        return JsonVectorStore(path, name, **kwargs)
    raise SchemaError(f"unknown backend {backend!r}; expected 'auto', 'chroma' or 'json'")


def reset_store(path: Path | str) -> None:
    """Delete a store directory. Used by ``bis-rag build --force``."""
    path = Path(path)
    if path.exists():
        shutil.rmtree(path)
        log.info("removed %s", path)
