"""Retrieval evaluation against hand-written questions.

Why this module exists
----------------------
The project's original `qa_pairs.jsonl` (985 pairs) was generated from templates
like ``{"question": "What is IS 269:2015?", "answer": "Ordinary Portland
Cement - Specification"}``. Every one of those is answered by looking up the
designation that is printed in the question, so a system with no retrieval at
all scores 100% on them. They are a smoke test -- they prove the designation
lookup works -- and they measure nothing about retrieval quality.

This module scores a different kind of test set: questions phrased the way a
person phrases them, with no designation in them, where the answer is the
standard a knowledgeable engineer would cite. See ``eval/retrieval_cases.jsonl``
and ``eval/README.md``.

What it measures, and what each number actually means
-----------------------------------------------------
**Hit Rate @k** -- of the questions this corpus *can* answer, how many put a
correct standard in the top k. An expected standard that is not in the corpus is
excluded from the denominator and reported separately as a coverage gap, because
scoring a retriever against an answer it cannot possibly return measures the
corpus, not the retriever.

**MRR @k** -- mean reciprocal rank of the first correct hit within k. Hits at
rank 1 count 1.0, rank 2 count 0.5, and so on; a miss counts 0. This is the
number that separates "usually right" from "right, but ranked third".

**Hallucination rate** -- citations emitted by the answer path that do not
resolve to a standard in the corpus. Note the asymmetry: on the search path this
is structurally zero, because search returns corpus rows by definition, so a
zero there is not evidence of anything. It is only a real measurement when the
answer came from a language model, which is why the report says which mode ran.

**Superseded violation rate** -- a superseded edition appearing in the top
results for a query when a current edition of the same standard is in the
corpus. This is measured with the current-only filter *disabled*, on purpose:
the shipped API filters superseded editions out before the user sees them, so
measuring with the filter on would score the filter, not the ranking. The
interesting question is whether the ranking itself prefers the withdrawn
edition, and that is what this answers.

**Latency P50/P95/P99** -- wall-clock per query, after a warm-up call. A note on
the P99, because it is easy to over-read: with 50 queries the P99 is
approximately the second-worst sample and its confidence interval is enormous.
The report prints the sample count for exactly this reason. Use ``--repeats``
to get more samples before quoting a tail figure to anyone.
"""

from __future__ import annotations

import json
import logging
import math
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from .compliance import yearless_key
from .data import BisData
from .hybrid import HybridSearch, SearchResponse

log = logging.getLogger(__name__)

__all__ = [
    "EvalCase",
    "CaseResult",
    "EvalReport",
    "load_cases",
    "evaluate",
    "format_report",
    "DEFAULT_CASES_PATH",
]

#: Shipped alongside the package so `bis-rag eval` works with no arguments.
DEFAULT_CASES_PATH = Path(__file__).resolve().parents[2] / "eval" / "retrieval_cases.jsonl"

#: Ranks reported in the hit-rate line. @10 needs a top_k of at least 10.
HIT_RANKS = (1, 3, 5, 10)

#: The rank at which supersession is checked. A withdrawn edition at rank 40 is
#: not something a user ever sees; at rank 5 it is a wrong answer.
SUPERSEDED_CHECK_DEPTH = 5

#: The stages a search is timed in, in the order they run. `total` is the whole
#: search; end-to-end RAG latency (retrieval + generation) is reported
#: separately, because one number mixing the two cannot say which is the slow
#: part.
STAGE_ORDER = ("query_processing", "sparse", "dense", "fusion", "rerank", "total")


# ----------------------------------------------------------------------
# test cases
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class EvalCase:
    id: str
    query: str
    #: Acceptable designations. Matched on the year-less key, so an edition
    #: difference is not counted as a retrieval failure -- supersession is
    #: measured separately, and conflating the two hides which one is broken.
    expected: tuple[str, ...] = ()
    difficulty: str = "medium"
    #: Coarse industry grouping for the sector breakdown. Falls back to the
    #: first tag, so a case file written before sectors existed still reports.
    sector: str = ""
    tags: tuple[str, ...] = ()
    rationale: str = ""

    @property
    def expected_keys(self) -> tuple[str, ...]:
        return tuple(key for key in (yearless_key(e) for e in self.expected) if key)

    @property
    def sector_name(self) -> str:
        if self.sector:
            return self.sector
        if self.is_rejection:
            # A rejection case has no sector: it is not about the corpus at all,
            # and letting it fall into "unspecified" would put it in the sector
            # table beside the industries it is being contrasted with.
            return "Out of scope"
        return self.tags[0] if self.tags else "unspecified"

    @property
    def is_rejection(self) -> bool:
        """An out-of-scope query: the only correct answer is "nothing applies".

        Kept in the same file as the real cases so the two cannot drift, but
        excluded from every retrieval metric -- a case with no expected standard
        has no rank to be right or wrong about.
        """
        return not self.expected

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "EvalCase":  # noqa: D102 - see load_cases
        if not row.get("query"):
            raise ValueError(f"eval case {row.get('id')!r} has no query")
        expected = row.get("expected") or []
        if isinstance(expected, str):
            expected = [expected]
        tags = row.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        return cls(
            id=str(row.get("id") or f"case-{abs(hash(row['query'])) % 10**6}"),
            query=str(row["query"]).strip(),
            expected=tuple(str(e).strip() for e in expected if str(e).strip()),
            difficulty=str(row.get("difficulty") or "medium").lower(),
            sector=str(row.get("sector") or "").strip(),
            tags=tuple(str(t) for t in tags),
            rationale=str(row.get("rationale") or ""),
        )


