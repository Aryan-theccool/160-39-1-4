"""Search index over the merged standards dataset.

Default backend
---------------
A dependency-free hashed TF-IDF cosine index. It needs nothing beyond the
standard library, loads in milliseconds, and is a *honest* lexical baseline:
"drinking water quality" matches titles and text containing those words.

That is a deliberate choice. The usual alternative -- a 1.3 GB sentence
transformer plus a vector DB -- cannot be installed or run in a constrained
environment, and pretending otherwise makes the pipeline unrunnable exactly
where it is most likely to be tried first.

Dense retrieval
---------------
Pass ``embed_fn`` to :meth:`SearchIndex.build` to plug in real embeddings
(sentence-transformers, an API, anything returning a list of floats). The index
then stores dense vectors and does exact cosine search over them. ChromaDB is
*not* required for this; see :func:`export_for_chroma` if you do want it.

Retrieval hygiene
-----------------
Every hit carries ``is_current`` and ``status``. A standards recommender that
can return a superseded 1994 edition without saying so is worse than no
recommender, so callers should filter on ``is_current`` -- :meth:`search` does
it for you by default.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence

log = logging.getLogger(__name__)

#: Dimensions for the hashing trick. 2**16 keeps collisions rare for a corpus
#: of ~22k documents while staying small enough to hold in memory.
DEFAULT_DIM = 1 << 16

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9.\-/]*")
_STOPWORDS = frozenset("""
a an and are as at be by for from has have in is it its of on or that the this to was were will with
""".split())


def tokenize(text: str) -> list[str]:
    """Lowercase, de-accent, split and lightly stem.

    Two decisions matter for this corpus:

    * Hyphens and slashes stay *inside* tokens. Standards text is full of
      designations like ``IS-14220`` and ``IS/IEC 61730-1``; splitting them
      would destroy the most searchable strings in the dataset.
    * A trailing ``s`` is folded away. BIS titles are plural ("Submersible
      pumps", "Requirements") while queries are usually singular ("pump"),
      and without this a query for ``pump`` scores zero against ``pumps``.
      Only a plain plural ``s`` is removed -- ``es``/``ies`` endings are left
      alone, so "requirements" and "alloys" keep their distinct forms.
    """
    if not text:
        return []
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    tokens = []
    for tok in _TOKEN_RE.findall(text.lower()):
        tok = tok.strip(".-/")
        if not tok or tok in _STOPWORDS:
            continue
        if len(tok) > 3 and tok.endswith("s") and not tok.endswith(("es", "ss", "us", "is")):
            tok = tok[:-1]
        tokens.append(tok)
    return tokens


def _with_bigrams(tokens: Sequence[str]) -> list[str]:
    """Add adjacent pairs so "drinking water" beats "water ... drinking"."""
    out = list(tokens)
    for a, b in zip(tokens, tokens[1:]):
        out.append(f"{a}_{b}")
    return out


def _hash_token(token: str, dim: int) -> tuple[int, float]:
    """Feature-hashing bucket plus sign, so collisions partly cancel.

    Uses a digest rather than the builtin ``hash()`` **on purpose**: CPython
    salts ``hash()`` per process (``PYTHONHASHSEED``), so buckets assigned
    while building the index would not match those assigned while querying it
    in a separate process. A persisted index would silently return nothing.
    """
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    h = int.from_bytes(digest, "big") & 0x7FFFFFFF
    return h % dim, (1.0 if (h >> 31) & 1 else -1.0)


@dataclass
class SearchHit:
    designation: str
    title: str
    score: float
    #: Publication year, or None when the index was built before years were
    #: recorded. None is *unknown*, never "no year" -- and it must never be a
    #: sentinel like -1, which a `$lte` filter would silently accept.
    year: Optional[int] = None
    status: str = "unknown"
    is_current: bool = True
    superseded_by: str = ""
    canonical: str = ""
    archive_url: str = ""
    is_compulsory: bool = False
    snippet: str = ""

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class SearchIndex:
    """A small, serialisable search index."""

    dim: int = DEFAULT_DIM
    dense: bool = False
    docs: list[dict] = field(default_factory=list)
    vectors: list[dict] = field(default_factory=list)
    idf: dict[str, float] = field(default_factory=dict)
    dense_vectors: list[list[float]] = field(default_factory=list)
    embed_fn: Optional[Callable[[list[str]], list[list[float]]]] = field(default=None, repr=False)

    # ------------------------------------------------------------------
    # build
    # ------------------------------------------------------------------
    def build(self, records: Iterable, *, documents: Optional[Sequence[str]] = None,
              texts_for_snippets: Optional[Sequence[str]] = None,
              index_chars: int = 20_000,
              embed_fn: Optional[Callable[[list[str]], list[list[float]]]] = None) -> "SearchIndex":
        """Index `records` (``StandardRecord``-like objects).

        ``documents`` overrides the embedded text; by default each record's
        ``retrieval_text()`` is used, with OCR text appended when a
        ``text_path`` is present. Only the first ``index_chars`` of each file
        are read: the whole 22k-item corpus would otherwise be ~550 MB in
        memory, and BIS front matter past the Scope clause is mostly tables.

        Pass ``embed_fn`` to use dense vectors instead of the built-in TF-IDF.
        """
        if embed_fn is not None:
            self.embed_fn = embed_fn
        records = list(records)
        self.docs = []
        self.vectors = []
        self.dense_vectors = []

        if documents is None:
            documents = [self._document_for(r, index_chars) for r in records]

        self.dense = self.embed_fn is not None
        if self.dense:
            self.dense_vectors = [list(map(float, v)) for v in self.embed_fn(list(documents))]
        else:
            df: Counter = Counter()
            raw: list[Counter] = []
            for doc in documents:
                counts = Counter()
                for tok in _with_bigrams(tokenize(doc)):
                    bucket, sign = _hash_token(tok, self.dim)
                    counts[str(bucket)] += sign
                raw.append(counts)
                df.update(counts.keys())

            n = max(1, len(documents))
            self.idf = {k: math.log((1 + n) / (1 + v)) + 1.0 for k, v in df.items()}
            self.vectors = [_l2_normalise(
                {k: c * self.idf.get(k, 1.0) for k, c in counts.items()}) for counts in raw]

        for i, (rec, doc) in enumerate(zip(records, documents)):
            snippet_source = texts_for_snippets[i] if texts_for_snippets else doc
            year = getattr(rec, "year", None)
            self.docs.append({
                "designation": getattr(rec, "designation", ""),
                "title": getattr(rec, "title", ""),
                # Numeric year, not a string: a filter has to compare 1998 > 999
                # and a lexicographic field would quietly get that wrong. Zero
                # means unknown, and `SearchHit.year` maps it back to None so
                # nothing downstream has to know that.
                "year": int(year) if isinstance(year, (int, float)) and year else 0,
                "status": getattr(rec, "status", "unknown"),
                "is_current": bool(getattr(rec, "is_current", True)),
                "superseded_by": getattr(rec, "superseded_by", ""),
                "canonical": getattr(rec, "canonical", ""),
                "archive_url": getattr(rec, "archive_url", ""),
                "is_compulsory": bool(getattr(rec, "is_compulsory", False)),
                "snippet": _snippet(snippet_source),
            })

        log.info("indexed %d documents (%s backend)", len(self.docs),
                 "dense" if self.dense else "tf-idf")
        return self

    def _document_for(self, rec, index_chars: int = 20_000) -> str:
        text = ""
        text_path = getattr(rec, "text_path", "")
        if text_path and Path(text_path).exists():
            try:
                with open(text_path, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read(index_chars)
            except OSError as exc:
                log.debug("could not read %s: %s", text_path, exc)
        return rec.retrieval_text(content=text)

    # ------------------------------------------------------------------
    # search
    # ------------------------------------------------------------------
    def search(self, query: str, *, k: int = 5, current_only: bool = True,
               min_score: float = 0.05) -> list[SearchHit]:
        """Return the top `k` matches, best first.

        ``current_only=True`` suppresses superseded editions -- a recommender
        should not propose IS 14220:1994 when it also holds the 2002 revision.

        ``min_score`` defaults above zero on purpose. Cosine over TF-IDF is
        never exactly 0 for a big enough corpus: a query sharing one stopword-
        adjacent stem with a document scores ~0.02, and returning that as the
        top hit for "submersible pump" is worse than answering "no match".
        """
        if not self.docs:
            return []

        scored = self._score_all(query)
        ranked = sorted(scored, key=lambda s: s[0], reverse=True)

        out: list[SearchHit] = []
        for score, idx in ranked:
            if score <= min_score:
                break
            doc = dict(self.docs[idx])
            if current_only and not doc["is_current"]:
                continue
            raw_year = doc.get("year")
            # Absent key (an index built before this field existed) or 0 both
            # mean unknown.
            doc["year"] = int(raw_year) if isinstance(raw_year, (int, float)) and raw_year else None
            out.append(SearchHit(score=round(score, 6), **doc))
            if len(out) >= k:
                break
        return out

    def _score_all(self, query: str) -> list[tuple[float, int]]:
        if self.dense:
            qv = _l2_normalise_dict_from_list(self.embed_fn([query])[0])
            return [(_dot(qv, _list_to_dict(v)), i) for i, v in enumerate(self.dense_vectors)]

        qcounts: Counter = Counter()
        for tok in _with_bigrams(tokenize(query)):
            bucket, sign = _hash_token(tok, self.dim)
            qcounts[str(bucket)] += sign
        qv = _l2_normalise({k: c * self.idf.get(k, 1.0) for k, c in qcounts.items()})
        return [(_dot(qv, v), i) for i, v in enumerate(self.vectors)]

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------
    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "dim": self.dim, "dense": self.dense, "docs": self.docs,
            "vectors": self.vectors, "idf": self.idf, "dense_vectors": self.dense_vectors,
        }), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path, *, embed_fn: Optional[Callable] = None) -> "SearchIndex":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        index = cls(dim=data["dim"], dense=data["dense"], docs=data["docs"],
                    vectors=data["vectors"], idf=data["idf"],
                    dense_vectors=data["dense_vectors"])
        index.embed_fn = embed_fn
        return index

    def __len__(self) -> int:
        return len(self.docs)


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _l2_normalise(vec: dict) -> dict:
    norm = math.sqrt(sum(v * v for v in vec.values()))
    if norm == 0:
        return {}
    return {k: v / norm for k, v in vec.items()}


def _l2_normalise_dict_from_list(vec: Sequence[float]) -> dict:
    return _l2_normalise({str(i): v for i, v in enumerate(vec) if v})


def _list_to_dict(vec: Sequence[float]) -> dict:
    return {str(i): v for i, v in enumerate(vec) if v}


def _dot(a: dict, b: dict) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b[k] for k, v in a.items() if k in b)


def _snippet(text: str, limit: int = 220) -> str:
    if not text:
        return ""
    flat = " ".join(text.split())
    return flat[:limit] + ("..." if len(flat) > limit else "")


def export_for_chroma(index: SearchIndex) -> dict:
    """Render the index in the shape ``collection.add(**...)`` expects.

    Provided so a ChromaDB deployment is a two-line change rather than a
    rewrite::

        client.get_or_create_collection("bis_standards").add(**export_for_chroma(idx))
    """
    return {
        "ids": [d["canonical"] or f"doc_{i}" for i, d in enumerate(index.docs)],
        "documents": [f"{d['designation']} {d['title']}" for d in index.docs],
        "metadatas": [{k: v for k, v in d.items() if k != "snippet"} | {"snippet": d["snippet"]}
                      for d in index.docs],
        "embeddings": index.dense_vectors or None,
    }
