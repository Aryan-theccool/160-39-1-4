"""Write the evaluation artifacts.

Five files, each with one job:

``latest.json``
    The full machine-readable report, including per-case detail and the
    provenance banner.
``latest.md``
    The same thing for a human, with the fixture warning at the top where it
    cannot be missed.
``failures.jsonl``
    One line per case that did not fully succeed: misses, ordering violations,
    out-of-scope queries that were answered, and errors. This is the file to
    read when the summary looks fine and something is still wrong.
``missing_corpus_standards.json``
    Expected standards the corpus does not hold, with the case ids that wanted
    each one. The coverage percentage says how bad the gap is; this says what to
    scrape to close it.
``ablation.csv``
    One row per retriever configuration.

Written by ``bis-rag eval`` unless ``--no-artifacts`` is passed. The directory
is ``eval/results/`` by default and is safe to commit: it is generated output,
but it is *small* generated output, and a number that only exists on the
machine that produced it is a number nobody can check.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

from .evaluate import AblationConfig, EvalReport, ablation_rows, format_report

#: Default location, relative to the repository's `bis_scraper/` directory.
DEFAULT_RESULTS_DIR = Path(__file__).resolve().parents[2] / "eval" / "results"

ARTIFACT_NAMES = (
    "latest.json",
    "latest.md",
    "failures.jsonl",
    "missing_corpus_standards.json",
    "ablation.csv",
)


def failure_records(report: EvalReport) -> list[dict[str, Any]]:
    """Every case worth a second look, with the reason attached.

    Deliberately broader than "rank was None". A case that was answered but
    ranked a withdrawn edition above its current one succeeded by the hit-rate
    metric and still put the wrong first result in front of a user.
    """
    records: list[dict[str, Any]] = []
    for result in report.cases:
        reasons: list[str] = []
        if result.error:
            reasons.append("error")
        if result.rejection:
            if not result.declined:
                reasons.append("out_of_scope_answered")
        else:
            if result.rank is None:
                reasons.append("miss" if result.answerable else "standard_not_in_corpus")
            elif result.rank > 5:
                reasons.append("ranked_below_5")
            if result.superseded_ahead:
                reasons.append("superseded_ranked_first")
            if result.superseded_recommended:
                reasons.append("superseded_recommended")
            if result.answerable and not result.edition_exact and result.rank is not None:
                reasons.append("edition_not_exact")
        if not reasons:
            continue
        records.append({
            "id": result.case.id,
            "reasons": reasons,
            "query": result.case.query,
            "expected": list(result.case.expected),
            "difficulty": result.case.difficulty,
            "sector": result.case.sector_name,
            "rank": result.rank,
            "top": result.top[:5],
            "superseded_ahead": result.superseded_ahead,
            "superseded_recommended": result.superseded_recommended,
            "top_score": round(result.top_score, 4),
            "error": result.error,
            "rationale": result.case.rationale,
        })
    return records


def _markdown(report: EvalReport, *, cases_path: str,
              ablation_rows_data: Sequence[dict[str, Any]] = ()) -> str:
    """The human-readable artifact.

    Reproduces the terminal report inside a fenced block rather than restating
    the numbers, so the file in `eval/results/` and the figure someone saw on
    screen are the same figure by construction.
    """
    lines: list[str] = ["# Retrieval evaluation", ""]
    provenance = report.provenance or {}
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if provenance and not provenance.get("certifiable_as_production"):
        lines += [
            f"> **{provenance.get('kind', 'unverified').upper()} -- NOT PRODUCTION ACCURACY.**",
            ">",
            f"> corpus: `{provenance.get('root', '?')}` "
            f"({provenance.get('standards', '?')} standards).",
            "> These figures describe this corpus. They say nothing about the",
            "> 197-standard dataset, and must not be quoted as its accuracy.",
            "",
        ]

    lines += [
        f"- generated: {generated}",
        f"- cases: `{cases_path}`",
        f"- retriever: `{report.retriever or 'unknown'}`",
        f"- retrieval samples: {report.latency_samples}",
        f"- end-to-end RAG samples: {len(report.rag_latencies)}",
        "",
        "## Report",
        "",
        "```",
        format_report(report, show_misses=10).rstrip(),
        "```",
        "",
    ]

    if ablation_rows_data:
        lines += ["## Ablation", "",
                  "| config | Hit@1 | Hit@5 | MRR@5 | exact edition | hard Hit@5 | P50 ms | P95 ms |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for row in ablation_rows_data:
            lines.append(
                f"| `{row['config']}` | {row['hit@1']:.4f} | {row['hit@5']:.4f} | "
                f"{row['mrr@5']:.4f} | {row['exact_edition']:.4f} | "
                f"{row['hard_hit@5']:.4f} | {row['latency_p50_ms']} | "
                f"{row['latency_p95_ms']} |"
            )
        lines += ["",
                  "End-to-end hit rates (`hit@*_end_to_end` in `ablation.csv`) count "
                  "cases whose standard the corpus does not hold as misses; the "
                  "columns above are covered-only.", ""]

    # Targets belong in the artifact, not only in the brief, so a reader can see
    # which of these are assertions about the system and which are observations.
    lines += [
        "## Targets versus measurements",
        "",
        "| metric | target | measured | status |",
        "| --- | --- | --- | --- |",
        _target_row("superseded-first violation rate", 0.0,
                    report.superseded_violation_rate, lower_is_better=True),
        _target_row("superseded exposure in recommend mode", 0.0,
                    report.superseded_exposure_rate, lower_is_better=True),
        _target_row("out-of-scope rejection accuracy", 1.0,
                    report.rejection_accuracy, lower_is_better=False,
                    applicable=bool(report.rejections)),
        _target_row("invalid citation rate (extractive)", 0.0,
                    report.invalid_citation_rate, lower_is_better=True),
        "",
        "A target is a commitment; a measurement is an observation about one "
        "corpus. The two supersession targets are hard zero and are gated in CI. "
        "The hit rates are not targets -- there is no agreed number for a corpus "
        "this size, and picking one would invent an expectation.",
        "",
    ]
    return "\n".join(lines)


def _target_row(metric: str, target: float, measured: float, *,
                lower_is_better: bool, applicable: bool = True) -> str:
    if not applicable:
        return f"| {metric} | {target:g} | not applicable | n/a |"
    passed = measured <= target if lower_is_better else measured >= target
    return (f"| {metric} | {target:g} | {measured:.4f} | "
            f"{'met' if passed else 'MISSED'} |")


def write_artifacts(
    report: EvalReport,
    *,
    out_dir: Path | str = DEFAULT_RESULTS_DIR,
    cases_path: str = "",
    ablation: Optional[Sequence[tuple[AblationConfig, EvalReport]]] = None,
) -> dict[str, Path]:
    """Write the five artifacts and return their paths."""
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)

    rows = ablation_rows(ablation) if ablation else []
    payload = report.as_dict()
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    payload["cases_file"] = cases_path
    if ablation:
        payload["ablation"] = rows
        payload["ablation_configs"] = [asdict(config) for config, _ in ablation]

    written: dict[str, Path] = {}

    path = directory / "latest.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    written["latest.json"] = path

    path = directory / "latest.md"
    path.write_text(_markdown(report, cases_path=cases_path, ablation_rows_data=rows),
                    encoding="utf-8")
    written["latest.md"] = path

    failures = failure_records(report)
    path = directory / "failures.jsonl"
    path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n"
                            for record in failures), encoding="utf-8")
    written["failures.jsonl"] = path

    path = directory / "missing_corpus_standards.json"
    path.write_text(json.dumps({
        "corpus": {"standards": report.corpus_size, "chunks": report.corpus_chunks},
        "scored_cases": len(report.scoring),
        "covered_cases": len(report.answerable),
        "coverage": round(report.coverage, 4),
        "provenance": report.provenance,
        "missing": [
            {"designation": designation, "cases": ids, "case_count": len(ids)}
            for designation, ids in report.missing_standards().items()
        ],
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    written["missing_corpus_standards.json"] = path

    path = directory / "ablation.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    written["ablation.csv"] = path

    return written


def render_artifacts(written: dict[str, Path], out_dir: Path | str,
                     ablation_text: str = "") -> str:
    """What the CLI prints after writing: where the files are, and what is in them."""
    lines = [f"artifacts written to {out_dir}"]
    for name, path in written.items():
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        lines.append(f"  {name:<32}{size:>8} bytes")
    if ablation_text:
        lines += ["", ablation_text.rstrip()]
    return "\n".join(lines) + "\n"