def load_cases(path: str | Path) -> list[EvalCase]:
    """Read a JSONL test set. One case per line, blank lines and # ignored."""
    file = Path(path).expanduser()
    if not file.exists():
        raise FileNotFoundError(
            f"eval cases not found: {file}\n"
            f"  the shipped set lives at {DEFAULT_CASES_PATH}"
        )

    cases: list[EvalCase] = []
    seen: set[str] = set()
    for lineno, raw in enumerate(file.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{file}:{lineno}: not valid JSON -- {exc}") from exc
        case = EvalCase.from_dict(row)
        if case.id in seen:
            # A duplicate id would silently shrink the denominator and make a
            # real miss invisible in the per-case listing.
            raise ValueError(f"{file}:{lineno}: duplicate case id {case.id!r}")
        seen.add(case.id)
        cases.append(case)

    if not cases:
        raise ValueError(f"{file} contains no cases")
    return cases


def _percentile(samples: Sequence[float], p: float) -> float:
    """Linear interpolation between closest ranks.

    The usual definition, and the one ``statistics.quantiles`` approximates at
    these sample sizes. Reported with the sample count everywhere it is printed,
    because a P99 over 50 samples is a statement about the second-worst
    observation, not about a tail.
    """
    if not samples:
        return 0.0
    ordered = sorted(samples)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * (p / 100.0)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[int(position)]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _mrr(pool: Sequence["CaseResult"], k: int) -> float:
    if not pool:
        return 0.0
    total = 0.0
    for result in pool:
        if result.rank is not None and result.rank <= k:
            total += 1.0 / result.rank
    return total / len(pool)


# ----------------------------------------------------------------------
# results
# ----------------------------------------------------------------------
@dataclass
class CaseResult:
    case: EvalCase
    #: 1-based rank of the first acceptable standard, or None if missed.
    rank: Optional[int] = None
    #: Whether the found standard was the current edition, not just a correct one.
    edition_exact: bool = False
    top: list[str] = field(default_factory=list)
    top_keys: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    #: Withdrawn editions that rank ABOVE their own current edition. A defect.
    superseded_ahead: list[str] = field(default_factory=list)
    #: Every withdrawn edition in the window, correctly ranked or not. Reported
    #: so that fixing the ordering cannot hide that they are being retrieved.
    superseded_seen: list[str] = field(default_factory=list)
    #: False when no acceptable standard is in the corpus at all.
    answerable: bool = True
    #: True for an out-of-scope case (expected == []).
    rejection: bool = False
    #: For a rejection case: the retriever returned nothing, i.e. it declined
    #: rather than offering the least-unrelated standard it could find.
    declined: bool = False
    #: For a rejection case: how confident the best returned match was, on the
    #: retriever's own scale. Evidence for "nothing was returned" being a
    #: decision rather than an empty index.
    top_score: float = 0.0
    #: Per-stage milliseconds for the first pass of this case.
    timings: dict[str, float] = field(default_factory=dict)
    #: Withdrawn editions that reached the ranked results in recommendation
    #: mode. Must be empty: this is the hard-zero policy metric.
    superseded_recommended: list[str] = field(default_factory=list)
    #: Withdrawn editions the recommendation policy held back. Not a defect --
    #: it is the count of exposures prevented.
    superseded_withheld: list[str] = field(default_factory=list)
    error: str = ""

    def hit(self, k: int) -> bool:
        return self.rank is not None and self.rank <= k

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.case.id,
            "query": self.case.query,
            "expected": list(self.case.expected),
            "difficulty": self.case.difficulty,
            "tags": list(self.case.tags),
            "answerable": self.answerable,
            "rejection": self.rejection,
            "declined": self.declined,
            "top_score": round(self.top_score, 4),
            "rank": self.rank,
            "sector": self.case.sector_name,
            "timings_ms": self.timings,
            "superseded_recommended": self.superseded_recommended,
            "superseded_withheld": self.superseded_withheld,
            "edition_exact": self.edition_exact,
            "hit": {f"@{k}": self.hit(k) for k in HIT_RANKS},
            "top": self.top,
            "superseded_ahead": self.superseded_ahead,
            "superseded_seen": self.superseded_seen,
            "latency_ms": round(self.latency_ms, 3),
            "error": self.error,
        }


