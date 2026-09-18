"""Embedding backends, and the guard that stops you mixing them.

The honest summary
------------------
There is no way to run ``BAAI/bge-large-en-v1.5`` in the environment this
repository is developed in: the weights are ~1.3 GB, they need torch, and the
sandbox has no route to huggingface.co. Pretending otherwise produces a script
that only runs on one laptop.

So this module ships three backends behind one interface, and is loud about
which one you are using:

``hash``
    Default. Deterministic hashed bag-of-words with the same tokenizer as
    ``bis_pipeline.index``. **This is lexical, not semantic.** "water pipe"
    will not match "conduit for aqueous transport". It exists so the whole
    pipeline is runnable, testable and correct with zero downloads -- then you
    swap it for a real model on a machine that has one.
``st:<model>``
    ``sentence-transformers``. Use ``st:BAAI/bge-large-en-v1.5`` for the
    retrieval quality the plan describes. Requires the ``dense`` extra.
``api:<model>``
    Any OpenAI-compatible ``/v1/embeddings`` endpoint -- OpenAI, Voyage,
    Together, Jina, or a local text-embeddings-inference / Ollama server.

The mixing guard
----------------
ChromaDB will happily accept a query vector from a *different* model than the
one that built the collection. The result is not an error: it is a ranked list
of plausible-looking, meaningless hits. Every store therefore records an
:func:`embedder_fingerprint` at build time and the query path compares, raising
:class:`EmbedderMismatch` with instructions rather than returning garbage.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional, Sequence

from .schema import SchemaError

log = logging.getLogger(__name__)

__all__ = [
    "Embedder",
    "HashingEmbedder",
    "SentenceTransformerEmbedder",
    "APIEmbedder",
    "EmbedderMismatch",
    "get_embedder",
    "embedder_fingerprint",
]

#: Bumped whenever the text handed to a backend changes, so that fingerprints
#: from an older build invalidate instead of silently overlapping.
PREPROCESS_VERSION = "1"


class EmbedderMismatch(SchemaError):
    """Raised when a query embedder does not match the one that built a store."""


class Embedder:
    """Interface every backend implements.

    ``dim`` may be ``None`` for models whose width is only known once loaded
    (most API models report it on first call).
    """

    name: str = "base"
    dim: Optional[int] = None
    #: True when the backend has any chance of matching on *meaning*. The CLI
    #: prints this so nobody mistakes the offline fallback for semantic search.
    semantic: bool = False

    def encode(self, texts: Sequence[str], *, batch_size: int = 32,
               is_query: bool = False) -> list[list[float]]:
        raise NotImplementedError

    def encode_one(self, text: str, *, is_query: bool = False) -> list[float]:
        return self.encode([text], is_query=is_query)[0]

    @property
    def fingerprint(self) -> str:
        return embedder_fingerprint(self)


def embedder_fingerprint(embedder: Embedder) -> str:
    """Stable id of (backend, model, width, preprocessing) for store metadata."""
    payload = "|".join([
        type(embedder).__name__,
        embedder.name,
        str(embedder.dim or "auto"),
        PREPROCESS_VERSION,
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ----------------------------------------------------------------------
# offline default
# ----------------------------------------------------------------------
@dataclass
class HashingEmbedder(Embedder):
    """Signed hashing-trick bag of words. Lexical, deterministic, offline.

    Mirrors ``bis_pipeline.index``: same tokenizer (which keeps ``IS-14220``
    and ``IS/IEC 61730-1`` intact), same word-bigram expansion, so the lexical
    score a user sees from BM25 and from this "dense" layer agree rather than
    disagreeing in confusing ways.
    """

    dim: int = 4096
    with_bigrams: bool = True
    name: str = field(init=False, default="hash-bow-v1")
    semantic: bool = field(init=False, default=False)

    def encode(self, texts: Sequence[str], *, batch_size: int = 32,
               is_query: bool = False) -> list[list[float]]:
        from bis_pipeline.index import tokenize  # local import: keeps this module importable alone

        out: list[list[float]] = []
        for text in texts:
            counts: dict[int, float] = {}
            tokens = tokenize(text or "")
            if self.with_bigrams:
                tokens = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
            for tok in tokens:
                digest = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
                h = int.from_bytes(digest, "big")
                bucket = h % self.dim
                sign = 1.0 if (h >> 63) & 1 else -1.0
                counts[bucket] = counts.get(bucket, 0.0) + sign

            vec = [0.0] * self.dim
            for bucket, value in counts.items():
                # Sublinear scaling (1 + log|v|) with the sign kept: without it a
                # long OCR chunk outscores a short precise one purely on length,
                # which is the classic bag-of-words failure mode.
                magnitude = abs(value)
                scaled = magnitude if magnitude <= 1.0 else 1.0 + math.log(magnitude)
                vec[bucket] = scaled if value >= 0 else -scaled
            norm = sum(v * v for v in vec) ** 0.5
            if norm:
                vec = [v / norm for v in vec]
            out.append(vec)
        return out


# ----------------------------------------------------------------------
# real embeddings
# ----------------------------------------------------------------------
class SentenceTransformerEmbedder(Embedder):
    """Local ``sentence-transformers`` model. The quality option, when available.

    Handles the BGE/E5 query-instruction convention, which is *not* optional
    detail: ``bge-large-en-v1.5`` expects retrieval queries to carry the prefix
    ``"Represent this sentence for searching relevant passages: "`` while
    passages carry none. Omitting it on the query side costs several points of
    recall and is invisible in the code that does it.
    """

    semantic = True
    #: Prefixes for models that need an asymmetric query instruction.
    _QUERY_PREFIXES = (
        ("bge-", "Represent this sentence for searching relevant passages: "),
        ("e5-", "query: "),
        ("gte-", ""),
    )
    _PASSAGE_PREFIXES = (
        ("e5-", "passage: "),
    )

    def __init__(self, model_name: str = "BAAI/bge-large-en-v1.5",
                 *, device: Optional[str] = None, query_prefix: Optional[str] = None):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise SchemaError(
                "sentence-transformers is not installed. Install the dense extra:\n"
                "    pip install 'sentence-transformers>=2.7'\n"
                "or run with the offline backend:  --embedder hash"
            ) from exc

        log.info("loading sentence-transformers model %s", model_name)
        self.model = SentenceTransformer(model_name, device=device)
        self.model_name = model_name
        self.name = f"st:{model_name}"
        self.dim = int(self.model.get_sentence_embedding_dimension())

        lowered = model_name.lower()
        self.query_prefix = query_prefix
        if self.query_prefix is None:
            self.query_prefix = ""
            for marker, prefix in self._QUERY_PREFIXES:
                if marker in lowered:
                    self.query_prefix = prefix
                    break
        self.passage_prefix = ""
        for marker, prefix in self._PASSAGE_PREFIXES:
            if marker in lowered:
                self.passage_prefix = prefix
                break

    def encode(self, texts: Sequence[str], *, batch_size: int = 32,
               is_query: bool = False) -> list[list[float]]:
        prefix = self.query_prefix if is_query else self.passage_prefix
        payload = [f"{prefix}{t}" for t in texts] if prefix else list(texts)
        vectors = self.model.encode(
            payload,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,   # cosine == dot product, and Chroma wants unit vectors
            convert_to_numpy=True,
        )
        return [list(map(float, row)) for row in vectors]


class APIEmbedder(Embedder):
    """OpenAI-compatible ``/v1/embeddings``.

    Batching, retry with backoff, and a hard failure on a dimension that
    changes mid-run (which would corrupt a store built across two models).
    """

    semantic = True

    def __init__(self, model: str, *, base_url: Optional[str] = None,
                 api_key: Optional[str] = None, dim: Optional[int] = None,
                 timeout: float = 60.0, max_retries: int = 3):
        self.model = model
        self.base_url = (base_url or os.environ.get("EMBEDDING_BASE_URL")
                         or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or os.environ.get("EMBEDDING_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.dim = dim
        self.timeout = timeout
        self.max_retries = max_retries
        self.name = f"api:{model}"
        if not self.api_key:
            raise SchemaError(
                "no API key for the embeddings endpoint. Set EMBEDDING_API_KEY "
                "(or OPENAI_API_KEY), or use --embedder hash / st:<model>."
            )

    def encode(self, texts: Sequence[str], *, batch_size: int = 32,
               is_query: bool = False) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = list(texts[start:start + batch_size])
            out.extend(self._post(batch))
        return out

    def _post(self, batch: Sequence[str]) -> list[list[float]]:
        body = json.dumps({"model": self.model, "input": list(batch)}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/embeddings",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                rows = sorted(payload["data"], key=lambda row: row.get("index", 0))
                vectors = [list(map(float, row["embedding"])) for row in rows]
                if self.dim is None:
                    self.dim = len(vectors[0])
                elif len(vectors[0]) != self.dim:
                    raise EmbedderMismatch(
                        f"embedding endpoint returned width {len(vectors[0])}, "
                        f"expected {self.dim}; the model behind it changed mid-run"
                    )
                return vectors
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:200]
                last_error = SchemaError(f"embeddings endpoint returned {exc.code}: {detail}")
                if exc.code in (429, 500, 502, 503, 504) and attempt + 1 < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise last_error from exc
            except (urllib.error.URLError, TimeoutError, KeyError) as exc:
                last_error = exc
                if attempt + 1 < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
        raise SchemaError(f"embeddings request failed after {self.max_retries} attempts: {last_error}")


# ----------------------------------------------------------------------
# factory
# ----------------------------------------------------------------------
def get_embedder(spec: Optional[str] = None, **kwargs) -> Embedder:
    """Build an embedder from a spec string.

    ``None`` reads ``$BIS_RAG_EMBEDDER`` then falls back to ``hash``. Specs::

        hash                      offline lexical default
        hash:8192                 offline, wider buckets
        st:BAAI/bge-large-en-v1.5 local sentence-transformers
        api:text-embedding-3-small OpenAI-compatible endpoint
    """
    spec = spec or os.environ.get("BIS_RAG_EMBEDDER") or "hash"
    spec = spec.strip()

    if spec.startswith("st:"):
        return SentenceTransformerEmbedder(spec[3:], **kwargs)
    if spec.startswith("api:"):
        return APIEmbedder(spec[4:], **kwargs)
    if spec == "hash" or spec.startswith("hash:"):
        dim = int(spec.split(":", 1)[1]) if ":" in spec else 4096
        return HashingEmbedder(dim=dim)
    raise SchemaError(
        f"unknown embedder spec {spec!r}; expected 'hash', 'hash:<dim>', "
        f"'st:<model>' or 'api:<model>'"
    )


def describe(embedder: Embedder) -> str:
    """One-line description for logs and CLI output, honest about capability."""
    quality = "semantic" if embedder.semantic else "lexical only (no download required)"
    return f"{embedder.name} [dim={embedder.dim}, {quality}, fp={embedder.fingerprint}]"
