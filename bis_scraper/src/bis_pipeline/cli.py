"""Command-line entry point.

    python -m bis_pipeline archive  --max-items 200
    python -m bis_pipeline mandatory
    python -m bis_pipeline merge
    python -m bis_pipeline index
    python -m bis_pipeline query "submersible pump"
    python -m bis_pipeline all --max-items 200
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .archive_scraper import scrape as scrape_archive
from .http import DEFAULT_USER_AGENT, HttpClient, HttpError
from .index import SearchIndex
from .mandatory import scrape_mandatory
from .coverage import build_corpus_index, report as coverage_report, summarise, write_report
from .merger import (
    archive_items_from_jsonl,
    from_archive_items,
    from_mandatory,
    from_portal_rows,
    merge,
    write_outputs,
)

log = logging.getLogger("bis_pipeline")

DEFAULT_DATA = Path("bis_data")


def build_client(args) -> HttpClient:
    return HttpClient(
        user_agent=args.user_agent,
        timeout=args.timeout,
        min_interval=args.min_interval,
        cache_dir=Path(args.data_dir) / "http_cache",
    )


# ----------------------------------------------------------------------
# subcommands
# ----------------------------------------------------------------------
def cmd_archive(args) -> int:
    client = build_client(args)
    out = Path(args.data_dir) / "archive"
    items = scrape_archive(
        client, out, query=args.query, max_items=args.max_items,
        download_text=not args.no_text, download_pdfs=args.pdfs,
        on_progress=lambda n: print(f"\r  {n} items", end="", flush=True),
    )
    print(f"\n  {len(items)} items -> {out / 'items.jsonl'}")
    return 0


def cmd_mandatory(args) -> int:
    client = build_client(args)
    # `--urls` defaults to an empty list, which must mean "use the defaults",
    # not "scrape nothing". Passing () would silently produce an empty report.
    report = scrape_mandatory(client, urls=tuple(args.urls) or None)
    if not report.tables_seen:
        print("  warning: no HTML tables found -- BIS may have changed their markup")
    out = Path(args.data_dir) / "mandatory"
    out.mkdir(parents=True, exist_ok=True)
    (out / "mandatory.json").write_text(json.dumps(
        [{
            "designation": s.designation.format(),
            "canonical": s.designation.canonical,
            "title": s.title,
            "scheme": s.scheme,
            "source_url": s.source_url,
        } for s in report.standards], indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  {report.as_dict()}")
    print(f"  {len(report.standards)} IS numbers -> {out / 'mandatory.json'}")
    return 0


def cmd_merge(args) -> int:
    data = Path(args.data_dir)
    sources: list = []

    archive_jsonl = data / "archive" / "items.jsonl"
    if archive_jsonl.exists():
        items = archive_items_from_jsonl(archive_jsonl)
        sources.append(from_archive_items(items, text_dir=data / "archive" / "text",
                                          pdf_dir=data / "archive" / "pdf"))
        print(f"  archive.org : {len(sources[-1])} records")
    else:
        print(f"  archive.org : skipped ({archive_jsonl} not found)")

    mandatory_json = data / "mandatory" / "mandatory.json"
    if mandatory_json.exists():
        from .iscode import parse_designation
        from .mandatory import MandatoryStandard

        rows = json.loads(mandatory_json.read_text(encoding="utf-8"))
        standards = []
        for row in rows:
            desig = parse_designation(row["designation"])
            if desig:
                standards.append(MandatoryStandard(
                    designation=desig, title=row.get("title", ""),
                    scheme=row.get("scheme", ""), source_url=row.get("source_url", "")))
        sources.append(from_mandatory(standards))
        print(f"  BIS QCO     : {len(sources[-1])} records")

    if args.portal_json and Path(args.portal_json).exists():
        rows = json.loads(Path(args.portal_json).read_text(encoding="utf-8"))
        sources.append(from_portal_rows(rows))
        print(f"  BIS portal  : {len(sources[-1])} records")

    if not sources:
        print("  nothing to merge -- run `archive` or `mandatory` first")
        return 1

    records = merge(*sources)
    current = sum(1 for r in records if r.is_current)
    compulsory = sum(1 for r in records if r.is_compulsory)
    with_text = sum(1 for r in records if r.has_full_text)

    paths = write_outputs(records, data / "merged", write_xlsx=args.xlsx)
    print(f"\n  {len(records)} unique standards "
          f"({current} current, {with_text} with full text, {compulsory} QCO-mandated)")
    for kind, path in paths.items():
        print(f"    {kind:5} {path}")
    return 0


def cmd_index(args) -> int:
    from .merger import StandardRecord

    data = Path(args.data_dir)
    jsonl = data / "merged" / "merged_standards.jsonl"
    if not jsonl.exists():
        print(f"  {jsonl} not found -- run `merge` first")
        return 1

    records = []
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(StandardRecord(**json.loads(line)))

    embed_fn = _load_embed_fn(args.embed_model)
    index = SearchIndex(dim=args.dim).build(records, embed_fn=embed_fn,
                                           index_chars=args.index_chars)
    out = index.save(data / "index" / "search_index.json")
    print(f"  indexed {len(index)} documents ({'dense' if index.dense else 'tf-idf'}) -> {out}")
    return 0


def cmd_query(args) -> int:
    path = Path(args.data_dir) / "index" / "search_index.json"
    if not path.exists():
        print(f"  {path} not found -- run `index` first")
        return 1

    index = SearchIndex.load(path, embed_fn=_load_embed_fn(args.embed_model))
    for query in args.queries:
        print(f"\n  '{query}'")
        print("  " + "-" * 66)
        hits = index.search(query, k=args.k, min_score=args.min_score,
                            current_only=not args.include_superseded)
        if not hits:
            print("    (no matches)")
        for i, hit in enumerate(hits, 1):
            print(f"  {i}. {hit.designation}  (score {hit.score:.3f})")
            print(f"     {hit.title[:88]}")
            flags = []
            if hit.is_compulsory:
                flags.append("QCO-mandated")
            if not hit.is_current:
                flags.append(f"superseded by {hit.superseded_by}")
            if flags:
                print(f"     ! {', '.join(flags)}")
            if hit.archive_url:
                print(f"     {hit.archive_url}")
    return 0


def cmd_coverage(args) -> int:
    """Which QCO-mandated standards are already free to index?"""
    data = Path(args.data_dir)
    mandatory_json = data / "mandatory" / "mandatory.json"
    if not mandatory_json.exists():
        print(f"  {mandatory_json} not found -- run `mandatory` first")
        return 1

    from .iscode import parse_designation
    from .mandatory import MandatoryStandard

    rows = json.loads(mandatory_json.read_text(encoding="utf-8"))
    standards = []
    for row in rows:
        desig = parse_designation(row["designation"])
        if desig:
            standards.append(MandatoryStandard(
                designation=desig, title=row.get("title", ""),
                product_category=row.get("product_category", ""),
                scheme=row.get("scheme", ""), source_url=row.get("source_url", "")))

    client = build_client(args)
    print(f"  listing archive.org corpus (this is ~111 requests)...")
    corpus = build_corpus_index(client, max_items=args.max_items)

    result = coverage_report(standards, corpus)
    stats = summarise(result)
    paths = write_report(result, data / "coverage")

    print(f"\n  QCO-mandated standards : {stats['qco_standards']}")
    print(f"  already free (CC0)     : {stats['held_in_cc0_corpus']}  ({stats['coverage_pct']}%)")
    print(f"  need registration      : {stats['not_held']}")
    for name, path in paths.items():
        print(f"    {name:12} {path}")
    print("\n  'need registration' = obtain from https://standardsbis.bsbedge.com")
    print("  after registering; BIS provides Indian Standards there free of charge.")
    return 0


def cmd_all(args) -> int:
    for fn in (cmd_archive, cmd_mandatory, cmd_merge, cmd_index):
        print(f"\n== {fn.__name__[4:]} ==")
        try:
            code = fn(args)
        except HttpError as exc:
            print(f"  network failure: {exc}")
            return 2
        if code:
            return code
    return cmd_query(args)


def _load_embed_fn(model_name: str):
    """Optional dense backend. Returns None (=> TF-IDF) when unavailable."""
    if not model_name or model_name == "tfidf":
        return None
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        log.warning("sentence-transformers not installed; falling back to TF-IDF")
        return None
    log.info("loading embedding model %s (this downloads ~1.3GB on first use)", model_name)
    model = SentenceTransformer(model_name)
    return lambda texts: model.encode(texts, show_progress_bar=False).tolist()


# ----------------------------------------------------------------------
# argparse
# ----------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bis-pipeline", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA))
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--min-interval", type=float, default=1.0,
                        help="minimum seconds between requests to one host")
    parser.add_argument("-v", "--verbose", action="store_true")

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("archive", help="scrape archive.org's gov.in.is.* collection")
    p.add_argument("--max-items", type=int, default=None,
                   help="cap the run (the full collection is ~22k items)")
    p.add_argument("--query", default="identifier:gov.in.is.*")
    p.add_argument("--no-text", action="store_true", help="metadata only")
    p.add_argument("--pdfs", action="store_true", help="also download PDFs (slow, large)")
    p.set_defaults(func=cmd_archive)

    p = sub.add_parser("mandatory", help="scrape BIS compulsory-certification IS numbers")
    p.add_argument("--urls", nargs="*", default=[],
                   help="override the BIS pages to read")
    p.set_defaults(func=cmd_mandatory)

    p = sub.add_parser("merge", help="merge sources into one dataset")
    p.add_argument("--portal-json", default=None,
                   help="optional JSON list of {is_number,title,status,committee}")
    p.add_argument("--xlsx", action="store_true")
    p.set_defaults(func=cmd_merge)

    p = sub.add_parser("index", help="build the search index")
    p.add_argument("--dim", type=int, default=1 << 16)
    p.add_argument("--index-chars", type=int, default=20_000)
    p.add_argument("--embed-model", default="tfidf",
                   help="'tfidf' (default, no download) or a sentence-transformers model")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("query", help="query the index")
    p.add_argument("queries", nargs="+")
    p.add_argument("-k", type=int, default=5)
    p.add_argument("--embed-model", default="tfidf")
    p.add_argument("--include-superseded", action="store_true")
    p.add_argument("--min-score", type=float, default=0.05)
    p.set_defaults(func=cmd_query)

    p = sub.add_parser("coverage", help="report which QCO standards are already free to index")
    p.add_argument("--max-items", type=int, default=None,
                   help="cap the corpus listing (omit for the full ~22k)")
    p.set_defaults(func=cmd_coverage)

    p = sub.add_parser("all", help="archive -> mandatory -> merge -> index -> query")
    p.add_argument("--max-items", type=int, default=200)
    p.add_argument("--query", default="identifier:gov.in.is.*")
    p.add_argument("--no-text", action="store_true")
    p.add_argument("--pdfs", action="store_true")
    p.add_argument("--urls", nargs="*", default=[])
    p.add_argument("--portal-json", default=None)
    p.add_argument("--xlsx", action="store_true")
    p.add_argument("--dim", type=int, default=1 << 16)
    p.add_argument("--index-chars", type=int, default=20_000)
    p.add_argument("--embed-model", default="tfidf")
    p.add_argument("queries", nargs="*", default=["drinking water quality"])
    p.set_defaults(func=cmd_all)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