@dataclass
class EvalReport:
    cases: list[CaseResult] = field(default_factory=list)
    corpus_size: int = 0
    corpus_chunks: int = 0
    retriever: str = ""
    top_k: int = 10
    repeats: int = 1
    #: Answer-path measurement; None when the answer pass was not run.
    answer_mode: str = ""
    citations_total: int = 0
    citations_unresolvable: list[str] = field(default_factory=list)
    answer_superseded: list[str] = field(default_factory=list)
    latencies: list[float] = field(default_factory=list)
    #: End-to-end RAG latencies (retrieval + generation), kept separate from
    #: `latencies`, which covers retrieval only. One number mixing the two
    #: cannot answer "is the model or the index the slow part".
    rag_latencies: list[float] = field(default_factory=list)
    #: Per-stage samples collected from SearchResponse.timings.
    stage_latencies: dict[str, list[float]] = field(default_factory=dict)
    #: Where the corpus came from -- fixture or real. Set by the CLI.
    provenance: Optional[dict[str, Any]] = None
    notes: list[str] = field(default_factory=list)
    #: Set by the CLI when --baseline ran, so the comparison survives --json.
    baseline: Optional[dict[str, Any]] = None

    # ---- coverage ----------------------------------------------------
    #: Cases whose expected standard is in the corpus ("covered"), cases whose
    #: standard is not ("unanswerable"), and out-of-scope cases ("rejection").
    #: Every rate below says which population it divides by, because a hit rate
    #: over covered cases and a hit rate over every case are different numbers
    #: and the difference is exactly the corpus's coverage gap.
    @property
    def answerable(self) -> list[CaseResult]:
        # `rejection` is checked as well as the flag because the flag defaults to
        # True on a hand-built CaseResult, and a rejection case silently joining
        # the ranking denominators would corrupt every rate in the report.
        return [r for r in self.cases if r.answerable and not r.rejection]

    @property
    def unanswerable(self) -> list[CaseResult]:
        return [r for r in self.cases
                if not r.answerable and not r.rejection]

    @property
    def rejections(self) -> list[CaseResult]:
        return [r for r in self.cases if r.rejection]

    @property
    def scoring(self) -> list[CaseResult]:
        """Every retrieval case, covered or not: the end-to-end population."""
        return [r for r in self.cases if not r.rejection]

    @property
    def coverage(self) -> float:
        population = self.scoring
        return len(self.answerable) / len(population) if population else 0.0

    # ---- ranking -----------------------------------------------------
    def hit_rate(self, k: int) -> float:
        """Covered-only: of the cases whose standard *is* in the corpus."""
        pool = self.answerable
        return sum(1 for r in pool if r.hit(k)) / len(pool) if pool else 0.0

    def hit_rate_end_to_end(self, k: int) -> float:
        """Every scored case, with a standard the corpus lacks scored as a miss.

        This is the number a user experiences, and its distance from the
        covered-only figure is the coverage gap showing through. Both are
        reported; quoting only the first overstates the system, only the second
        understates it.
        """
        pool = self.scoring
        if not pool:
            return 0.0
        return sum(1 for r in pool if r.hit(k)) / len(pool)

    def mrr(self, k: int) -> float:
        return _mrr(self.answerable, k)

    def mrr_end_to_end(self, k: int) -> float:
        return _mrr(self.scoring, k)

    @property
    def edition_exact_rate(self) -> float:
        pool = self.answerable
        return sum(1 for r in pool if r.edition_exact) / len(pool) if pool else 0.0

    # ---- out-of-scope queries ----------------------------------------
    @property
    def rejection_accuracy(self) -> float:
        """Of the out-of-scope queries, how many got no confident answer.

        ``1.0`` means every one of them was declined. The system declines when
        the lexical retrievers find no term in common with the corpus, which is
        a real decision (see `HybridSearch.search`) rather than an empty index.
        """
        pool = self.rejections
        if not pool:
            return 0.0
        return sum(1 for r in pool if r.declined) / len(pool)

    @property
    def out_of_scope_answered(self) -> list[CaseResult]:
        return [r for r in self.rejections if not r.declined]

    @property
    def max_negative_score(self) -> float:
        """The best raw score any out-of-scope query managed to obtain."""
        return max((r.top_score for r in self.rejections), default=0.0)

    @property
    def min_positive_score(self) -> float:
        """The weakest top score among the covered cases that found a match.

        Read with `max_negative_score`: if the worst genuine hit outscores the
        best unrelated one, there is a separating threshold and the decline
        decision has evidence behind it. If they overlap, no score floor can
        tell them apart and the report says so rather than implying it can.
        """
        scores = [r.top_score for r in self.answerable if r.rank is not None and r.top_score]
        return min(scores) if scores else 0.0

    @property
    def scores_separate(self) -> bool:
        if not self.rejections or not self.answerable:
            return False
        return self.min_positive_score > self.max_negative_score

    # ---- correctness of what was emitted -----------------------------
    @property
    def superseded_violation_rate(self) -> float:
        pool = self.answerable
        if not pool:
            return 0.0
        return sum(1 for r in pool if r.superseded_ahead) / len(pool)

    @property
    def superseded_exposure_rate(self) -> float:
        """Cases whose *recommended* results include a withdrawn edition.

        Measured separately from the ordering violation above, and it is the
        stricter of the two: the ordering metric asks "is a withdrawn edition
        ranked sensibly?", this one asks "was one offered at all?" In
        recommendation mode the target is zero, because no ranking of a dead
        standard is safe to act on.

        Denominator is the covered cases -- nothing else can return a match.
        """
        pool = self.answerable
        if not pool:
            return 0.0
        return sum(1 for r in pool if r.superseded_recommended) / len(pool)

    @property
    def invalid_citation_rate(self) -> float:
        """Share of emitted citations that do not resolve to a corpus standard.

        Named for what it measures rather than for what people assume it
        measures. "Hallucination rate" overclaims on two counts: on the search
        path this is structurally zero (search returns corpus rows), and in
        extractive mode the answer quotes retrieved text, so a zero says the
        template stayed inside its sources -- not that a model would. It only
        becomes evidence about a model when ``BIS_RAG_LLM`` is set, which
        ``answer_mode`` records.
        """
        if not self.citations_total:
            return 0.0
        return len(self.citations_unresolvable) / self.citations_total

    #: Old name, kept because callers and reports used it. Prefer
    #: `invalid_citation_rate`, which says what it actually counts.
    hallucination_rate = invalid_citation_rate

    # ---- latency by stage --------------------------------------------
    def stage_percentile(self, stage: str, p: float) -> float:
        samples = self.stage_latencies.get(stage) or []
        return _percentile(samples, p)

    def stage_summary(self) -> dict[str, dict[str, float]]:
        """P50/P95/P99 per stage, plus the retrieval total."""
        out: dict[str, dict[str, float]] = {}
        for stage in STAGE_ORDER:
            samples = self.stage_latencies.get(stage) or []
            if not samples:
                continue
            out[stage] = {
                "samples": len(samples),
                "p50": round(_percentile(samples, 50), 3),
                "p95": round(_percentile(samples, 95), 3),
                "p99": round(_percentile(samples, 99), 3),
                "mean": round(statistics.fmean(samples), 3),
            }
        return out

    def rag_latency_summary(self) -> dict[str, float]:
        return {
            "samples": len(self.rag_latencies),
            "p50": round(_percentile(self.rag_latencies, 50), 2),
            "p95": round(_percentile(self.rag_latencies, 95), 2),
            "p99": round(_percentile(self.rag_latencies, 99), 2),
        }

    # ---- latency -----------------------------------------------------
    def percentile(self, p: float) -> float:
        return _percentile(self.latencies, p)

    @property
    def latency_samples(self) -> int:
        return len(self.latencies)

    @property
    def failures(self) -> list[CaseResult]:
        return [r for r in self.answerable if r.error]

    def by_difficulty(self) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for level in ("easy", "medium", "hard"):
            pool = [r for r in self.answerable if r.case.difficulty == level]
            if not pool:
                continue
            out[level] = {
                "n": len(pool),
                "hit@1": sum(1 for r in pool if r.hit(1)) / len(pool),
                "hit@5": sum(1 for r in pool if r.hit(5)) / len(pool),
                "mrr@5": sum(1.0 / r.rank for r in pool if r.rank and r.rank <= 5)
                / len(pool),
            }
        return out

    def missing_standards(self) -> dict[str, list[str]]:
        """designation -> the case ids that wanted it, for standards not held.

        The coverage count alone ("18% answerable") tells you how bad the gap is
        but not what to scrape next. This is the actionable half: which
        standards, and how many cases each one costs.
        """
        missing: dict[str, list[str]] = {}
        for result in self.unanswerable:
            for designation in result.case.expected:
                missing.setdefault(designation, []).append(result.case.id)
        return dict(sorted(missing.items(), key=lambda kv: (-len(kv[1]), kv[0])))

    def by_sector(self) -> dict[str, dict[str, float]]:
        """Same metrics per industry sector, over every scored case.

        Denominators differ per sector -- a sector with four cases and one with
        twenty are not comparable -- so `n` is carried in the row rather than
        left to the reader to look up. Sectors small enough that one case moves
        the number by more than ten points are flagged.
        """
        out: dict[str, list[CaseResult]] = {}
        for result in self.scoring:
            out.setdefault(result.case.sector_name, []).append(result)
        rows: dict[str, dict[str, float]] = {}
        for sector, pool in sorted(out.items(), key=lambda kv: -len(kv[1])):
            covered = [r for r in pool if r.answerable]
            rows[sector] = {
                "n": len(pool),
                "covered": len(covered),
                "hit@1": sum(1 for r in pool if r.hit(1)) / len(pool),
                "hit@5": sum(1 for r in pool if r.hit(5)) / len(pool),
                "hit@5_covered": (sum(1 for r in covered if r.hit(5)) / len(covered)
                                  if covered else 0.0),
                "mrr@5": _mrr(pool, 5),
                "exact_edition": (sum(1 for r in covered if r.edition_exact)
                                  / len(covered) if covered else 0.0),
                "thin": len(pool) < 10,
            }
        return rows

    def by_tag(self) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for result in self.answerable:
            for tag in result.case.tags or ("untagged",):
                bucket = out.setdefault(tag, {"n": 0, "hits": 0})
                bucket["n"] += 1
                bucket["hits"] += 1 if result.rank is not None else 0
        return {
            tag: {"n": v["n"], "hit@10": v["hits"] / v["n"]}
            for tag, v in sorted(out.items(), key=lambda kv: -kv[1]["n"])
        }

    def misses(self, k: int = 5) -> list[CaseResult]:
        return [r for r in self.answerable if not r.hit(k)]

    def as_dict(self) -> dict[str, Any]:
        return {
            "cases": len(self.cases),
            "corpus": {"standards": self.corpus_size, "chunks": self.corpus_chunks},
            "retriever": self.retriever,
            "top_k": self.top_k,
            "repeats": self.repeats,
            "provenance": self.provenance,
            "coverage": {
                "scored": len(self.scoring),
                "answerable": len(self.answerable),
                "unanswerable": len(self.unanswerable),
                "rejection": len(self.rejections),
                "rate": round(self.coverage, 4),
                "absent_from_corpus": sorted(
                    {e for r in self.unanswerable for e in r.case.expected}
                ),
                "missing_standards": self.missing_standards(),
            },
            # Covered-only: of the cases whose standard the corpus actually
            # holds. The end-to-end figures beside them divide by every scored
            # case, so the two differ by exactly the coverage gap.
            "hit_rate": {f"@{k}": round(self.hit_rate(k), 4) for k in HIT_RANKS},
            "mrr": {"@5": round(self.mrr(5), 4), "@10": round(self.mrr(10), 4)},
            "hit_rate_end_to_end": {f"@{k}": round(self.hit_rate_end_to_end(k), 4)
                                    for k in HIT_RANKS},
            "mrr_end_to_end": {"@5": round(self.mrr_end_to_end(5), 4),
                               "@10": round(self.mrr_end_to_end(10), 4)},
            "edition_exact_rate": round(self.edition_exact_rate, 4),
            "invalid_citation_rate_extractive": round(self.invalid_citation_rate, 4),
            "citations": {
                "answer_mode": self.answer_mode,
                "citations_total": self.citations_total,
                "unresolvable": sorted(set(self.citations_unresolvable)),
                "superseded_citations": sorted(set(self.answer_superseded)),
            },
            "superseded_first_violation_rate": round(self.superseded_violation_rate, 4),
            "superseded_violations": [
                {"id": r.case.id, "editions": r.superseded_ahead}
                for r in self.answerable
                if r.superseded_ahead
            ],
            "superseded_exposure_rate_recommend": round(self.superseded_exposure_rate, 4),
            "superseded_exposed": [
                {"id": r.case.id, "editions": r.superseded_recommended}
                for r in self.answerable
                if r.superseded_recommended
            ],
            "superseded_withheld": sorted(
                {d for r in self.answerable for d in r.superseded_withheld}
            ),
            "superseded_editions_retrieved": sorted(
                {d for r in self.answerable for d in r.superseded_seen}
            ),
            "rejection": {
                "cases": len(self.rejections),
                "declined": sum(1 for r in self.rejections if r.declined),
                "accuracy": round(self.rejection_accuracy, 4),
                "answered": [
                    {"id": r.case.id, "query": r.case.query, "top": r.top[:3],
                     "score": round(r.top_score, 4)}
                    for r in self.out_of_scope_answered
                ],
                "max_top_score": round(self.max_negative_score, 4),
                "min_positive_top_score": round(self.min_positive_score, 4),
                "scores_separate": self.scores_separate,
            },
            # Retrieval alone, then retrieval + generation, then each stage.
            "latency_ms": {
                "samples": self.latency_samples,
                "p50": round(self.percentile(50), 2),
                "p95": round(self.percentile(95), 2),
                "p99": round(self.percentile(99), 2),
                "mean": round(statistics.fmean(self.latencies), 2) if self.latencies else 0.0,
                "max": round(max(self.latencies), 2) if self.latencies else 0.0,
            },
            "rag_latency_ms": self.rag_latency_summary(),
            "stage_latency_ms": self.stage_summary(),
            "by_difficulty": {
                k: {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()}
                for k, v in self.by_difficulty().items()
            },
            "by_sector": {
                k: {kk: (round(vv, 4) if isinstance(vv, float) else vv)
                    for kk, vv in v.items()}
                for k, v in self.by_sector().items()
            },
            "by_tag": self.by_tag(),
            "misses": [r.as_dict() for r in self.misses(5)],
            "per_case": [r.as_dict() for r in self.cases],
            "notes": self.notes,
            "baseline": self.baseline,
        }


