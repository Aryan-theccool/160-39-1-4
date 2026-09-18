"""Hybrid retrieval: BM25 + the pre-built TF-IDF + dense, fused with RRF. Part 3.

The pipeline
------------
::

    query --> QueryProcessor --> filters + retrieval text
              |
              +--> BM25 over chunks ..................\
              +--> TF-IDF over standards (prebuilt) ...+--> RRF fuse --> rerank --> diversity
              +--> dense over vector store ............/                        --> top_k

Why reciprocal rank fusion
--------------------------
The three retrievers produce scores on incomparable scales: BM25 is unbounded,
TF-IDF cosine is in ``[0, 1]``, a cross-encoder is a logit. Normalising them to
compare directly requires a calibration constant per retriever that has to be
retuned whenever the corpus changes, and which fails silently when it drifts.

RRF sidesteps this by fusing *ranks* rather than scores::

    score(d) = sum over retrievers r of  weight_r / (k + rank_r(d))

``k=60`` is the value from the original TREC work and is what everyone else's
implementations use, so results are comparable between systems. The property
that matters: a document returned by all three retrievers outranks one that is
rank 1 in a single retriever. That is exactly the behaviour you want when
retrievers disagree -- agreement is evidence.

Every result carries its provenance (which retrievers found it and at what
rank). Retrieval you cannot debug is retrieval you cannot improve, and in a
demo the "why did this come back" answer is often more interesting than the
score.

Reranking
---------
``st:<model>`` uses a real cross-encoder, which is the only component that sees
query and passage *together* and therefore the only one that can catch negation
and specificity. Without sentence-transformers installed, a lexical reranker
runs instead -- query-term coverage, title overlap, and an exact-designation
match. It is honestly labelled as not a cross-encoder, in the API response and
in the logs, because presenting it as one would be a lie a reader could not
detect from the output.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence

from bis_pipeline.index import tokenize
from bis_pipeline.iscode import yearless_key

from .bm25 import BM25Document, BM25Index
from .data import BisData
from .embeddings import Embedder, get_embedder
from .query_processor import Intent, ProcessedQuery
from .schema import Chunk
from .vectorstore import COLLECTION_FOR, VectorStore, open_store

log = logging.getLogger(__name__)

__all__ = [
    "Candidate", "SearchResult", "SearchResponse", "RetrievalConfig",
    "HybridSearch", "RRF_K",
]

#: Standard RRF constant. Lower values weight the top few ranks harder.
RRF_K = 60

DEFAULT_STORE_DIRNAME = "vector_store"


def _timings(clock: Optional["_Stopwatch"], started: float) -> dict[str, float]:
    """Close a stopwatch against the wall clock the search started at."""
    if clock is None:
        return {}
    clock.add("total", (time.perf_counter() - started) * 1000.0)
    return clock.stop("")


class _Stopwatch:
    """Accumulating per-stage timer.

    ``lap`` adds to whatever is already recorded for a stage, so a stage that
    runs twice (the sparse leg covers BM25 *and* TF-IDF; each per-standard and
    per-chunk call is separate) reports its true total rather than the last
    fragment. Overlapping starts are not supported -- stages are sequential.
    """

    __slots__ = ("_marks", "_open", "_totals")

    def __init__(self) -> None:
        self._totals: dict[str, float] = {}
        self._open: Optional[tuple[str, float]] = None

    def start(self, stage: str) -> None:
        """Begin timing `stage` from now."""
        self._open = (stage, time.perf_counter())

    def lap(self, stage: str) -> None:
        """Close the stage opened by `start`, adding to its total."""
        if self._open is None or self._open[0] != stage:
            return
        _, started = self._open
        self.add(stage, (time.perf_counter() - started) * 1000.0)
        self._open = None

    def add(self, stage: str, milliseconds: float) -> None:
        """Record a duration measured elsewhere."""
        self._totals[stage] = self._totals.get(stage, 0.0) + milliseconds

    def stop(self, stage: str = "") -> dict[str, float]:
        """Close `stage` and return every stage so far, rounded."""
        if stage:
            self.lap(stage)
        return {k: round(v, 3) for k, v in self._totals.items()}


#: How a search treats withdrawn editions. See ``HybridSearch._mode_for``.
#:   recommend -> withheld from the ranked results, returned separately
#:   search    -> may appear, but only below the current edition, with replacement
#:   history   -> the user asked for the old edition; nothing is filtered
VALID_MODES = frozenset({"recommend", "search", "history"})


@dataclass
class Candidate:
    """One item as produced by a single retriever, before fusion."""

    id: str
    text: str
    metadata: dict[str, Any]
    score: float
    retriever: str
    rank: int = 0
    collection: str = ""

    @property
    def designation(self) -> str:
        return str(self.metadata.get("designation") or self.metadata.get("canonical") or "")

    @property
    def canonical(self) -> str:
        return str(self.metadata.get("standard_id") or self.metadata.get("canonical") or "")

    @property
    def is_current(self) -> bool:
        value = self.metadata.get("is_current", True)
        return bool(value) if isinstance(value, bool) else str(value).lower() == "true"


@dataclass
class SearchResult:
    """A fused, reranked result."""

    id: str
    text: str
    metadata: dict[str, Any]
    score: float
    #: retriever name -> rank (1-based).
    provenance: dict[str, int] = field(default_factory=dict)
    rerank_score: Optional[float] = None
    collection: str = ""

    @property
    def designation(self) -> str:
        return str(self.metadata.get("designation") or self.metadata.get("canonical") or "")

    @property
    def canonical(self) -> str:
        return str(self.metadata.get("standard_id") or self.metadata.get("canonical") or "")

    @property
    def title(self) -> str:
        return str(self.metadata.get("title") or "")

    @property
    def division(self) -> str:
        return str(self.metadata.get("division") or "")

    @property
    def year(self) -> Optional[int]:
        year = self.metadata.get("year")
        return int(year) if isinstance(year, (int, float)) and year and year > 0 else None

    @property
    def is_current(self) -> bool:
        value = self.metadata.get("is_current", True)
        return bool(value) if isinstance(value, bool) else str(value).lower() == "true"

    def as_dict(self, *, text_chars: int = 600) -> dict[str, Any]:
        return {
            "id": self.id,
            "designation": self.designation,
            "title": self.title,
            "division": self.division,
            "year": self.year,
            "is_current": self.is_current,
            "score": round(self.score, 5),
            "rerank_score": (round(self.rerank_score, 4)
                             if self.rerank_score is not None else None),
            "found_by": self.provenance,
            "collection": self.collection,
            "archive_url": self.metadata.get("archive_url", ""),
            # Without this, a caller sees `is_current: false` and no way to say
            # what replaced it -- which is the difference between "this standard
            # is old" and "use this one instead". The API surfaces it directly,
            # so dropping it here silently undid the supersession policy's
            # promise to hand back replacement metadata.
            "superseded_by": self.metadata.get("superseded_by") or "",
            "text": " ".join(self.text.split())[:text_chars],
        }


@dataclass
class SearchResponse:
    query: ProcessedQuery
    results: list[SearchResult] = field(default_factory=list)
    #: Populated when a superseded edition was retrieved -- the caller must
    #: surface this, not bury it.
    supersession_warnings: list[dict[str, Any]] = field(default_factory=list)
    reranker: str = ""
    notes: list[str] = field(default_factory=list)
    #: ``recommend`` | ``search`` | ``history`` -- see :meth:`HybridSearch.search`.
    mode: str = "search"
    #: IDF-weighted share of the query's keywords found in the best candidate.
    #: -1.0 when not computed. Reported for diagnosis; not a confidence score.
    query_coverage: float = -1.0
    #: Per-stage milliseconds. Empty when ``RetrievalConfig.instrument`` is off.
    #: Keys: query_processing, sparse, dense, fusion, rerank, total. The stages
    #: are measured where they happen rather than reconstructed from the total,
    #: so "the dense leg is the slow one" is an observation and not a guess.
    timings: dict[str, float] = field(default_factory=dict)
    #: Withdrawn editions held back from the ranked recommendations in
    #: ``recommend`` mode, each carrying ``superseded_by``. They are still
    #: returned, because a user who is about to buy against a standard is better
    #: served by seeing "IS 269:1989, replaced by IS 269:2015" than by silence.
    #: They are *not* in ``results``, which is what the recommender ranks.
    superseded: list["SearchResult"] = field(default_factory=list)

    def as_dict(self, *, text_chars: int = 600) -> dict[str, Any]:
        return {
            "query": self.query.raw,
            "intent": str(self.query.intent),
            "mode": self.mode,
            "query_coverage": (round(self.query_coverage, 4)
                               if self.query_coverage >= 0 else None),
            "timings_ms": self.timings,
            "filter": self.query.where(),
            "reranker": self.reranker,
            "notes": self.notes,
            "superseded_alternatives": [r.as_dict(text_chars=text_chars)
                                        for r in self.superseded],
            "supersession_warnings": self.supersession_warnings,
            "results": [r.as_dict(text_chars=text_chars) for r in self.results],
        }


@dataclass
class RetrievalConfig:
    top_k: int = 8
    candidates_per_retriever: int = 50
    rrf_k: int = RRF_K
    #: How many passages from the same standard may appear. Without a cap, the
    #: four chunks of IS 10500 fill the context window and the generator never
    #: sees the other standards the user needs.
    max_per_standard: int = 3
    weights: dict[str, float] = field(default_factory=lambda: {
        "bm25": 1.0, "tfidf": 0.8, "dense": 1.2,
    })
    use_bm25: bool = True
    use_tfidf: bool = True
    use_dense: bool = True
    rerank: bool = True
    #: ``rrf`` (reciprocal rank fusion) or ``score`` (weighted, normalised
    #: scores). RRF is the default because it needs no calibration across
    #: retrievers whose scores are not comparable -- a BM25 score of 14 and a
    #: cosine of 0.72 have no common scale. The ablation runs both, because
    #: "which fusion" is an empirical question and the answer is corpus-specific.
    fusion: str = "rrf"
    #: Record per-stage milliseconds on every SearchResponse. On by default:
    #: the timings are what makes a latency claim checkable, and the cost is a
    #: handful of `perf_counter` calls.
    instrument: bool = True
    rerank_candidates: int = 30
    #: Nudge current editions above superseded ones when both are in play.
    #: Only bites when the query did *not* filter to current-only (compliance
    #: and supersession questions), which is exactly when ranking a withdrawn
    #: 1989 edition first would be misleading. Applies to ranking, never to
    #: filtering: superseded editions stay retrievable.
    prefer_current: bool = True
    current_bonus: float = 1.15
    #: Optional floor on IDF-weighted keyword coverage (see
    #: `HybridSearch._query_coverage`). **Off by default, and that default is a
    #: measured decision, not caution.**
    #:
    #: Over the evaluation set the worst out-of-scope query reaches 0.142 and
    #: every answerable case but one reaches at least 0.159, so 0.15 declines
    #: all twelve out-of-scope queries and keeps nine of ten answerable ones.
    #: Tempting -- and wrong: it was fitted to 22 cases. The same floor declines
    #: "Is cement covered under mandatory BIS certification?", a legitimate
    #: compliance question that shares one word with the right standard and
    #: four with the vocabulary of compliance itself. A threshold that cannot
    #: tell that apart from "who won the 2011 cricket world cup" is not
    #: measuring relevance, it is measuring how many of the query's words happen
    #: to be in one short document. Re-measure on the real 197-standard corpus
    #: before turning this on.
    min_query_coverage: float = 0.0
    #: Cosine floor for the TF-IDF leg. The underlying index defaults to 0.05
    #: for the same reason the dense leg has a floor: cosine over TF-IDF is
    #: never exactly zero for a large corpus, so without this a nonsense query
    #: gets ranked "least unrelated" documents and looks like a real answer.
    #: Measured with the out-of-scope cases in the evaluation set.
    min_tfidf_score: float = 0.05
    #: Cosine floor for the dense leg. Reciprocal rank fusion fuses *ranks*, so
    #: it has no way to notice that every candidate was equally irrelevant: a
    #: nonsense query still gets ranks 1..n and therefore a confident-looking
    #: answer list. This prunes the obviously-unrelated before ranking.
    #: Raise it for a semantic model (BGE puts unrelated pairs around 0.3);
    #: lower it for the hashing embedder (lexical overlap, near 0 when unrelated).
    min_dense_similarity: float = 0.15


# ----------------------------------------------------------------------
# rerankers
# ----------------------------------------------------------------------
class Reranker(Protocol):
    name: str
    is_cross_encoder: bool

    def score(self, query: str, candidates: Sequence[SearchResult]) -> list[float]: ...


class LexicalReranker:
    """Query-term coverage + field overlap. Not a cross-encoder.

    Scores three cheap signals that a bag-of-words retriever cannot express:

    * **coverage** -- what fraction of the query's content words appear in the
      passage. Favours passages that answer the whole question over ones that
      match one rare word hard;
    * **specificity** -- an IS designation typed by the user, found verbatim in
      the passage or its metadata;
    * **title agreement** -- overlap with the standard's title, which is the
      single most reliable relevance signal in a standards corpus.

    ``is_cross_encoder = False`` is carried into every API response so a client
    can tell which reranker produced the ranking.
    """

    name = "lexical (coverage + designation)"
    is_cross_encoder = False

    def __init__(self, *, designation_boost: float = 2.5, title_boost: float = 1.5):
        self.designation_boost = designation_boost
        self.title_boost = title_boost

    def score(self, query: str, candidates: Sequence[SearchResult]) -> list[float]:
        from bis_pipeline.index import tokenize

        query_terms = [t for t in dict.fromkeys(tokenize(query)) if len(t) > 2]
        if not query_terms:
            return [0.0] * len(candidates)
        query_set = set(query_terms)

        out: list[float] = []
        for candidate in candidates:
            passage = set(tokenize(candidate.text)) | set(tokenize(candidate.title))
            covered = len(query_set & passage)
            score = covered / len(query_set) if query_set else 0.0

            designation_terms = {t for t in query_terms if re.fullmatch(r"is\d+|is\d+\.\d+", t)}
            if designation_terms & passage:
                score += self.designation_boost

            title_terms = {t for t in query_terms if t in set(tokenize(candidate.title))}
            if title_terms:
                score += self.title_boost * len(title_terms) / len(query_set)
            out.append(score)
        return out


class CrossEncoderReranker:
    """``sentence-transformers`` CrossEncoder over (query, passage) pairs.

    The one component that reads both texts jointly, and thus the only one that
    can tell "reinforced concrete" from "prestressed concrete" when the query
    says "reinforced". Loads lazily; construction fails if the model is absent.
    """

    name = "cross-encoder"
    is_cross_encoder = True

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "sentence-transformers not installed; use the lexical reranker "
                "or install the dense extra"
            ) from exc
        log.info("loading cross-encoder %s", model_name)
        self.model = CrossEncoder(model_name)
        self.name = f"cross-encoder:{model_name}"

    def score(self, query: str, candidates: Sequence[SearchResult]) -> list[float]:
        pairs = [(query, f"{c.designation} {c.title}\n{c.text}") for c in candidates]
        if not pairs:
            return []
        return [float(s) for s in self.model.predict(pairs, show_progress_bar=False)]


def default_reranker(spec: Optional[str] = None) -> Reranker:
    """``--reranker auto`` picks the cross-encoder when it is installed."""
    if spec in (None, "auto"):
        try:
            return CrossEncoderReranker()
        except Exception as exc:
            log.info("cross-encoder unavailable (%s); using lexical reranker", exc)
            return LexicalReranker()
    if spec == "none":
        return LexicalReranker()  # identity is handled by the caller
    if spec == "lexical":
        return LexicalReranker()
    if spec.startswith("st:") or spec.startswith("cross-encoder"):
        return CrossEncoderReranker(spec[3:] if spec.startswith("st:") else spec)
    return LexicalReranker()


# ----------------------------------------------------------------------
# the thing itself
# ----------------------------------------------------------------------
class HybridSearch:
    """Owns the retrievers and the fusion. Load once, query many times."""

    def __init__(self, data: BisData, *, store_dir: Optional[str] = None,
                 embedder: Optional[Embedder | str] = None,
                 config: Optional[RetrievalConfig] = None,
                 reranker: Optional[Reranker | str] = None,
                 backend: str = "auto"):
        self.data = data
        self.config = config or RetrievalConfig()

        if isinstance(embedder, str) or embedder is None:
            embedder = get_embedder(embedder)
        self.embedder: Embedder = embedder

        if store_dir is None:
            self.store_dir = data.root / DEFAULT_STORE_DIRNAME
        else:
            candidate = Path(store_dir)
            # A relative path is taken relative to the data directory, so
            # `--store-dir vector_store` means "inside bis_data", not "inside
            # whatever directory the process happens to have been started in".
            self.store_dir = candidate if candidate.is_absolute() else data.root / candidate
        self._backend = backend
        self._stores: dict[str, VectorStore] = {}
        self._chunk_index: Optional[BM25Index] = None
        self._standard_index: Optional[BM25Index] = None
        self._chunk_docs: list[BM25Document] = []
        self._standard_docs: list[BM25Document] = []
        self._chunks_cache: Optional[list[Chunk]] = None
        #: designation/canonical -> year, filled on first TF-IDF search.
        self._year_by_key: Optional[dict[str, int]] = None
        #: counts TF-IDF candidates dropped for having no year, per search.
        self._tfidf_unknown_year: int = 0
        #: canonical -> replacement designation, filled on first use.
        self._replacements: Optional[dict[str, str]] = None

        if reranker is None or isinstance(reranker, str):
            self.reranker: Optional[Reranker] = default_reranker(reranker)
        else:
            self.reranker = reranker

    # ------------------------------------------------------------------
    # lazy components
    # ------------------------------------------------------------------
    def _query_coverage(self, processed: ProcessedQuery,
                        candidates: Sequence[Candidate]) -> float:
        """IDF-weighted share of the query's keywords the best candidate contains.

        Weighting by IDF is what makes this comparable across queries. An
        unweighted count would treat "india" in a nonsense query as being as
        informative as "luminaire" in a real one; the corpus's own document
        frequencies say otherwise. Returns 1.0 when there is nothing to measure
        against, so an unmeasurable query is never silently declined.
        """
        keywords = [k for k in processed.keywords if k]
        if not keywords or not candidates:
            return 1.0
        index = self.standard_index()
        tokens = {c.id: set(tokenize(c.text)) for c in candidates}
        total = 0.0
        for keyword in keywords:
            stems = tokenize(keyword)
            if not stems:
                continue
            total += max(index.idf(t) for t in stems)
        if total <= 0:
            return 1.0
        best = 0.0
        for candidate in candidates:
            document = tokens[candidate.id]
            hit = 0.0
            for keyword in keywords:
                stems = tokenize(keyword)
                if not stems:
                    continue
                if any(t in document for t in stems):
                    hit += max(index.idf(t) for t in stems)
            best = max(best, hit / total)
        return best

    def _year_lookup(self) -> dict[str, int]:
        """canonical id and designation -> year, built once per search object."""
        if self._year_by_key is None:
            lookup: dict[str, int] = {}
            for standard in self.data.standards():
                if not getattr(standard, "year", None):
                    continue
                year = int(standard.year)
                if standard.canonical:
                    lookup[standard.canonical] = year
                if standard.designation:
                    lookup[standard.designation] = year
            self._year_by_key = lookup
        return self._year_by_key

    def _store(self, level: str) -> Optional[VectorStore]:
        """Open the vector collection backing a retrieval level.

        ``level`` is the retrieval level (``chunks`` / ``standards``); the
        on-disk collection name comes from :data:`~bis_rag.vectorstore.COLLECTION_FOR`
        so the two can never drift apart.
        """
        if level in self._stores:
            return self._stores[level]
        collection = COLLECTION_FOR.get(level, level)
        try:
            store = open_store(self.store_dir, collection, backend=self._backend,
                               fingerprint=self.embedder.fingerprint,
                               embedder_name=self.embedder.name,
                               dim=self.embedder.dim, create=False)
        except Exception as exc:
            log.info("no vector store for %s/%s (%s); dense retrieval disabled",
                     level, collection, exc)
            self._stores[level] = None  # type: ignore[assignment]
            return None
        # Refuse to serve from a store built by a different embedder.
        store.assert_compatible(self.embedder)
        self._stores[level] = store
        return store

    def _chunks(self) -> list[Chunk]:
        if self._chunks_cache is None:
            self._chunks_cache = self.data.chunks()
        return self._chunks_cache

    def chunk_index(self) -> BM25Index:
        if self._chunk_index is None:
            self._chunk_docs = [BM25Document.from_chunk(c) for c in self._chunks()]
            self._chunk_index = BM25Index(self._chunk_docs)
            log.info("BM25 chunk index: %d documents", len(self._chunk_index))
        return self._chunk_index

    def standard_index(self) -> BM25Index:
        if self._standard_index is None:
            self._standard_docs = [BM25Document.from_standard(s) for s in self.data.standards()]
            self._standard_index = BM25Index(self._standard_docs)
            log.info("BM25 standard index: %d documents", len(self._standard_index))
        return self._standard_index

    # ------------------------------------------------------------------
    # retriever adapters, all returning Candidate
    # ------------------------------------------------------------------
    def _bm25(self, level: str, q: ProcessedQuery, k: int,
              where: Optional[dict]) -> list[Candidate]:
        if level == "chunks":
            index = self.chunk_index()
            docs = self._chunk_docs
        else:
            index = self.standard_index()
            docs = self._standard_docs
        out: list[Candidate] = []
        # Unexpanded query: BM25 is an exact-ish term matcher, and injecting
        # synonym terms here changes term frequencies rather than merely adding
        # recall. Expansions are fed to the dense leg, which is approximate
        # anyway and benefits from them.
        for rank, (doc_idx, score) in enumerate(index.search(q.search_text, k=k, where=where),
                                                 start=1):
            doc = docs[doc_idx]
            out.append(Candidate(id=doc.id, text=doc.text, metadata=doc.metadata,
                                 score=float(score), retriever=f"bm25:{level}", rank=rank,
                                 collection=level))
        return out

    def _tfidf(self, q: ProcessedQuery, k: int,
               where: Optional[dict]) -> list[Candidate]:
        """The standards-level TF-IDF index that already exists in bis_data.

        Falls back to BM25 when ``index/search_index.json`` is absent, so a
        data directory built by only ``create_rag_dataset.py`` still works.
        """
        index = self.data.tfidf_index()
        if index is None:
            return []
        from .vectorstore import _matches

        hits = index.search(q.search_text, k=k * 3, current_only=False,
                            min_score=self.config.min_tfidf_score)
        out: list[Candidate] = []
        for hit in hits:
            year = self._year_for(hit)
            meta = {
                "canonical": hit.canonical,
                "designation": hit.designation,
                "title": hit.title,
                "is_current": hit.is_current,
                "status": hit.status,
                "archive_url": hit.archive_url,
                "year": year,
            }
            if where and not _matches(meta, where):
                # Two different reasons to drop a candidate, and conflating
                # them hid a bug for a long time. `year: -1` used to be written
                # here as a placeholder, so every TF-IDF candidate failed a
                # `$gte` year filter (silently losing a whole retriever) and
                # *passed* a `$lte` one (offering a 2015 standard as a 1980s
                # edition). An unknown year is now None, which fails both.
                if year is None and self._year_filtered(where):
                    self._tfidf_unknown_year += 1
                continue
            out.append(Candidate(id=hit.canonical or hit.designation, text=hit.snippet,
                                 metadata=meta, score=float(hit.score),
                                 retriever="tfidf:standards",
                                 rank=len(out) + 1, collection="standards"))
            if len(out) >= k:
                break
        return out

    def _year_for(self, hit: Any) -> Optional[int]:
        """The real publication year, from the index or from bis_data.

        The index carries it only if it was built by a version that records it.
        The standards themselves always carry it, so a corpus scraped by an
        older build still answers year filters correctly -- which matters,
        because rebuilding is the user's call, not ours.
        """
        year = getattr(hit, "year", None)
        if isinstance(year, (int, float)) and year:
            return int(year)
        lookup = self._year_lookup()
        for key in (getattr(hit, "canonical", ""), getattr(hit, "designation", "")):
            if key and key in lookup:
                return lookup[key]
        return None

    @staticmethod
    def _year_filtered(where: Optional[dict]) -> bool:
        """Whether a metadata filter constrains the year at all."""
        def walk(node: Any) -> bool:
            if not isinstance(node, dict):
                return False
            for key, value in node.items():
                if key in ("$and", "$or"):
                    if isinstance(value, (list, tuple)) and any(walk(c) for c in value):
                        return True
                    continue
                if key == "year":
                    return True
            return False

        return walk(where)

    def _dense(self, level: str, q: ProcessedQuery, k: int,
               where: Optional[dict]) -> list[Candidate]:
        store = self._store(level)
        if store is None:
            return []
        vector = self.embedder.encode_one(q.retrieval_text, is_query=True)
        out: list[Candidate] = []
        for hit in store.query(vector, n_results=k, where=where):
            if hit.score < self.config.min_dense_similarity:
                # Ranked below the floor: the store is returning "least
                # unrelated" rather than "related".
                continue
            out.append(Candidate(id=hit.id, text=hit.text, metadata=hit.metadata,
                                 score=float(hit.score), retriever=f"dense:{level}",
                                 rank=len(out) + 1, collection=level))
        return out

    # ------------------------------------------------------------------
    # fusion
    # ------------------------------------------------------------------
    def _fuse(self, candidate_lists: Sequence[Sequence[Candidate]]) -> list[SearchResult]:
        """Fuse per-retriever candidate lists into one ranked list."""
        if self.config.fusion == "score":
            return self._fuse_by_score(candidate_lists)
        return self._fuse_by_rank(candidate_lists)

    def _fuse_by_score(self, candidate_lists: Sequence[Sequence[Candidate]]) -> list[SearchResult]:
        """Weighted fusion of min-max normalised scores.

        Each retriever's scores are normalised *within its own list*, so the
        best hit from every leg starts from 1.0. Without that, whichever leg
        happens to emit the largest numbers wins by arithmetic rather than by
        relevance -- BM25 scores are unbounded and cosine sits in [0, 1].
        """
        fused: dict[str, SearchResult] = {}
        for candidates in candidate_lists:
            if not candidates:
                continue
            scores = [c.score for c in candidates]
            low, high = min(scores), max(scores)
            span = (high - low) or 1.0
            for candidate in candidates:
                weight = self.config.weights.get(candidate.retriever.split(":")[0], 1.0)
                normalised = (candidate.score - low) / span
                contribution = weight * normalised
                if self.config.prefer_current and candidate.is_current:
                    contribution *= self.config.current_bonus
                existing = fused.get(candidate.id)
                if existing is None:
                    fused[candidate.id] = SearchResult(
                        id=candidate.id,
                        text=candidate.text,
                        metadata=dict(candidate.metadata),
                        score=contribution,
                        provenance={candidate.retriever: candidate.rank},
                        collection=candidate.collection,
                    )
                else:
                    existing.score += contribution
                    existing.provenance[candidate.retriever] = candidate.rank
                    if len(candidate.text) > len(existing.text):
                        existing.text = candidate.text
                        existing.metadata.update(candidate.metadata)
        return sorted(fused.values(), key=lambda r: r.score, reverse=True)

    def _fuse_by_rank(self, candidate_lists: Sequence[Sequence[Candidate]]) -> list[SearchResult]:
        """Reciprocal rank fusion, one entry per id, provenance preserved."""
        fused: dict[str, SearchResult] = {}
        for candidates in candidate_lists:
            for candidate in candidates:
                weight = self.config.weights.get(candidate.retriever.split(":")[0], 1.0)
                contribution = weight / (self.config.rrf_k + max(1, candidate.rank))
                if self.config.prefer_current and candidate.is_current:
                    contribution *= self.config.current_bonus
                existing = fused.get(candidate.id)
                if existing is None:
                    fused[candidate.id] = SearchResult(
                        id=candidate.id,
                        text=candidate.text,
                        metadata=dict(candidate.metadata),
                        score=contribution,
                        provenance={candidate.retriever: candidate.rank},
                        collection=candidate.collection,
                    )
                else:
                    existing.score += contribution
                    existing.provenance[candidate.retriever] = candidate.rank
                    # Prefer the richer text: a chunk body beats a TF-IDF snippet.
                    if len(candidate.text) > len(existing.text):
                        existing.text = candidate.text
                        existing.metadata.update(candidate.metadata)
        return sorted(fused.values(), key=lambda r: r.score, reverse=True)

    @staticmethod
    def _current_edition_first(results: Sequence[SearchResult]) -> list[SearchResult]:
        """Within one standard, the current edition must not sit below a withdrawn one.

        Found by the retrieval evaluator, not by a user report: for an aggregates
        query, IS 456:1978 came back at rank 5 and IS 456:2000 at rank 7. Nobody
        reading a result list scrolls past the fifth entry to check, so the
        withdrawn edition was, in practice, the answer.

        Deliberately narrow. Each withdrawn edition that precedes its own current
        edition is swapped with that current edition, and **nothing else moves**,
        so the relevance order the fusion and reranker computed survives
        everywhere it is not actively wrong. Hoisting every current edition to
        the top -- which the compliance path does, and which is right there with
        its much smaller candidate set -- would rearrange unrelated standards
        here and throw away that work.

        An earlier version swapped only *adjacent* pairs, on the assumption that
        two editions of one standard come back next to each other. They do not:
        an unrelated standard was sitting between IS 456:1978 at rank 5 and
        IS 456:2000 at rank 7, and the fix silently did nothing. The test that
        caught it is `test_evaluate_reports_the_supersession_check_against_the_real_ranking`.

        O(n) with a dict of first-current positions, and n is the result limit.
        """
        ordered = list(results)

        first_current: dict[str, int] = {}
        for index, item in enumerate(ordered):
            key = yearless_key(item.designation)
            if item.is_current and key:
                first_current.setdefault(key, index)

        for index in range(len(ordered)):
            item = ordered[index]
            if item.is_current:
                continue
            key = yearless_key(item.designation)
            current_at = first_current.get(key)
            if current_at is None or current_at < index:
                continue
            # Put the current edition where the withdrawn one was, and the
            # withdrawn one where the current one was. One swap, two items moved.
            ordered[index], ordered[current_at] = ordered[current_at], ordered[index]
            first_current[key] = index

        return ordered

    def _diversify(self, results: Sequence[SearchResult], *, limit: int,
                   max_per_standard: int) -> list[SearchResult]:
        """Cap how many passages one standard may contribute.

        The cap is hard: if only two standards are relevant, this returns
        passages from two standards and stops, rather than padding the list with
        five more chunks of the same one. Fewer, distinct results are more
        useful than a longer list that looks like a bug -- and for the RAG
        context, three passages saying the same thing waste the window.
        """
        if max_per_standard <= 0:
            return list(results[:limit])
        counts: dict[str, int] = {}
        out: list[SearchResult] = []
        for result in results:
            key = result.canonical or result.designation or result.id
            if counts.get(key, 0) >= max_per_standard:
                continue
            counts[key] = counts.get(key, 0) + 1
            out.append(result)
            if len(out) >= limit:
                break
        return out

    def _replacement_map(self) -> dict[str, str]:
        """canonical id -> designation that replaces it, from the standards."""
        if self._replacements is None:
            self._replacements = {
                std.canonical: std.superseded_by
                for std in self.data.standards()
                if std.superseded_by
            }
        return self._replacements

    def with_replacement_metadata(self, results: Sequence[SearchResult]) -> list[SearchResult]:
        """Stamp ``superseded_by`` onto every withdrawn edition in ``results``.

        The vector collections do not store it (see the chunk field coverage in
        `doctor`: `status` is 0%), so a withdrawn edition arrives looking like
        any other result. "Superseded with no replacement named" is not a usable
        answer, and the rule for search mode is that exposure is only acceptable
        *with* the replacement, so the mapping is resolved here.
        """
        replacements = self._replacement_map()
        for result in results:
            if result.is_current:
                continue
            if result.metadata.get("superseded_by"):
                continue
            replacement = replacements.get(result.canonical, "")
            if not replacement:
                info = self.data.supersession(result.canonical)
                replacement = info.replacement_designation if info else ""
            if replacement:
                result.metadata["superseded_by"] = replacement
        return list(results)

    def _annotate_supersession(self, results: Sequence[SearchResult]) -> list[dict]:
        warnings: list[dict] = []
        seen: set[str] = set()
        for result in results:
            canonical = result.canonical
            if not canonical or canonical in seen:
                continue
            if result.is_current:
                continue
            seen.add(canonical)
            info = self.data.supersession(canonical)
            if info is None:
                continue
            warnings.append({
                "designation": info.designation,
                "superseded_by": info.replacement_designation,
                "replacement_in_dataset": info.in_dataset,
                "message": (
                    f"{info.designation} is superseded by {info.replacement_designation}. "
                    + ("Use the newer edition." if info.in_dataset else
                       "The newer edition is not in this dataset (197 of ~22,025 standards "
                       "are held); point the user at it rather than relying on the old text.")
                ),
            })
        return warnings

    # ------------------------------------------------------------------
    # public search
    # ------------------------------------------------------------------
    def process(self, query: str) -> ProcessedQuery:
        """Run the query processor on its own.

        Exposed because the filters are a *processor* decision, and a caller
        that wants to inspect or override them -- the evaluator turns
        `current_only` off to measure the ranking rather than the filter -- has
        no other way to reach them.
        """
        return self._processor().process(query)

    def _mode_for(self, request: Optional[str], processed: ProcessedQuery) -> str:
        """Decide how superseded editions may appear, from intent unless told.

        Three modes, because "may a withdrawn edition be shown?" has three
        different right answers:

        ``recommend``
            The user is being told what to buy, comply with or cite. A withdrawn
            edition must not be in the ranked recommendations at all -- someone
            who acts on IS 269:1989 is buying against a standard that no longer
            exists. They are returned separately, with their replacement named.
        ``search``
            The user is browsing. A withdrawn edition may appear, but never
            above its own current edition, and never without the replacement.
        ``history``
            The user asked about an old edition specifically ("has IS 456:1978
            been superseded?"). It belongs at the top and nothing is filtered.
        """
        if request:
            if request not in VALID_MODES:
                raise ValueError(f"unknown search mode {request!r}; expected one of "
                                 f"{', '.join(sorted(VALID_MODES))}")
            return request
        if processed.intent == Intent.SUPERSESSION:
            return "history"
        if processed.intent in (Intent.COMPLIANCE, Intent.LATEST, Intent.LIST_BY_DOMAIN):
            return "recommend"
        return "search"

    def search(self, query: str | ProcessedQuery, *, top_k: Optional[int] = None,
               max_per_standard: Optional[int] = None,
               rerank: Optional[bool] = None,
               mode: Optional[str] = None) -> SearchResponse:
        """Route by intent, retrieve, fuse, rerank, annotate.

        ``mode`` overrides the intent-derived supersession policy; see
        :meth:`_mode_for`.
        """
        config = self.config
        clock = _Stopwatch() if config.instrument else None
        # Query understanding (parse, designation extraction, filter building,
        # ontology expansion) happens before any retriever runs, so it is timed
        # here rather than through a stopwatch stage -- and it is not free: on a
        # cold process it builds the facet and ontology indices.
        search_started = time.perf_counter()
        processed = query if isinstance(query, ProcessedQuery) else \
            self._processor().process(query)
        if clock:
            clock.add("query_processing",
                      (time.perf_counter() - search_started) * 1000.0)
        limit = top_k or config.top_k
        per_standard = config.max_per_standard if max_per_standard is None else max_per_standard
        do_rerank = config.rerank if rerank is None else rerank
        search_mode = self._mode_for(mode, processed)
        where = processed.where()
        k = max(config.candidates_per_retriever, limit * 4)
        # Per-search counters for the TF-IDF leg, reported as notes below.
        self._tfidf_unknown_year = 0

        notes: list[str] = list(processed.notes)
        if (config.use_dense and self.embedder is not None
                and self._store("chunks") is None and self._store("standards") is None):
            notes.append(
                f"no vector store found at {self.store_dir}: results come from BM25 and "
                f"the TF-IDF index only, so semantic (dense) retrieval is inactive. "
                f"Run `bis-rag build` to enable it."
            )

        # Exact designation lookup short-circuits semantic search entirely: if a
        # user types "IS 1239", rank 1 must be IS 1239, not "a standard that
        # mentions steel pipes a lot".
        exact = self._exact_matches(processed)
        if exact:
            notes.append(f"{len(exact)} exact designation match(es) promoted to the top")

        standard_lists: list[Sequence[Candidate]] = []
        chunk_lists: list[Sequence[Candidate]] = []

        standards_first = processed.intent in (
            Intent.LOOKUP, Intent.COMPLIANCE, Intent.SUPERSESSION, Intent.LATEST,
            Intent.LIST_BY_DOMAIN)

        # Sparse (BM25 + TF-IDF) and dense are timed separately: they are the
        # two legs whose cost actually varies, and an ablation that reports one
        # "retrieval" number cannot say which of them to drop.
        if config.use_bm25:
            if clock:
                clock.start("sparse")
            standard_lists.append(self._bm25("standards", processed, k, where))
            chunk_lists.append(self._bm25("chunks", processed, k, where))
            if clock:
                clock.lap("sparse")
        elif clock:
            clock.start("sparse")
            clock.lap("sparse")
        if config.use_tfidf:
            if clock:
                clock.start("sparse")
            standard_lists.append(self._tfidf(processed, k, where))
            if clock:
                clock.lap("sparse")
        if config.use_dense:
            if clock:
                clock.start("dense")
            standard_lists.append(self._dense("standards", processed, k, where))
            chunk_lists.append(self._dense("chunks", processed, k, where))
            if clock:
                clock.lap("dense")
        else:
            if clock:
                clock.start("dense")
                clock.lap("dense")

        if self._tfidf_unknown_year and self._year_filtered(where):
            notes.append(
                f"{self._tfidf_unknown_year} TF-IDF candidate(s) had no year in the "
                f"index and were excluded from this year-filtered query. Rebuild the "
                f"index (`python -m bis_pipeline index`) to record years."
            )

        if clock:
            clock.start("fusion")
        fused_standards = self._fuse(standard_lists)
        fused_chunks = self._fuse(chunk_lists)
        if clock:
            clock.lap("fusion")

        if standards_first:
            ordered = fused_standards + fused_chunks
        else:
            ordered = fused_chunks + fused_standards

        # An offline lexical embedder cannot match a query whose terms appear
        # nowhere in the corpus, so if the lexical retrievers found nothing the
        # dense leg's hits are hash collisions, not relevance. Say "no match"
        # rather than returning the least-unrelated standard with a straight
        # face. Semantic embedders are exempt: matching without lexical overlap
        # is the entire point of them.
        #
        # "Found nothing" is too weak a test on its own. BM25 has no score floor
        # because its scores are not comparable between queries, so a query
        # sharing one common word with one short document scores *high*: "how do
        # I register a private limited company in india" scored 7.9 against the
        # National Flag standard on the word "india" alone, outscoring genuine
        # matches. The floor below is on IDF-weighted keyword coverage, which is
        # comparable, and it was set from measurement (see RetrievalConfig).
        lexical_candidates = [c for lst in standard_lists + chunk_lists for c in lst
                              if str(c.retriever).startswith(("bm25", "tfidf"))]
        lexical_hits = len(lexical_candidates)
        # Reported, never inferred from: this measures how much of the query the
        # best candidate actually contains, and the evaluation shows it does not
        # separate relevance from coincidence well enough to gate on. It is
        # carried in the notes so that a wrong answer can be explained.
        coverage = (self._query_coverage(processed, lexical_candidates)
                    if lexical_candidates else -1.0)
        if (not self.embedder.semantic and lexical_hits and not exact
                and config.min_query_coverage > 0
                and coverage < config.min_query_coverage):
            notes.append(
                f"best candidate covers only {coverage:.0%} of the query's "
                f"informative terms, below the configured "
                f"{config.min_query_coverage:.0%} floor: declining rather than "
                f"returning a keyword coincidence as a match."
            )
            return SearchResponse(query=processed, results=[], reranker="none",
                                  notes=notes, mode=search_mode,
                                  timings=_timings(clock, search_started))

        # Only meaningful if a lexical retriever actually ran. With BM25 and
        # TF-IDF switched off -- the `dense_only` ablation row -- `lexical_hits`
        # is zero because nothing looked, not because nothing matched, and
        # concluding "no term occurs in the corpus" from that made the dense leg
        # look broken when it had in fact found the right standard.
        lexical_legs_ran = bool(config.use_bm25 or config.use_tfidf)
        if (not self.embedder.semantic and lexical_legs_ran
                and lexical_hits == 0 and not exact):
            notes.append(
                f"no term in this query occurs in the corpus. The embedder in use "
                f"({self.embedder.name}) is lexical, so it cannot match on meaning; "
                f"re-run with --embedder st:<model> or api:<model> for semantic search."
            )
            return SearchResponse(query=processed, results=[], reranker="none",
                                  notes=notes, mode=search_mode,
                                  timings=_timings(clock, search_started))

        if exact:
            exact_ids = {c.id for c in exact}
            exact_top = [c for c in exact if c.id in exact_ids]
            ordered = exact_top + [r for r in ordered if r.id not in exact_ids]

        if do_rerank and self.reranker is not None and len(ordered) > 1:
            if clock:
                clock.start("rerank")
            head = ordered[:config.rerank_candidates]
            tail = ordered[config.rerank_candidates:]
            try:
                scores = self.reranker.score(processed.retrieval_text, head)
                for result, score in zip(head, scores):
                    result.rerank_score = float(score)
                head.sort(key=lambda r: (r.rerank_score or 0.0), reverse=True)
                ordered = head + tail
            except Exception as exc:  # pragma: no cover - model/runtime failures
                notes.append(f"reranker failed ({exc}); keeping fusion order")
                log.warning("reranker failed: %s", exc)
            if clock:
                clock.lap("rerank")
        elif clock:
            clock.start("rerank")
            clock.lap("rerank")

        results = self._diversify(ordered, limit=limit, max_per_standard=per_standard)

        # A compliance question must be answered against the current edition.
        # Because `current_only` is deliberately relaxed for that intent (the
        # superseded text is often the one carrying the detailed requirement),
        # a heavily-worded older edition can outrank the current one. Demoting
        # it here -- without removing it -- is what stops the system leading
        # with "IS 269:1989" when asked whether cement is mandatory.
        #
        # Not applied to the supersession intent, where the user is explicitly
        # asking about the old edition and it belongs at the top.
        if processed.intent == Intent.COMPLIANCE and not processed.current_only:
            current = [r for r in results if r.is_current]
            superseded = [r for r in results if not r.is_current]
            if current and superseded:
                results = current + superseded
                notes.append(
                    "compliance question: current editions ranked above superseded ones "
                    f"({len(superseded)} withdrawn edition(s) kept in the results so the "
                    "answer can flag them)"
                )

        # A relevance ranker has no notion of which edition is in force, so a
        # withdrawn edition can outrank its own replacement. Found by the
        # retrieval evaluator: for an aggregates query, IS 456:1978 came back at
        # rank 5 and IS 456:2000 at rank 6. Nobody reading a result list scrolls
        # past the sixth entry to check, so in practice the withdrawn edition
        # was the answer.
        #
        # Not applied to the supersession intent, where the user is asking about
        # a specific old edition and it belongs at the top.
        if processed.intent != Intent.SUPERSESSION and not processed.current_only:
            reordered = self._current_edition_first(results)
            if reordered != results:
                results = reordered
                notes.append(
                    "a withdrawn edition was ranked below its current edition and "
                    "has been reordered (relevance ignored edition currency)"
                )

        # ---- supersession policy ------------------------------------------
        # The filter decided whether a withdrawn edition could be retrieved;
        # the mode decides what may be *recommended*. A user who names the
        # standard explicitly ("IS 269:1989") is exempt: they asked for that
        # edition, and silently swapping it for the current one would be a
        # worse failure than the one this policy exists to prevent.
        named_a_designation = bool(processed.designations)
        separated: list[SearchResult] = []
        if search_mode == "recommend" and not named_a_designation:
            primary = [r for r in results if r.is_current]
            separated = self.with_replacement_metadata(
                [r for r in results if not r.is_current])
            if separated:
                notes.append(
                    f"recommendation mode: {len(separated)} withdrawn edition(s) held "
                    f"out of the ranked results and returned separately with their "
                    f"replacement named"
                )
            results = primary
        elif search_mode == "search":
            results = self.with_replacement_metadata(results)
            unnamed = [r for r in results if not r.is_current and not r.metadata.get("superseded_by")]
            if unnamed:
                # Exposure without the replacement named is not acceptable, and
                # the corpus itself cannot supply it (no supersession chain for
                # these), so drop the rank rather than present a dead standard
                # as a live one.
                dropped = {r.id for r in unnamed}
                results = [r for r in results if r.id not in dropped]
                notes.append(
                    f"search mode: {len(dropped)} withdrawn edition(s) with no known "
                    f"replacement were dropped rather than shown as current"
                )

        warnings = self._annotate_supersession(list(results) + separated)

        return SearchResponse(
            query=processed,
            results=results,
            superseded=separated,
            mode=search_mode,
            supersession_warnings=warnings,
            reranker=(self.reranker.name if (do_rerank and self.reranker) else "none"),
            notes=notes,
            query_coverage=coverage,
            timings=_timings(clock, search_started),
        )

    def _processor(self):
        if not hasattr(self, "_query_processor"):
            from .query_processor import QueryProcessor
            self._query_processor = QueryProcessor(self.data)
        return self._query_processor

    def _exact_matches(self, processed: ProcessedQuery) -> list[SearchResult]:
        """Standards whose designation the user typed verbatim."""
        if not processed.designations:
            return []
        out: list[SearchResult] = []
        for parsed in processed.designations:
            standard = self.data.resolve_designation(parsed.format())
            if standard is None:
                # Try the year-less key: "IS 456" should still find IS 456:2000.
                for candidate in self.data.standards():
                    if candidate.designation.upper().startswith(parsed.format().upper()):
                        standard = candidate
                        break
            if standard is None:
                continue
            out.append(SearchResult(
                id=standard.canonical or standard.designation,
                text=standard.summary,
                metadata=standard.as_metadata(),
                score=1.0,
                provenance={"exact": 1},
                collection="standards",
            ))
        return out
