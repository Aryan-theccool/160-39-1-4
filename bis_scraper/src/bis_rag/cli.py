"""``bis-rag`` command line: doctor, build, search, ask, analyze.

    bis-rag doctor                       what data and dependencies are present
    bis-rag build                        embed bis_data into a vector store
    bis-rag search "drinking water"      hybrid retrieval, with provenance
    bis-rag ask "is cement mandatory?"   full RAG answer
    bis-rag analyze "IS 456 latest"      how the query was understood

``analyze`` exists because retrieval bugs are almost never in the retriever.
They are in the query being parsed into the wrong filters, and printing the
parsed query is the fastest way to see that.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional, Sequence

from .data import BisData, default_data_dir
from .doctor import FixtureDataError, inspect_provenance, require_real_corpus
from .embeddings import describe, get_embedder
from .schema import SchemaError

log = logging.getLogger(__name__)

__all__ = ["main"]

_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_RESET = "\033[0m"


def _supports_colour() -> bool:
    return sys.stdout.isatty()


def _c(text: str, colour: str) -> str:
    return f"{colour}{text}{_RESET}" if _supports_colour() else text


# ----------------------------------------------------------------------
def cmd_doctor(args: argparse.Namespace) -> int:
    """Report the resolved paths, the corpus, the vector store and the environment.

    The corpus and store facts come from :mod:`bis_rag.doctor`, which is also
    what the evaluator gates on, so the two cannot disagree about how many
    standards are on disk. Everything else here is inventory: which files exist,
    which optional dependencies are importable, which embedders and generators
    are usable, and how well-populated the chunks are.
    """
    from .doctor import (
        doctor_payload,
        format_doctor,
        inspect_corpus,
        inspect_provenance,
        inspect_store,
    )
    from .vectorstore import available_backends

    data = BisData(args.data_dir)
    store_root = Path(args.store_dir) if args.store_dir else (data.root / "vector_store")
    corpus = inspect_corpus(data)
    provenance = inspect_provenance(data, standards=corpus.standards or None)
    store = inspect_store(store_root, backend=args.backend)

    payload = doctor_payload(corpus, store, provenance, embedder=args.embedder,
                             backends=available_backends())
    # Attach the inventory so --json is a complete picture rather than a
    # differently-shaped subset of the terminal output.
    payload["files"] = [
        {"key": st.key, "path": str(st.path), "exists": st.exists,
         "bytes": st.size if st.exists else 0}
        for st in data.availability()
    ]
    payload["generator"] = "extractive" if not _llm_configured() else "llm"

    # A missing corpus is the one thing doctor must not be relaxed about: every
    # number below is then either absent or from somewhere else. Exit 2 rather
    # than 0, so a CI step or a shell `&&` notices. A *fixture* corpus is a
    # warning and exit 0 -- it is a legitimate thing to inspect, just not to
    # quote -- and `bis-rag eval --production` is where it becomes fatal.
    exit_code = 0 if (corpus.exists and not corpus.error) else 2

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return exit_code

    print(format_doctor(payload))

    print("\nFiles:")
    for status in data.availability():
        colour = _GREEN if status.exists else _DIM
        print("  " + _c(str(status), colour))

    print("\nPython dependencies:")
    backends = available_backends()
    print(f"  vector store backends : {', '.join(backends)}"
          + ("" if "chroma" in backends else _c("   (chromadb not installed -> using json)", _YELLOW)))
    import importlib.util

    if importlib.util.find_spec("sentence_transformers") is not None:
        print("  sentence-transformers : present (--embedder st:<model> available)")
    else:
        print("  sentence-transformers : absent "
              + _c("(semantic embeddings unavailable; use --embedder hash or api:<model>)", _DIM))

    print("\nEmbedders:")
    for spec in ("hash", "st:BAAI/bge-large-en-v1.5", "api:text-embedding-3-small"):
        try:
            embedder = get_embedder(spec)
            print(f"  {spec:<32} {describe(embedder)}")
        except Exception as exc:
            print(f"  {spec:<32} {_c('unavailable: ' + str(exc).splitlines()[0], _DIM)}")

    print("\nLLM for `bis-rag ask`:")
    from .rag import select_generator
    generator = select_generator(None)
    if generator.is_llm:
        print(f"  {generator.name} ({getattr(generator, 'model', '?')})")
    else:
        print(f"  {_c('none configured', _YELLOW)} -- answers will be extractive,")
        print("  so the citation metrics measure the template, not a model.")
        print("  set GROQ_API_KEY, OPENAI_API_KEY or OLLAMA_HOST for generated prose.")

    if data.exists("chunks") or data.exists("knowledge_base"):
        try:
            if data.exists("chunks"):
                print("\nChunk field coverage:")
                for entry in data.chunk_coverage():
                    flag = "" if entry.ratio > 0.9 else _c("  <- low", _YELLOW)
                    print(f"  {entry}{flag}")
        except SchemaError as exc:
            print(_c(f"\n  {exc}", _RED))
            return 2

    print("\nCompliance (QCO) data:")
    from .compliance import SEED_QCO
    if data.exists("mandatory"):
        print("  authoritative: bis_data/mandatory/mandatory.json")
    else:
        print(_c(f"  mandatory.json absent -> using the built-in seed list "
                 f"({len(SEED_QCO)} entries, UNVERIFIED)", _YELLOW))
        print("  run: python -m bis_pipeline mandatory")
    if exit_code:
        print(_c(f"\n  FATAL: no usable corpus at {data.root} -- nothing above "
                 f"describes real data. Set --data-dir.", _RED))
    return exit_code


def _llm_configured() -> bool:
    from .rag import select_generator
    try:
        return bool(select_generator(None).is_llm)
    except Exception:  # noqa: BLE001 - doctor must not fail over an env var
        return False


def cmd_build(args: argparse.Namespace) -> int:
    from .build_vector_store import BuildConfig, build
    return _run(lambda: build(BuildConfig(
        data_dir=args.data_dir or default_data_dir(),
        store_dir=args.store_dir,
        embedder=args.embedder,
        backend=args.backend,
        batch_size=args.batch_size,
        limit=args.limit,
        force=args.force,
        verify=not args.no_verify,
        current_only=args.current_only,
    )))


def cmd_search(args: argparse.Namespace) -> int:
    from .hybrid import HybridSearch, RetrievalConfig

    def run():
        data = BisData(args.data_dir)
        search = HybridSearch(data, store_dir=args.store_dir, embedder=args.embedder,
                              config=RetrievalConfig(top_k=args.top_k),
                              reranker=args.reranker)
        response = search.search(args.query, top_k=args.top_k)
        if args.json:
            print(json.dumps(response.as_dict(), indent=2, ensure_ascii=False))
            return response
        print(_c(f"\nquery: {response.query.raw}", _BOLD))
        print(f"intent      : {response.query.intent}")
        if response.query.designations:
            print("designations: " + ", ".join(d.format() for d in response.query.designations))
        if response.query.where():
            print(f"filters     : {json.dumps(response.query.where())}")
        if response.query.expansions:
            print(f"expansions  : {', '.join(response.query.expansions)}")
        print(f"reranker    : {response.reranker}")
        print(f"\n{len(response.results)} result(s)")
        for i, result in enumerate(response.results, 1):
            found = " ".join(f"{k}#{v}" for k, v in result.provenance.items())
            state = "" if result.is_current else _c("  SUPERSEDED", _YELLOW)
            print(f"\n{i:2}. {_c(result.designation, _BOLD)}  {result.title}{state}")
            print(f"    score {result.score:.4f}   found by {found}")
            if result.rerank_score is not None:
                print(f"    rerank {result.rerank_score:.3f}")
            print(f"    {' '.join(result.text.split())[:220]}")
        for warning in response.supersession_warnings:
            print(_c(f"\nwarning: {warning['message']}", _YELLOW))
        for note in response.notes:
            print(_c(f"note: {note}", _DIM))
        return response
    return _run(run)


def cmd_ask(args: argparse.Namespace) -> int:
    from .rag import RAGPipeline

    def run():
        data = BisData(args.data_dir)
        pipeline = RAGPipeline(data)
        answer = pipeline.answer(args.query, top_k=args.top_k,
                                 include_passages=args.passages)
        if args.json:
            print(json.dumps(answer.as_dict(include_passages=args.passages),
                             indent=2, ensure_ascii=False))
            return answer
        print(_c(f"\nQ: {answer.question}", _BOLD))
        print(f"mode={answer.mode}  generator={answer.generator}  intent={answer.intent}\n")
        print(answer.answer)
        if answer.citations:
            print(_c("\nCitations:", _BOLD))
            for citation in answer.citations:
                print(f"  - {citation.display()}")
        for warning in answer.warnings:
            print(_c(f"\nwarning: {warning}", _YELLOW))
        if answer.unsupported_citations:
            print(_c(f"\nUNVERIFIED citations: {', '.join(answer.unsupported_citations)}", _RED))
        for note in answer.notes:
            print(_c(f"note: {note}", _DIM))
        return answer
    return _run(run)


def cmd_compliance(args: argparse.Namespace) -> int:
    from .compliance import ComplianceChecker, render_html

    def run():
        data = BisData(args.data_dir)
        checker = ComplianceChecker(data)
        standards = list(args.standards or [])
        if not standards:
            # No explicit list: use what the pipeline would recommend for this
            # product, which is the common case for "am I compliant?".
            from .hybrid import HybridSearch
            search = HybridSearch(data, store_dir=args.store_dir, embedder="hash",
                                  reranker=args.reranker)
            response = search.search(args.product, top_k=args.top_k)
            standards = [r.designation for r in response.results if r.designation]
            if not args.json:
                # Only in human mode: `--json` must emit nothing but the document,
                # or it cannot be piped into anything.
                print(_c(f"\nUsing {len(standards)} standard(s) recommended for this "
                         f"product by hybrid search:", _BOLD))
                for designation in standards:
                    print(f"    {designation}")

        report = checker.analyze(args.product, standards, sector=args.sector)

        if args.html:
            output = Path(args.html)
            output.write_text(render_html(report), encoding="utf-8")
            # stderr: stdout is reserved for --json.
            print(f"HTML gap report -> {output}", file=sys.stderr)
        if args.json:
            print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
            return report

        print(_c(f"\n{report.grade} {report.grade_emoji()}   "
                 f"score {report.compliance_score:.2f}", _BOLD))
        print(f"product     : {report.product_description or '(not given)'}")
        print(f"sector      : {report.sector or '(not detected)'}")
        print(f"QCO list    : {report.qco_basis}")
        print(f"status      : {report.status()}")
        print(f"\nmandatory   : {report.total_mandatory} identified, "
              f"{len(report.mandatory_present)} present, "
              f"{len(report.mandatory_missing)} missing")
        for designation in report.mandatory_missing:
            print(_c(f"    MISSING  {designation}", _RED))
        if report.superseded_used:
            print("\nsuperseded editions in use:")
            for item in report.superseded_used:
                print(_c(f"    {item['used']}  ->  {item['replace_with']}", _YELLOW))
        for conflict in report.conflicts:
            print(_c(f"\nconflict: {conflict['detail']}", _YELLOW))
        if report.action_items:
            print(_c("\naction items:", _BOLD))
            for i, action in enumerate(report.action_items, 1):
                print(f"  {i}. {action}")
        if report.grade_capped_by:
            print(_c(f"\ngrade capped: {report.grade_capped_by}", _DIM))
        for note in report.notes:
            print(_c(f"note: {note}", _DIM))
        return report
    return _run(run)


def cmd_analyze(args: argparse.Namespace) -> int:
    from .query_processor import QueryProcessor

    def run():
        data = BisData(args.data_dir)
        processor = QueryProcessor(data)
        processed = processor.process(args.query)
        print(json.dumps({"vocabulary": processor.vocabulary_size(),
                          "processed": processed.as_dict()}, indent=2, ensure_ascii=False))
        return processed
    return _run(run)


def _run(function) -> int:
    try:
        function()
    except SchemaError as exc:
        print(f"\n{_c('error:', _RED)} {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    return 0


# ----------------------------------------------------------------------
def cmd_eval(args: argparse.Namespace) -> int:
    """Measure retrieval against the hand-written test set."""
    from .evaluate import (
        DEFAULT_CASES_PATH,
        ablation,
        evaluate,
        evaluate_answers,
        format_ablation,
        format_report,
        gate_failures,
        load_cases,
    )
    from .hybrid import HybridSearch, RetrievalConfig
    from .rag import RAGPipeline

    cases_path = args.cases or DEFAULT_CASES_PATH
    try:
        cases = load_cases(cases_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.limit:
        cases = cases[: args.limit]

    data = BisData(args.data_dir)
    # Ask the data contract what is missing rather than re-deriving it here.
    # `data.missing()` lists *optional* files too (the scraped QCO list, the
    # semantic indexes), so treating a non-empty result as fatal would refuse to
    # run on a perfectly usable corpus -- which is exactly what the first
    # version of this command did.
    try:
        data.chunks()
    except SchemaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # Provenance first: refuse to certify fixture data when a production number
    # was asked for. `allow_fixture` keeps the fixture able to exercise this very
    # path; without it the gate would be untestable.
    provenance = inspect_provenance(data, standards=len(data.standards()))
    if args.production and not provenance.certifiable:
        try:
            require_real_corpus(data, what="this evaluation",
                                allow_fixture=False,
                                standards=provenance.standards)
        except FixtureDataError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    if not provenance.certifiable:
        warning = provenance.warning()
        if warning:
            print(f"warning: {warning}", file=sys.stderr)

    search = HybridSearch(data, store_dir=args.store_dir, embedder=args.embedder,
                          config=RetrievalConfig(top_k=args.top_k),
                          reranker=args.reranker)

    report = evaluate(
        search, cases,
        top_k=args.top_k,
        repeats=args.repeats,
        check_supersession=not args.no_supersession_check,
    )
    report.provenance = provenance.as_dict()
    report.notes.append(f"cases file: {cases_path}")
    for name in data.missing():
        if name != "chunks":
            report.notes.append(
                f"optional input absent: {name} ({data.path(name).name}) -- "
                f"this does not affect retrieval, but it does affect features that use it"
            )

    if not args.no_answers:
        pipeline = RAGPipeline(data, search=search)
        evaluate_answers(pipeline, cases, report)

    if args.baseline:
        from .evaluate import compare
        degraded = HybridSearch(
            data, store_dir=args.store_dir, embedder=args.embedder,
            config=RetrievalConfig(top_k=args.top_k, use_tfidf=False, use_dense=False,
                                   rerank=False),
            reranker="none",
        )
        baseline = evaluate(search=degraded, cases=cases, top_k=args.top_k,
                            repeats=1, check_supersession=False)
        if args.json:
            report.baseline = baseline.as_dict()
        else:
            print(compare(report, baseline))

    ablation_result = None
    if args.ablation:
        def factory(config):
            """Build one ablation row's retriever. This module owns the store
            directory and embedder, so the eval module only gets a factory."""
            return HybridSearch(
                data, store_dir=args.store_dir, embedder=args.embedder,
                config=RetrievalConfig(
                    top_k=args.top_k, use_bm25=config.use_bm25,
                    use_tfidf=config.use_tfidf, use_dense=config.use_dense,
                    fusion=config.fusion, rerank=config.rerank,
                ),
                reranker=args.reranker if config.rerank else "none",
            )

        ablation_result = ablation(factory, cases, top_k=args.top_k,
                                   repeats=args.repeats)

    if args.json:
        payload = report.as_dict()
        if ablation_result:
            from .evaluate import ablation_rows
            payload["ablation"] = ablation_rows(ablation_result)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(format_report(report, show_misses=args.show_misses))
        if ablation_result:
            print()
            print(format_ablation(ablation_result))

    written = None
    if not args.no_artifacts:
        from .artifacts import DEFAULT_RESULTS_DIR, render_artifacts, write_artifacts

        out_dir = args.out_dir or DEFAULT_RESULTS_DIR
        written = write_artifacts(report, out_dir=out_dir, cases_path=str(cases_path),
                                  ablation=ablation_result)

    problems = gate_failures(
        report,
        max_superseded_violation=args.max_superseded,
        max_superseded_exposure=args.max_superseded_exposure,
        min_hit_rate_5=args.min_hit_rate_5,
        min_hit_rate_1=args.min_hit_rate_1,
        min_rejection_accuracy=args.min_rejection_accuracy,
        max_invalid_citations=args.max_invalid_citations,
    )

    if written and not args.json:
        print()
        print(render_artifacts(written, args.out_dir or "eval/results"))

    if problems and not args.allow_regression:
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        return 1
    for problem in problems:
        print(f"warning (allowed): {problem}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bis-rag",
        description="Retrieval engine over the BIS standards dataset "
                    "(vector store, hybrid search, RAG).")
    parser.add_argument("-q", "--quiet", action="store_true", help="suppress info logs")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_data(ap: argparse.ArgumentParser) -> None:
        ap.add_argument("--data-dir", type=Path, default=None,
                        help="bis_data directory (default $BIS_DATA_DIR or bis_scraper/bis_data)")
        ap.add_argument("--store-dir", type=Path, default=None,
                        help="vector store directory (default <data-dir>/vector_store)")

    p = sub.add_parser("doctor", help="report on data, dependencies and configuration")
    add_data(p)
    p.add_argument("--embedder", default="hash",
                   help="embedder whose compatibility with the store is reported")
    p.add_argument("--backend", default="auto", choices=["auto", "chroma", "json"],
                   help="vector store backend to open the collections with")
    p.add_argument("--json", action="store_true", help="emit the report as JSON")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("build", help="embed bis_data into a persistent vector store")
    add_data(p)
    p.add_argument("--embedder", default="hash",
                   help="hash | hash:<dim> | st:<hf-model> | api:<model>")
    p.add_argument("--backend", default="auto", choices=["auto", "chroma", "json"])
    p.add_argument("--batch-size", type=int, default=64)
    p.add_argument("--limit", type=int, default=None, help="cap items per collection (smoke test)")
    p.add_argument("--force", action="store_true", help="delete an existing store first")
    p.add_argument("--no-verify", action="store_true")
    p.add_argument("--current-only", action="store_true",
                   help="exclude superseded standards from the standards collection")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("search", help="hybrid search with provenance")
    add_data(p)
    p.add_argument("query")
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--embedder", default="hash")
    p.add_argument("--reranker", default="auto",
                   choices=["auto", "none", "lexical", "st:cross-encoder/ms-marco-MiniLM-L-6-v2"])
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("ask", help="full RAG answer with citations")
    add_data(p)
    p.add_argument("query")
    p.add_argument("--top-k", type=int, default=6)
    p.add_argument("--passages", action="store_true", help="include retrieved passages in JSON")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("compliance",
                       help="check standards against the QCO mandatory list")
    add_data(p)
    p.add_argument("product", help="product description, e.g. 'submersible pumpset'")
    p.add_argument("standards", nargs="*",
                   help="standards in use (default: those hybrid search recommends)")
    p.add_argument("--sector", default=None,
                   help="override sector detection (construction, electrical, ...)")
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--reranker", default="auto", choices=["auto", "none", "lexical"])
    p.add_argument("--html", metavar="PATH", default=None,
                   help="write the printable gap report")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_compliance)

    p = sub.add_parser("eval", help="retrieval evaluation against hand-written cases")
    add_data(p)
    p.add_argument("--production", action="store_true",
                   help="refuse to run (exit 2) unless the corpus is real: no "
                        "fixture marker and at least 50 standards")
    p.add_argument("--ablation", action="store_true",
                   help="additionally run the six retriever configurations")
    p.add_argument("--out-dir", type=Path, default=None,
                   help="where to write the artifacts (default eval/results)")
    p.add_argument("--no-artifacts", action="store_true",
                   help="do not write eval/results/*")
    p.add_argument("--max-superseded-exposure", type=float, default=0.0,
                   help="allowed share of cases where a withdrawn edition is "
                        "recommended (default 0.0)")
    p.add_argument("--min-rejection-accuracy", type=float, default=None,
                   help="minimum share of out-of-scope queries that must be declined")
    p.add_argument("--max-invalid-citations", type=float, default=None,
                   help="allowed share of citations that do not resolve (replaces "
                        "--max-hallucination, which is still accepted)")
    p.add_argument("--cases", type=Path, default=None,
                   help="JSONL test set (default: eval/retrieval_cases.jsonl)")
    p.add_argument("--top-k", type=int, default=10,
                   help="results per query; must be >= 10 to report Hit Rate @10")
    p.add_argument("--repeats", type=int, default=1,
                   help="run each query N times, for latency samples only")
    p.add_argument("--limit", type=int, default=None, help="use only the first N cases")
    p.add_argument("--reranker", default="auto", choices=["auto", "none", "lexical"])
    p.add_argument("--embedder", default=None,
                   help="embedder for the dense retriever (default: auto-detect)")
    p.add_argument("--baseline", action="store_true",
                   help="also run BM25-only and compare, to show the pipeline earns its keep")
    p.add_argument("--show-misses", type=int, default=10)
    p.add_argument("--no-answers", action="store_true",
                   help="skip the answer pass (hallucination + citation measurement)")
    p.add_argument("--no-supersession-check", action="store_true",
                   help="skip the ranking check that returns withdrawn editions")
    p.add_argument("--max-superseded", type=float, default=0.0,
                   help="allowed superseded violation rate (default 0: none)")
    p.add_argument("--max-hallucination", type=float, default=None)
    p.add_argument("--min-hit-rate-5", type=float, default=None)
    p.add_argument("--min-hit-rate-1", type=float, default=None)
    p.add_argument("--allow-regression", action="store_true",
                   help="report threshold breaches but exit 0")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("analyze", help="show how a query is parsed (filters, intent, expansions)")
    add_data(p)
    p.add_argument("query")
    p.set_defaults(func=cmd_analyze)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