# ----------------------------------------------------------------------
# corpus helpers
# ----------------------------------------------------------------------
class _Corpus:
    """The set of standards the retriever could possibly return."""

    def __init__(self, data: BisData):
        standards = data.standards()
        self.size = len(standards)
        #: year-less key -> the designation of the *current* edition, if any.
        self.current: dict[str, str] = {}
        self.keys: set[str] = set()
        for standard in standards:
            key = yearless_key(standard.designation or standard.canonical)
            if not key:
                continue
            self.keys.add(key)
            if standard.is_current:
                self.current.setdefault(key, standard.designation)

    def has(self, key: str) -> bool:
        return key in self.keys

    def has_current_edition(self, key: str) -> bool:
        return key in self.current


def superseded_violations(results: Sequence[Any], corpus: _Corpus, depth: int) -> list[str]:
    """Superseded editions that *outrank* the current edition of the same standard.

    The first version of this check flagged any withdrawn edition appearing in
    the top results, and reported a 50% violation rate on a test run where the
    current edition was the number-one result in every single case. That is not
    a defect, and a metric that cries wolf on correct behaviour is worse than no
    metric -- it teaches the reader to ignore it.

    What actually matters is ordering: a user reads the top result, so a
    withdrawn edition is only a problem if it comes *before* the current one, or
    if the current one is not in the window at all. A superseded edition sitting
    at rank 4 under its own current edition at rank 1 is correctly ranked, and
    is annotated with a supersession warning besides.
    """
    first_current: dict[str, int] = {}
    first_superseded: dict[str, tuple[int, str]] = {}

    for position, item in enumerate(results[:depth], start=1):
        key = yearless_key(item.designation)
        if not key or not corpus.has(key):
            continue
        if item.is_current:
            first_current.setdefault(key, position)
        elif corpus.has_current_edition(key):
            first_superseded.setdefault(key, (position, item.designation))

    violations: list[str] = []
    for key, (position, designation) in first_superseded.items():
        current_position = first_current.get(key)
        if current_position is None or position < current_position:
            violations.append(designation)
    return violations


def superseded_present(results: Sequence[Any], corpus: _Corpus, depth: int) -> list[str]:
    """Every withdrawn edition in the window, ranked correctly or not.

    Reported alongside the violation count so that a fix to the ordering cannot
    hide the fact that withdrawn editions are being retrieved at all.
    """
    seen: list[str] = []
    for item in results[:depth]:
        key = yearless_key(item.designation)
        if key and not item.is_current and corpus.has_current_edition(key):
            seen.append(item.designation)
    return seen


