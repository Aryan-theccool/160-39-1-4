"""BM25 over the standards and chunk corpora. Part 3, sparse half.

Two sparse retrievers, deliberately
-----------------------------------
``BM25Index`` (this module)
    A real Okapi BM25 with per-field weighting. Built in memory at query time
    from ``chunked_documents.jsonl`` / ``search_corpus.jsonl`` in about a
    second for 9,043 chunks.

``bis_pipeline.index.SearchIndex`` (already in the repo, already tested)
    The 4.86 MB pre-built TF-IDF cosine index. Loaded verbatim through
    :meth:`~bis_rag.data.BisData.tfidf_index`.

Why keep both rather than picking one: they fail differently, and the fusion
step wants that. BM25 with ``b=0.75`` normalises for document length and rewards
rare terms, which is right for "unplasticized PVC" and wrong for a long
descriptive question. The hashed TF-IDF cosine is length-blind and bigram-aware,
which catches phrases like "drinking water" that BM25 splits into two
common-ish tokens. Fusing them is strictly better than either, and both are
cheap enough that there is no reason not to.

Reusing the repo's tokenizer is not incidental: ``bis_pipeline.index.tokenize``
keeps hyphens and slashes inside tokens so ``IS-14220`` and ``IS/IEC 61730-1``
survive, and applies the light stemming that keeps ``pipes`` and ``pipe``
together. A separate tokenizer here would make the sparse and TF-IDF scores
disagree about the same query.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence

from bis_pipeline.index import SearchIndex, tokenize

from .schema import Chunk, Standard

log = logging.getLogger(__name__)

__all__ = ["BM25Index", "BM25Document", "rank_bm25_hits"]

#: Okapi defaults. ``b=0.75`` is the standard length-normalisation strength;
#: ``k1=1.5`` is on the lower end of the usual 1.2-2.0 because these documents
#: are short and repetitive, and a larger k1 lets one repeated term dominate.
K1 = 1.5
B = 0.75

#: Title terms are worth more than body terms. A standard whose *title* mentions
#: "cement" is about cement; one that mentions it once in a Foreword is not.
TITLE_BOOST = 2.0
DESIGNATION_BOOST = 3.0

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


@dataclass
class BM25Document:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    #: Pre-tokenised term frequencies. Kept so a rebuild is not needed per query.
    tokens: list[str] = field(default_factory=list, repr=False)

    @classmethod
    def from_chunk(cls, chunk: Chunk) -> "BM25Document":
        # Index the metadata header as well as the passage: a chunk whose body
        # never repeats "IS 1239" must still match a query naming it.
        text = f"{chunk.designation} {chunk.title} {chunk.division} {chunk.committee} {chunk.text}"
        return cls(id=chunk.chunk_id, text=chunk.text,
                   metadata=chunk.as_metadata(), tokens=tokenize(text))

    @classmethod
    def from_standard(cls, standard: Standard) -> "BM25Document":
        text = " ".join(filter(None, [
            standard.designation, standard.title, standard.division,
            standard.committee, " ".join(standard.keywords), standard.summary,
        ]))
        return cls(id=standard.canonical or standard.designation, text=standard.summary,
                   metadata=standard.as_metadata(),
                   tokens=tokenize(text))


class BM25Index:
    """Okapi BM25 over a list of :class:`BM25Document`."""

    def __init__(self, documents: Sequence[BM25Document], *, k1: float = K1, b: float = B,
                 designation_boost: float = DESIGNATION_BOOST,
                 title_boost: float = TITLE_BOOST):
        self.documents = list(documents)
        self.k1 = k1
        self.b = b
        self.designation_boost = designation_boost
        self.title_boost = title_boost

        self._doc_freqs: list[Counter] = []
        self._doc_lengths: list[int] = []
        for document in self.documents:
            tokens = document.tokens or tokenize(document.text)
            self._doc_freqs.append(Counter(tokens))
            self._doc_lengths.append(len(tokens))

        self._n = len(self.documents)
        self._avgdl = (sum(self._doc_lengths) / self._n) if self._n else 0.0
        self._idf: dict[str, float] = {}
        df: Counter = Counter()
        for freqs in self._doc_freqs:
            df.update(freqs.keys())
        for term, count in df.items():
            # Lucene-style BM25 idf: smooth, and never negative, so a term
            # present in every document contributes ~0 rather than actively
            # penalising matches.
            self._idf[term] = math.log(1 + (self._n - count + 0.5) / (count + 0.5))

    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return self._n

    def idf(self, term: str) -> float:
        return self._idf.get(term, math.log(1 + (self._n + 0.5) / 0.5) if self._n else 0.0)

    def _field_boost(self, idx: int, term: str) -> float:
        meta = self.documents[idx].metadata
        boost = 1.0
        designation = str(meta.get("designation") or "").lower()
        title = str(meta.get("title") or "").lower()
        if term in _NON_ALNUM.split(designation):
            boost *= self.designation_boost
        if term in _NON_ALNUM.split(title):
            boost *= self.title_boost
        return boost

    def search(self, query: str, *, k: int = 10,
               where: Optional[dict[str, Any]] = None) -> list[tuple[int, float]]:
        """Return ``(document_index, score)`` pairs, best first.

        Filtering happens *before* ranking so that ``k`` results means ``k``
        results, rather than "k candidates of which four failed the filter".
        """
        if not self._n:
            return []
        from .vectorstore import _matches  # shared filter grammar with the vector store

        terms = tokenize(query)
        if not terms:
            return []

        scores: list[tuple[int, float]] = []
        for idx, freqs in enumerate(self._doc_freqs):
            if where and not _matches(self.documents[idx].metadata, where):
                continue
            length = self._doc_lengths[idx] or 1
            score = 0.0
            for term in terms:
                tf = freqs.get(term)
                if not tf:
                    continue
                idf = self.idf(term)
                denom = tf + self.k1 * (1 - self.b + self.b * length / (self._avgdl or 1))
                score += idf * (tf * (self.k1 + 1)) / denom * self._field_boost(idx, term)
            if score > 0:
                scores.append((idx, score))

        scores.sort(key=lambda pair: pair[1], reverse=True)
        return scores[:k]

    # ------------------------------------------------------------------
    @classmethod
    def from_chunks(cls, chunks: Iterable[Chunk], **kwargs) -> "BM25Index":
        return cls([BM25Document.from_chunk(c) for c in chunks], **kwargs)

    @classmethod
    def from_standards(cls, standards: Iterable[Standard], **kwargs) -> "BM25Index":
        return cls([BM25Document.from_standard(s) for s in standards], **kwargs)


def rank_bm25_hits(index: SearchIndex, query: str, *, k: int = 10,
                   current_only: bool = True) -> list[tuple[int, float]]:
    """Run the repo's existing TF-IDF index and return ``(doc_index, score)``.

    Wraps :meth:`SearchIndex.search` so the hybrid fuser can treat the pre-built
    TF-IDF index and this module's BM25 identically. ``min_score`` is dropped to
    zero here on purpose: the caller fuses ranks, and discarding a retriever's
    weak-but-present candidates before fusion loses recall that RRF is designed
    to recover from the other ranker.
    """
    hits = index.search(query, k=k, current_only=current_only, min_score=0.0)
    by_canonical = {doc.get("canonical"): i for i, doc in enumerate(index.docs)}
    out: list[tuple[int, float]] = []
    for hit in hits:
        idx = by_canonical.get(hit.canonical)
        if idx is not None:
            out.append((idx, float(hit.score)))
    return out