# ----------------------------------------------------------------------
# the run
# ----------------------------------------------------------------------
def evaluate(
    search: HybridSearch,
    cases: Sequence[EvalCase],
    *,
    top_k: int = 10,
    repeats: int = 1,
    check_supersession: bool = True,
    warmup: bool = True,
    recommend_pass: bool = True,
) -> EvalReport:
    """Run every case through the retriever and compute the metrics."""
    if top_k < max(HIT_RANKS):
        # Silently reporting 0.0 for Hit Rate @10 because only 5 were fetched
        # would look like a retrieval failure rather than a configuration one.
        raise ValueError(f"top_k must be at least {max(HIT_RANKS)} to report Hit Rate @10")

    data: BisData = search.data
    corpus = _Corpus(data)
    report = EvalReport(
        corpus_size=corpus.size,
        corpus_chunks=len(data.chunks()),
        retriever=retriever_label(search),
        top_k=top_k,
        repeats=max(1, repeats),
    )

    if warmup:
        # The first search builds the BM25 indexes, which takes far longer than
        # any query after it. Excluding it is not cheating; including it would
        # put a startup cost into the tail of a per-query latency distribution.
        try:
            search.search("warmup ordinary portland cement", top_k=1)
            report.notes.append("first search excluded from latency as a warm-up")
        except Exception as exc:  # pragma: no cover - a broken corpus fails loudly below
            report.notes.append(f"warm-up failed: {exc}")

    if not corpus.size:
        report.notes.append(
            "the corpus contains no standards: every case is unanswerable and "
            "every metric below is zero by construction, not by measurement"
        )

    for case in cases:
        result = CaseResult(case=case)
        expected_keys = set(case.expected_keys)
        result.rejection = case.is_rejection
        # A rejection case has nothing to be ranked against, so it is excluded
        # from the ranking metrics entirely rather than counted as a miss.
        result.answerable = bool(expected_keys & corpus.keys) if expected_keys else False

        try:
            response, latencies = _run_case(
                search, case, corpus=corpus, top_k=top_k, repeats=report.repeats,
                check_supersession=check_supersession, result=result,
            )
        except Exception as exc:
            result.error = f"{type(exc).__name__}: {exc}"
            result.answerable = False
            log.warning("eval case %s failed: %s", case.id, exc)
            report.cases.append(result)
            continue

        report.latencies.extend(latencies)
        result.top = [item.designation for item in response.results]
        result.top_keys = [yearless_key(designation) for designation in result.top]
        result.top_score = _top_score(response)
        if result.rejection:
            # "Declined" means the retriever returned nothing at all. It is the
            # system's own no-match decision, not a threshold invented here.
            result.declined = not response.results
        for stage, value in (response.timings or {}).items():
            report.stage_latencies.setdefault(stage, []).append(float(value))

        for index, key in enumerate(result.top_keys, start=1):
            if key in expected_keys:
                result.rank = index
                break

        if result.rank is not None:
            found = result.top[result.rank - 1]
            result.edition_exact = corpus.current.get(result.top_keys[result.rank - 1]) == found

        # ---- exposure in recommendation mode --------------------------
        # A second pass with the recommender's policy. The search pass above
        # deliberately disables the current-only *filter* to test the ranking;
        # without this pass the exposure metric would be zero by construction
        # and would certify nothing.
        if recommend_pass and not result.rejection:
            try:
                recommended = search.search(case.query, top_k=top_k,
                                            mode="recommend")
                # Two different numbers, and conflating them would make the
                # metric unfalsifiable:
                #   recommended -> withdrawn editions that reached the ranked
                #                  results. The policy exists to keep this at
                #                  zero, and the metric must be able to fail if
                #                  the policy is ever removed.
                #   withheld    -> withdrawn editions the policy held back. Not
                #                  a violation; evidence that the policy is
                #                  doing work rather than the filter being on.
                result.superseded_recommended = [
                    item.designation for item in recommended.results
                    if not item.is_current
                ]
                result.superseded_withheld = [
                    item.designation for item in getattr(recommended, "superseded", [])
                ]
            except Exception as exc:  # noqa: BLE001
                result.error = result.error or f"recommend pass: {type(exc).__name__}: {exc}"
                log.warning("recommend pass for %s failed: %s", case.id, exc)

        report.cases.append(result)

    return report


def _top_score(response: SearchResponse) -> float:
    """The raw score of the best result, or 0.0 when nothing was returned.

    Deliberately *not* the API's `match_strength`. That figure is the top hit's
    score as a share of the best hit's score, which for the first result is 1.0
    by construction -- it cannot separate a confident answer from a nonsense
    one, and reporting it here would have said "best match strength 1.0000" for
    every declined query. The raw score is comparable across cases using one
    configuration; the report compares the negative set against the positive set
    rather than pretending the number is a probability.
    """
    results = getattr(response, "results", None) or []
    if not results:
        return 0.0
    return float(results[0].score)


def _run_case(
    search: HybridSearch,
    case: EvalCase,
    *,
    corpus: _Corpus,
    top_k: int,
    repeats: int,
    check_supersession: bool,
    result: CaseResult,
) -> tuple[SearchResponse, list[float]]:
    """Run one case `repeats` times. Returns the first response and every timing.

    The extra passes exist for latency samples only; the ranking comes from the
    first pass. All of them are timed and all of them are reported, so the
    sample count in the report is honest.
    """
    response: Optional[SearchResponse] = None
    latencies: list[float] = []
    processed_for_case: Optional[float] = None

    for pass_index in range(repeats):
        query = case.query
        processing_started = time.perf_counter()
        if check_supersession:
            # The current-only filter is a *query processor* decision, so the
            # only way to test the ranking rather than the filter is to process
            # the query and then turn the filter off before searching. Leaving
            # it on would make this metric 0 by construction and prove nothing.
            processed = search.process(query)
            processed_for_case = (time.perf_counter() - processing_started) * 1000.0
            processed.current_only = False
            query_arg: Any = processed
        else:
            query_arg = query

        started = time.perf_counter()
        current = search.search(query_arg, top_k=top_k)
        elapsed = (time.perf_counter() - started) * 1000.0
        latencies.append(elapsed)
        # The supersession pass hands the search an already-processed query, so
        # the search's own `query_processing` stage is zero for it. Timing the
        # processing here keeps the stage honest rather than reporting zero for
        # work that did happen.
        if processed_for_case is not None and pass_index == 0:
            current.timings.setdefault("query_processing", 0.0)
            current.timings["query_processing"] = round(
                current.timings["query_processing"] + processed_for_case, 3)

        if pass_index == 0:
            response = current
            result.latency_ms = elapsed

    assert response is not None

    if check_supersession:
        result.superseded_ahead = superseded_violations(
            response.results, corpus, SUPERSEDED_CHECK_DEPTH)
        result.superseded_seen = superseded_present(
            response.results, corpus, SUPERSEDED_CHECK_DEPTH)

    return response, latencies


# ----------------------------------------------------------------------
# answer path: hallucinations and superseded citations
# ----------------------------------------------------------------------
def evaluate_answers(
    pipeline: Any,
    cases: Sequence[EvalCase],
    report: EvalReport,
) -> EvalReport:
    """Measure what the *answer* path emits, which is where errors reach a user.

    The search path cannot hallucinate: it returns rows it retrieved from the
    corpus. An answer can name a standard that does not exist, so this is the
    measurement that matters -- and it is only informative when a language model
    is generating the text, which the report states.
    """
    corpus = _Corpus(pipeline.data)
    modes: set[str] = set()

    for case in cases:
        if case.is_rejection:
            # An out-of-scope query has no right answer to emit; including it
            # would put the "no matching standards" boilerplate into the
            # citation denominator and dilute the rate with template text.
            continue
        # End-to-end means end to end: this measures retrieval *and* generation,
        # which is why it is reported separately from the retrieval latency.
        started = time.perf_counter()
        try:
            answer = pipeline.answer(case.query, top_k=6)
        except Exception as exc:
            log.warning("answer pass failed for %s: %s", case.id, exc)
            continue
        report.rag_latencies.append((time.perf_counter() - started) * 1000.0)

        modes.add(getattr(answer, "mode", "") or "unknown")
        for citation in getattr(answer, "citations", []):
            designation = getattr(citation, "designation", "") or ""
            if not designation:
                continue
            report.citations_total += 1
            key = yearless_key(designation)
            if not corpus.has(key):
                report.citations_unresolvable.append(designation)
                continue
            # For citations the ordering question does not arise: every one is
            # presented to the user as a source, so a withdrawn edition is a
            # problem wherever it appears.
            if not getattr(citation, "is_current", True) and corpus.has_current_edition(key):
                report.answer_superseded.append(designation)

        # Whatever the generator claimed it could not verify is a hallucination
        # by the generator's own admission, and must be counted even if a
        # citation list happened to filter it out.
        for unsupported in getattr(answer, "unsupported_citations", []) or []:
            report.citations_total += 1
            report.citations_unresolvable.append(str(unsupported))

    report.answer_mode = ", ".join(sorted(m for m in modes if m)) or "not run"
    return report


# ----------------------------------------------------------------------
# ablation
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class AblationConfig:
    """One row of the ablation table.

    `expects` is a note about what the row is *for*, so the table reads as an
    experiment rather than six arbitrary pipelines.
    """

    name: str
    use_bm25: bool
    use_tfidf: bool
    use_dense: bool
    fusion: str
    rerank: bool
    note: str


#: The six configurations, in the order the brief lists them: each row adds one
#: component to the row above, so the deltas are attributable.
ABLATION_CONFIGS: tuple[AblationConfig, ...] = (
    AblationConfig("tfidf_only", False, True, False, "rrf", False,
                   "the pre-existing bis_data index, no BM25, no vectors"),
    AblationConfig("bm25_only", True, False, False, "rrf", False,
                   "sparse retrieval over chunks and summaries"),
    AblationConfig("dense_only", False, False, True, "rrf", False,
                   "vectors alone; needs a built store"),
    AblationConfig("bm25_dense", True, False, True, "score", False,
                   "two legs, weighted normalised scores instead of RRF"),
    AblationConfig("bm25_dense_rrf", True, False, True, "rrf", False,
                   "same two legs, reciprocal rank fusion"),
    AblationConfig("bm25_dense_rrf_rerank", True, False, True, "rrf", True,
                   "the shipped configuration"),
)


def ablation(search_factory: Callable[["AblationConfig"], Any],
             cases: Sequence[EvalCase], *, top_k: int = 10,
             repeats: int = 1) -> list[tuple[AblationConfig, EvalReport]]:
    """Run the same cases through every configuration and keep the reports.

    `search_factory` builds a search object for a configuration; the caller owns
    the store directory and embedder, which this module has no business
    choosing. Answering the answer path is not part of an ablation -- the
    question is which retriever ranks best, and generation would add a
    per-configuration cost that says nothing about ranking.
    """
    out: list[tuple[AblationConfig, EvalReport]] = []
    for config in ABLATION_CONFIGS:
        search = search_factory(config)
        report = evaluate(search, cases, top_k=top_k, repeats=repeats,
                          check_supersession=True, warmup=True,
                          recommend_pass=True)
        report.notes.append(f"ablation row: {config.name} -- {config.note}")
        out.append((config, report))
    return out


def ablation_rows(rows: Sequence[tuple[AblationConfig, EvalReport]]) -> list[dict[str, Any]]:
    """The ablation table as records, ready for CSV or JSON."""
    records: list[dict[str, Any]] = []
    for config, report in rows:
        hard = [r for r in report.answerable if r.case.difficulty == "hard"]
        rag = report.rag_latency_summary()
        records.append({
            "config": config.name,
            "bm25": config.use_bm25,
            "tfidf": config.use_tfidf,
            "dense": config.use_dense,
            "fusion": config.fusion if (config.use_bm25 and config.use_dense) else "-",
            "rerank": config.rerank,
            "hit@1": round(report.hit_rate(1), 4),
            "hit@3": round(report.hit_rate(3), 4),
            "hit@5": round(report.hit_rate(5), 4),
            "hit@10": round(report.hit_rate(10), 4),
            "hit@1_end_to_end": round(report.hit_rate_end_to_end(1), 4),
            "hit@5_end_to_end": round(report.hit_rate_end_to_end(5), 4),
            "mrr@5": round(report.mrr(5), 4),
            "mrr@10": round(report.mrr(10), 4),
            "exact_edition": round(report.edition_exact_rate, 4),
            "hard_n": len(hard),
            "hard_hit@5": round(sum(1 for r in hard if r.hit(5)) / len(hard), 4) if hard else 0.0,
            "hard_mrr@5": round(_mrr(hard, 5), 4),
            "latency_p50_ms": round(report.percentile(50), 2),
            "latency_p95_ms": round(report.percentile(95), 2),
            "latency_p99_ms": round(report.percentile(99), 2),
            "rag_p95_ms": rag["p95"] if rag["samples"] else "",
            "superseded_first": round(report.superseded_violation_rate, 4),
            "superseded_exposure": round(report.superseded_exposure_rate, 4),
            "coverage": round(report.coverage, 4),
            "note": config.note,
        })
    return records


def format_ablation(rows: Sequence[tuple[AblationConfig, EvalReport]]) -> str:
    """The ablation table for a terminal."""
    records = ablation_rows(rows)
    lines = ["Retrieval ablation", ""]
    header = (f"  {'config':<24}{'Hit@1':<8}{'Hit@5':<8}{'MRR@5':<8}"
              f"{'exact':<8}{'hard@5':<9}{'P50 ms':<8}{'P95 ms'}")
    lines += [header, "  " + "-" * (len(header) - 2)]
    for record in records:
        lines.append(
            f"  {record['config']:<24}{_pct(record['hit@1']):<8}"
            f"{_pct(record['hit@5']):<8}{record['mrr@5']:<8.4f}"
            f"{_pct(record['exact_edition']):<8}{_pct(record['hard_hit@5']):<9}"
            f"{record['latency_p50_ms']:<8}{record['latency_p95_ms']}"
        )
    lines += ["",
              "  Every row is measured on the same cases and the same corpus.",
              "  'hard@5' is the hit rate over the keyword-free questions, the only",
              "  ones that separate semantic retrieval from a term index."]
    dense = next((r for r in records if r["config"] == "dense_only"), None)
    if dense and dense["hard_hit@5"] == 0 and records:
        # Without this, a zero in the dense row reads as a broken vector store.
        # It is the expected result for a lexical embedder, and saying so is the
        # difference between a measurement and a misleading one.
        lines += ["",
                  "  dense_only loses every keyword-free case. That is the embedder, not",
                  "  the vectors: the store here was built with a lexical hashing",
                  "  embedder, which matches words rather than meaning. Rebuild with",
                  "  --embedder st:<model> or api:<model> before reading that row as a",
                  "  verdict on dense retrieval."]
    if records:
        best = max(records, key=lambda r: (r["hit@5"], r["mrr@5"]))
        shipped = next((r for r in records if r["config"] == "bm25_dense_rrf_rerank"), None)
        lines += ["", f"  best Hit@5: {best['config']} ({_pct(best['hit@5'])})"]
        if shipped and shipped is not best:
            lines.append(
                f"  the shipped configuration scores {_pct(shipped['hit@5'])} at Hit@5:"
                f" the extra machinery is costing more than it returns on this corpus"
            )
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------
# presentation
# ----------------------------------------------------------------------
def retriever_label(search: Any) -> str:
    """Describe what will actually run, not what is installed.

    `getattr(search.reranker, "name")` reports a configured reranker even when
    `config.rerank` is False or the dense leg has no store, which made the
    baseline comparison label both runs identically -- the one thing the
    comparison exists to distinguish.
    """
    config = getattr(search, "config", None)
    legs = [
        name for name, enabled in (
            ("bm25", getattr(config, "use_bm25", True)),
            ("tfidf", getattr(config, "use_tfidf", True)),
            ("dense", getattr(config, "use_dense", True)),
        ) if enabled
    ]
    reranker = getattr(getattr(search, "reranker", None), "name", None)
    if getattr(config, "rerank", True) and reranker:
        return f"{'+'.join(legs) or 'none'} -> {reranker}"
    return f"{'+'.join(legs) or 'none'} (no rerank)"


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def format_report(report: EvalReport, *, show_misses: int = 10) -> str:
    """The human-readable report. Numbers first, then what went wrong."""
    lines: list[str] = []
    add = lines.append

    add("Retrieval evaluation")
    if report.provenance:
        add(f"  corpus provenance     {report.provenance.get('kind', 'unknown').upper()}")
    add(f"  cases                 {len(report.cases)}"
        f"   (scored {len(report.scoring)}, out-of-scope {len(report.rejections)})")
    add(f"  corpus                {report.corpus_size} standards, {report.corpus_chunks} chunks")
    add(f"  reranker              {report.retriever or 'none'}")
    add(f"  top_k                 {report.top_k}   (repeats {report.repeats})")
    if report.provenance and not report.provenance.get("certifiable_as_production"):
        add("")
        add("  " + "!" * 68)
        add("  FIXTURE DATA -- these numbers describe the test corpus, not the")
        add("  197-standard dataset. They are not production accuracy.")
        add("  " + "!" * 68)
    add("")

    add("Coverage")
    add(f"  scored cases          {len(report.scoring)}")
    add(f"  covered (answerable)  {len(report.answerable)}/{len(report.scoring)}"
        f"  ({_pct(report.coverage)})")
    add(f"  out-of-scope cases    {len(report.rejections)}   (reported separately below)")
    if report.unanswerable:
        add(f"  standards not held    {len(report.missing_standards())} distinct"
            f"  (affecting {len(report.unanswerable)} case(s))")
        add("                        a retriever cannot return a standard the corpus lacks,")
        add("                        so every rate below is given twice: covered-only,")
        add("                        and end-to-end (which counts these as misses)")
    add("")

    add("Ranking")
    add(f"  {'':<21}{'covered':<12}{'end-to-end'}")
    for k in HIT_RANKS:
        add(f"  Hit Rate @{k:<11} {_pct(report.hit_rate(k)):<12}{_pct(report.hit_rate_end_to_end(k))}")
    add(f"  {'MRR @5':<21}{report.mrr(5):<12.4f}{report.mrr_end_to_end(5):.4f}")
    add(f"  {'MRR @10':<21}{report.mrr(10):<12.4f}{report.mrr_end_to_end(10):.4f}")
    add(f"  exact edition         {_pct(report.edition_exact_rate)}"
        f"      (current edition, not just the right number)")
    add("")

    add("Correctness of what was emitted")
    # Renamed from "hallucination rate": on the search path the number is
    # structurally zero, and in extractive mode it measures the template, not a
    # model. The old name invited a claim the measurement cannot support.
    add(f"  Invalid citation rate  {_pct(report.invalid_citation_rate)}"
        f"   ({len(report.citations_unresolvable)} of {report.citations_total}"
        f" citations, mode: {report.answer_mode or 'not run'})")
    add("                        (invalid citation rate in extractive mode)")
    if report.answer_mode in ("extractive", "not run"):
        add("                        NOTE: extractive mode quotes retrieved text, so this")
        add("                        is 0 by construction here. It only measures the model")
        add("                        when an LLM is configured (BIS_RAG_LLM).")
    if report.citations_unresolvable:
        add(f"                        e.g. {', '.join(sorted(set(report.citations_unresolvable))[:5])}")
    violations = sum(1 for r in report.answerable if r.superseded_ahead)
    add(f"  Superseded-first       {_pct(report.superseded_violation_rate)}"
        f"   ({violations} of {len(report.answerable)} cases; target 0%)")
    add("                        a withdrawn edition ranking ABOVE its own current")
    add("                        edition, or appearing with the current one absent")
    add("                        from the window. Measured with the current-only")
    add("                        filter disabled, so this scores the ranking rather")
    add("                        than the filter the API applies before a user sees it")
    exposed = sum(1 for r in report.answerable if r.superseded_recommended)
    withheld = sorted({d for r in report.answerable for d in r.superseded_withheld})
    add(f"  Superseded exposure    {_pct(report.superseded_exposure_rate)}"
        f"   ({exposed} of {len(report.answerable)} cases in recommend mode;"
        f" target 0%)")
    add("                        a withdrawn edition reaching the ranked")
    add("                        recommendations. Separate from the ordering metric")
    add("                        above: that one asks how it was ranked, this one")
    add("                        asks whether it was offered at all.")
    if withheld:
        add(f"                        policy is doing work: {len(withheld)} withdrawn")
        add(f"                        edition(s) were held back -- {', '.join(withheld[:4])}")
    retrieved = sorted({d for r in report.answerable for d in r.superseded_seen})
    if retrieved:
        add("                        informational: withdrawn editions were retrieved")
        add(f"                        in {len(retrieved)} case(s) but ranked below their")
        add(f"                        current edition -- {', '.join(retrieved[:4])}")
    add("")

    add("Out-of-scope queries  (expected = [])")
    add(f"  cases                 {len(report.rejections)}")
    add(f"  declined (correct)    {sum(1 for r in report.rejections if r.declined)}"
        f"/{len(report.rejections)}   ({_pct(report.rejection_accuracy)})")
    if report.rejections:
        add(f"  best raw score        {report.max_negative_score:.4f}"
            f"   (strongest an unrelated query scored)")
        add(f"  weakest real hit      {report.min_positive_score:.4f}"
            f"   (weakest top score among covered cases)")
        if report.out_of_scope_answered:
            add("                        the two sets overlap, so no score floor can")
            add("                        separate them: relevance on this corpus is a")
            add("                        ranking signal, not a confidence one")
    for result in report.out_of_scope_answered[:5]:
        add(f"    not declined: {result.case.id:<20} -> {', '.join(result.top[:2])}")
    add("")

    add("Latency (per query, ms)")
    rag = report.rag_latency_summary()
    add(f"  {'':<22}{'samples':<9}{'P50':<8}{'P95':<8}{'P99'}")
    add(f"  {'retrieval':<22}{report.latency_samples:<9}{report.percentile(50):<8.1f}"
        f"{report.percentile(95):<8.1f}{report.percentile(99):.1f}")
    if rag["samples"]:
        add(f"  {'end-to-end RAG':<22}{int(rag['samples']):<9}{rag['p50']:<8.1f}"
            f"{rag['p95']:<8.1f}{rag['p99']:.1f}")
    else:
        # Said explicitly rather than omitted: the two figures answer different
        # questions (is the index slow, or is the generator slow?) and a missing
        # row reads as a zero.
        add("  end-to-end RAG        not measured (answer pass disabled)")
    if report.latency_samples < 200:
        add(f"                        a P99 from {report.latency_samples} samples is"
            f" ~the second-worst observation;")
        add("                        use --repeats for a tail figure worth quoting")
    stages = report.stage_summary()
    add("")
    if not stages:
        add("Retrieval stages (ms)  not instrumented in this run")
    if stages:
        add("Retrieval stages (ms)")
        add("                        where the time inside `retrieval` above goes")
        add(f"  {'stage':<20}{'P50':<9}{'P95':<9}{'P99'}")
        for stage in STAGE_ORDER:
            stats = stages.get(stage)
            if not stats:
                continue
            # Three decimals for the sub-millisecond stages: printing "0.0" for
            # query understanding would read as "not measured" when it is in
            # fact measured and fast.
            add(f"  {stage:<20}{stats['p50']:<9.3f}{stats['p95']:<9.3f}{stats['p99']:.3f}")
        add("                        measured where each stage runs, not derived")
        add("                        from the total")
    add("")
    if report.rag_latencies:
        add("End-to-end RAG latency (ms) -- retrieval plus generation")
        add(f"  samples {int(rag['samples'])}   P50 {rag['p50']}   P95 {rag['p95']}"
            f"   P99 {rag['p99']}")
        add("")

    by_difficulty = report.by_difficulty()
    if by_difficulty:
        add("By difficulty  (does it work when the question has no keywords in it?)")
        for level in ("easy", "medium", "hard"):
            stats = by_difficulty.get(level)
            if not stats:
                continue
            add(f"  {level:<8} n={int(stats['n']):<4} Hit@1 {_pct(stats['hit@1']):<8}"
                f" Hit@5 {_pct(stats['hit@5']):<8} MRR@5 {stats['mrr@5']:.3f}")
        add("")

    by_sector = report.by_sector()
    if by_sector:
        add("By sector")
        for sector, stats in by_sector.items():
            thin = "  (n<10: one case moves this)" if stats.get("thin") else ""
            add(f"  {sector:<22} n={int(stats['n']):<4} covered {int(stats['covered']):<4}"
                f" Hit@5 {_pct(stats['hit@5']):<8} MRR@5 {stats['mrr@5']:.3f}{thin}")
        add("")

    missing = report.missing_standards()
    if missing:
        worst = list(missing.items())[:5]
        add(f"Standards the corpus does not hold ({len(missing)})"
            "  -- what to scrape next")
        for designation, ids in worst:
            add(f"  {designation:<14} costs {len(ids)} case(s): {', '.join(ids[:3])}"
                + (" ..." if len(ids) > 3 else ""))
        if len(missing) > len(worst):
            add(f"  ... and {len(missing) - len(worst)} more; see "
                f"missing_corpus_standards.json")
        add("")

    if report.answer_superseded:
        add("Superseded citations in answers")
        for designation in sorted(set(report.answer_superseded)):
            add(f"  {designation}")
        add("")

    failures = report.failures
    if failures:
        add(f"Errors ({len(failures)})")
        for result in failures[:show_misses]:
            add(f"  {result.case.id:<24} {result.error}")
        add("")

    misses = report.misses(5)
    if misses:
        add(f"Missed within the top 5 ({len(misses)})")
        for result in misses[:show_misses]:
            expected = " | ".join(result.case.expected)
            add(f"  {result.case.id:<24} expected {expected}")
            add(f"  {'':<24} query: {result.case.query}")
            add(f"  {'':<24} got:   {', '.join(result.top[:3]) or '(nothing)'}")
        if len(misses) > show_misses:
            add(f"  ... and {len(misses) - show_misses} more; --json has the full list")
        add("")

    for note in report.notes:
        add(f"note: {note}")

    return "\n".join(lines).rstrip() + "\n"


def gate_failures(
    report: EvalReport,
    *,
    max_superseded_violation: float = 0.0,
    max_superseded_exposure: float = 0.0,
    min_hit_rate_5: Optional[float] = None,
    min_hit_rate_1: Optional[float] = None,
    min_rejection_accuracy: Optional[float] = None,
    max_invalid_citations: Optional[float] = None,
    max_hallucination: Optional[float] = None,
) -> list[str]:
    """Thresholds, as a list of human-readable failures. Empty means pass.

    Both supersession thresholds default to a hard zero, and they are two
    different failures: *first violation* is a withdrawn edition outranking its
    own current one, *exposure* is a withdrawn edition reaching the ranked
    recommendations at all. Telling a user to buy to a withdrawn edition is the
    worst answer this system can give, and it is never an acceptable trade for a
    higher hit rate.
    """
    problems: list[str] = []
    if report.superseded_violation_rate > max_superseded_violation:
        problems.append(
            f"superseded-first violation rate {_pct(report.superseded_violation_rate)} "
            f"exceeds the allowed {_pct(max_superseded_violation)}"
        )
    if report.superseded_exposure_rate > max_superseded_exposure:
        problems.append(
            f"superseded exposure rate in recommendation mode "
            f"{_pct(report.superseded_exposure_rate)} exceeds the allowed "
            f"{_pct(max_superseded_exposure)}"
        )
    if (min_rejection_accuracy is not None and report.rejections
            and report.rejection_accuracy < min_rejection_accuracy):
        problems.append(
            f"out-of-scope rejection accuracy {_pct(report.rejection_accuracy)} "
            f"is below {_pct(min_rejection_accuracy)}"
        )
    if min_hit_rate_5 is not None and report.hit_rate(5) < min_hit_rate_5:
        problems.append(f"Hit Rate @5 {_pct(report.hit_rate(5))} is below {_pct(min_hit_rate_5)}")
    if min_hit_rate_1 is not None and report.hit_rate(1) < min_hit_rate_1:
        problems.append(f"Hit Rate @1 {_pct(report.hit_rate(1))} is below {_pct(min_hit_rate_1)}")
    ceiling = max_invalid_citations if max_invalid_citations is not None else max_hallucination
    if ceiling is not None and report.invalid_citation_rate > ceiling:
        problems.append(
            f"invalid citation rate {_pct(report.invalid_citation_rate)} exceeds "
            f"the allowed {_pct(ceiling)}"
        )
    return problems


def compare(full: EvalReport, baseline: EvalReport) -> str:
    """Side-by-side of the full retriever and a degraded one.

    A hit rate on its own says nothing about whether the semantic and reranking
    machinery is earning its keep: on a small corpus a keyword search can score
    just as well. Running the same cases with the extra legs switched off is what
    turns "we got 92%" into "we got 92% and keyword-only got 61%, so the rest of
    the pipeline is doing the work".
    """
    lines = [
        "",
        "Against a degraded baseline",
        f"  full     : {full.retriever or 'none'}",
        f"  baseline : {baseline.retriever or 'none'} (BM25 only, no fusion, no rerank)",
        "",
        f"  {'':<14}{'full':>9}{'baseline':>11}{'delta':>9}",
    ]
    for label, value in (
        ("Hit Rate @1", "hit1"),
        ("Hit Rate @3", "hit3"),
        ("Hit Rate @5", "hit5"),
        ("MRR @5", "mrr5"),
    ):
        if value == "mrr5":
            full_value, base_value = full.mrr(5), baseline.mrr(5)
            render = lambda v: f"{v:.4f}"  # noqa: E731
        else:
            k = int(value[-1])
            full_value, base_value = full.hit_rate(k), baseline.hit_rate(k)
            render = lambda v: f"{v * 100:.1f}%"  # noqa: E731
        delta = full_value - base_value
        delta_text = f"{delta * 100:+.1f}pp" if value != "mrr5" else f"{delta:+.4f}"
        lines.append(f"  {label:<14}{render(full_value):>9}{render(base_value):>11}{delta_text:>9}")

    lines.append("")
    if full.answerable and full.hit_rate(5) <= baseline.hit_rate(5):
        lines.append(
            "  NOTE: the full retriever is not beating the baseline on this corpus.")
        lines.append(
            "  Either the corpus is small enough that keyword search suffices, or the")
        lines.append(
            "  test set is not discriminating. Both are worth knowing before quoting")
        lines.append("  the hit rate above.")
    else:
        lines.append("  The full pipeline beats keyword-only on this test set, so the hit")
        lines.append("  rate reflects retrieval rather than a trivial keyword match.")
    return "\n".join(lines)
