"""Build the vector store from ``bis_data``. Part 1 of the plan, done correctly.

    python -m bis_rag.build_vector_store                    # offline default
    python -m bis_rag.build_vector_store --embedder st:BAAI/bge-large-en-v1.5
    python -m bis_rag.build_vector_store --backend json --limit 200   # smoke test

What this does differently from the ``build_chromadb.py`` draft it replaces
----------------------------------------------------------------------------
The draft read ``chunk.get("text", chunk.get("content", ""))`` and
``chunk.get("is_number")``. None of those keys exist in
``chunked_documents.jsonl`` -- the real ones are ``chunk`` and ``designation``.
Every document would therefore have embedded as a bare metadata header with no
content, and the script would still have printed ``ChromaDB READY!``. Three
changes make that impossible:

* text comes from :class:`~bis_rag.schema.Chunk`, which knows the real field
  names and fails loudly if the text field is broadly empty;
* progress is reported as *characters embedded*, so a run that embeds headers
  only is visibly wrong (a healthy run embeds tens of millions of characters);
* a verification pass runs real queries at the end and prints the actual
  passages, not just similarity numbers.

It also writes two collections as planned -- ``bis_chunks`` for passage
retrieval, ``bis_standards`` for "what is IS 1239?" -- and preserves integer
years and booleans as native types so metadata filters work.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

from .data import BisData, default_data_dir
from .hybrid import DEFAULT_STORE_DIRNAME
from .embeddings import Embedder, describe, get_embedder
from .schema import SchemaError
from .vectorstore import CHUNK_COLLECTION, STANDARD_COLLECTION, open_store, reset_store

log = logging.getLogger(__name__)

__all__ = ["BuildConfig", "BuildReport", "build", "main"]

#: Queries that exercise the corpus at different levels of abstraction. Run
#: after every build so a regression in the data shows up as an obviously
#: wrong top hit rather than as a silently worse user experience.
VERIFY_QUERIES: tuple[str, ...] = (
    "cement for construction",
    "drinking water quality",
    "steel reinforcement bars for concrete",
)


@dataclass
class BuildConfig:
    data_dir: Path = field(default_factory=default_data_dir)
    store_dir: Optional[Path] = None
    embedder: str = "hash"
    backend: str = "auto"
    batch_size: int = 64
    #: Cap on indexed items per collection; ``None`` means everything.
    limit: Optional[int] = None
    force: bool = False
    verify: bool = True
    metric: str = "cosine"
    #: Skip superseded standards in the *standards* collection. Off by default:
    #: the compliance checker needs to find them to say "this is outdated".
    current_only: bool = False


@dataclass
class BuildReport:
    backend: str = ""
    store_dir: str = ""
    embedder: str = ""
    embedder_semantic: bool = False
    chunks_indexed: int = 0
    standards_indexed: int = 0
    characters_embedded: int = 0
    skipped_short: int = 0
    duration_s: float = 0.0
    coverage: list[str] = field(default_factory=list)
    verification: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "backend": self.backend,
            "store_dir": self.store_dir,
            "embedder": self.embedder,
            "chunks_indexed": self.chunks_indexed,
            "standards_indexed": self.standards_indexed,
            "characters_embedded": self.characters_embedded,
            "skipped_short": self.skipped_short,
            "duration_s": round(self.duration_s, 2),
            "coverage": self.coverage,
        }


def _progress(label: str, done: int, total: int, started: float, extra: str = "") -> None:
    """Single-line progress with ETA. No tqdm dependency on purpose."""
    elapsed = max(1e-6, time.time() - started)
    rate = done / elapsed
    remaining = (total - done) / rate if rate else 0.0
    pct = 100.0 * done / total if total else 100.0
    sys.stderr.write(
        f"\r  {label}: {done}/{total} ({pct:5.1f}%) "
        f"{rate:6.1f}/s  eta {remaining:5.1f}s {extra}"
    )
    sys.stderr.flush()


def _flush() -> None:
    sys.stderr.write("\r" + " " * 100 + "\r")
    sys.stderr.flush()


def _iter_batches(items: Sequence, size: int) -> Iterable[Sequence]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _index_chunks(data: BisData, store, embedder: Embedder, config: BuildConfig,
                  report: BuildReport) -> None:
    chunks = data.chunks()
    if config.limit:
        chunks = chunks[:config.limit]
    if not chunks:
        raise SchemaError("no chunks to index")

    started = time.time()
    for batch_no, batch in enumerate(_iter_batches(chunks, config.batch_size), 1):
        # Two different strings, deliberately:
        #   `passages` is what a user reads back in a citation -- clean prose;
        #   `embed_texts` is what the model sees -- metadata header + passage.
        # Storing the header in the document field instead would put
        # "IS Code: ... Title: ..." in front of every quote in the UI.
        passages = [c.text for c in batch]
        embed_texts = [c.embedding_text() for c in batch]
        vectors = embedder.encode(embed_texts, batch_size=len(embed_texts))
        store.add(
            ids=[c.chunk_id for c in batch],
            texts=passages,
            metadatas=[c.as_metadata() for c in batch],
            embeddings=vectors,
        )
        report.chunks_indexed += len(batch)
        report.characters_embedded += sum(len(t) for t in embed_texts)
        if batch_no % 4 == 0 or report.chunks_indexed >= len(chunks):
            _progress("chunks", report.chunks_indexed, len(chunks), started,
                      extra=f"{report.characters_embedded / 1e6:.1f} Mchar")
    _flush()
    store.finalize()


def _index_standards(data: BisData, store, embedder: Embedder, config: BuildConfig,
                     report: BuildReport) -> None:
    standards = data.standards()
    if config.current_only:
        standards = [s for s in standards if s.is_current]
    if config.limit:
        standards = standards[:config.limit]
    if not standards:
        return

    started = time.time()
    for batch_no, batch in enumerate(_iter_batches(standards, config.batch_size), 1):
        bodies = [s.summary or f"{s.designation} -- {s.title}" for s in batch]
        embed_texts = [s.embedding_text() for s in batch]
        vectors = embedder.encode(embed_texts, batch_size=len(embed_texts))
        store.add(
            ids=[s.canonical or f"std_{batch_no}_{i}" for i, s in enumerate(batch)],
            texts=bodies,
            metadatas=[s.as_metadata() for s in batch],
            embeddings=vectors,
        )
        report.standards_indexed += len(batch)
        report.characters_embedded += sum(len(t) for t in embed_texts)
        if batch_no % 4 == 0 or report.standards_indexed >= len(standards):
            _progress("standards", report.standards_indexed, len(standards), started)
    _flush()
    store.finalize()


def verify(store, embedder: Embedder, *, n: int = 3) -> list[str]:
    """Run the sample queries and return printable lines.

    Deliberately not a test assertion: what counts as a good hit depends on the
    embedder. It is a smoke check that the store answers at all, and a human
    reading the output can see instantly whether the passages are real.
    """
    lines: list[str] = []
    for query in VERIFY_QUERIES:
        vector = embedder.encode_one(query, is_query=True)
        hits = store.query(vector, n_results=n)
        if not hits:
            lines.append(f"  {query!r}\n     no results")
            continue
        lines.append(f"  {query!r}")
        for hit in hits:
            preview = " ".join(hit.text.split())[:90]
            lines.append(f"     {hit.score:6.3f}  {hit.designation:<26} {hit.title[:38]}")
            lines.append(f"              {preview}")
    return lines


def build(config: BuildConfig) -> BuildReport:
    report = BuildReport()
    started = time.time()

    data = BisData(config.data_dir)
    if not data.exists("chunks"):
        raise SchemaError(
            f"{data.root} has no rag/chunked_documents.jsonl.\n"
            f"  bis_data/ is gitignored, so a fresh clone does not include it.\n"
            f"  generate it with:  cd bis_scraper && python create_rag_dataset.py\n"
            f"  or set:            export BIS_DATA_DIR=/path/to/bis_data\n"
            f"  files present:     "
            f"{', '.join(k for k in ('chunks','knowledge_base','search_corpus','search_index') if data.exists(k)) or 'none'}"
        )

    # Must match HybridSearch's default exactly. When the two disagreed
    # (a sibling directory here, a nested one there) `build` wrote a store that
    # `search` never looked in, and dense retrieval silently went missing while
    # BM25 kept returning plausible results.
    store_dir = Path(config.store_dir) if config.store_dir else data.root / DEFAULT_STORE_DIRNAME
    if config.force and store_dir.exists():
        reset_store(store_dir)
    store_dir.mkdir(parents=True, exist_ok=True)

    embedder = get_embedder(config.embedder)
    backend = config.backend
    if backend == "auto":
        from .vectorstore import available_backends
        backend = available_backends()[0]

    report.backend = backend
    report.store_dir = str(store_dir)
    report.embedder = describe(embedder)
    report.embedder_semantic = embedder.semantic

    print("Building vector store")
    print(f"  data       : {data.root}")
    print(f"  store      : {store_dir}  (backend={backend})")
    print(f"  embedder   : {report.embedder}")
    if not embedder.semantic:
        print("  note       : this embedder is LEXICAL. Retrieval will behave like a")
        print("               keyword search. Re-run with --embedder st:BAAI/bge-large-en-v1.5")
        print("               (or api:<model>) on a machine with the model available")
        print("               for real semantic retrieval.")
    print()

    common = dict(backend=backend, dim=embedder.dim, fingerprint=embedder.fingerprint,
                  embedder_name=embedder.name, metric=config.metric, create=True)

    chunk_store = open_store(store_dir, CHUNK_COLLECTION, **common)
    _index_chunks(data, chunk_store, embedder, config, report)

    if data.exists("knowledge_base") or data.exists("search_corpus") or data.exists("merged_standards"):
        standard_store = open_store(store_dir, STANDARD_COLLECTION, **common)
        _index_standards(data, standard_store, embedder, config, report)
    else:
        standard_store = None
        print("  standards  : skipped (no knowledge_base / search_corpus / merged_standards)")

    report.coverage = [str(c) for c in data.chunk_coverage()]
    report.duration_s = time.time() - started

    if config.verify and chunk_store.count():
        print("\nVerification (top hits per sample query):")
        report.verification = verify(chunk_store, embedder)
        for line in report.verification:
            print(line)

    # A store that embedded almost no characters is the exact failure the old
    # script shipped silently, so it is now a hard error.
    mean_chars = report.characters_embedded / max(1, report.chunks_indexed + report.standards_indexed)
    if mean_chars < 200:
        raise SchemaError(
            f"only {mean_chars:.0f} characters embedded per document "
            f"({report.characters_embedded:,} total for "
            f"{report.chunks_indexed + report.standards_indexed:,} documents).\n"
            f"  Real chunks average well over 1,000 characters. This means the text "
            f"field came back empty -- check the coverage report below and compare "
            f"against the keys in chunked_documents.jsonl.\n"
            f"  coverage: " + "; ".join(report.coverage)
        )

    print(f"\nDone in {report.duration_s:.1f}s")
    print(f"  chunks indexed    : {report.chunks_indexed:,}")
    print(f"  standards indexed : {report.standards_indexed:,}")
    print(f"  characters        : {report.characters_embedded:,} "
          f"({mean_chars:,.0f} per document)")
    print("  field coverage    :")
    for line in report.coverage:
        print(f"      {line}")
    (store_dir / "build_report.json").write_text(
        json.dumps(report.as_dict(), indent=2), encoding="utf-8")
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bis-rag build",
        description="Embed bis_data into a persistent vector store.")
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="bis_data directory (default: $BIS_DATA_DIR or bis_scraper/bis_data)")
    parser.add_argument("--store-dir", type=Path, default=None,
                        help="where to write the store (default: <data-dir>/vector_store)")
    parser.add_argument("--embedder", default="hash",
                        help="hash | hash:<dim> | st:<hf-model> | api:<model>")
    parser.add_argument("--backend", default="auto", choices=["auto", "chroma", "json"])
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--limit", type=int, default=None,
                        help="index at most N items per collection (smoke tests)")
    parser.add_argument("--force", action="store_true", help="delete an existing store first")
    parser.add_argument("--no-verify", action="store_true", help="skip the sample queries")
    parser.add_argument("--current-only", action="store_true",
                        help="exclude superseded standards from the standards collection")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    config = BuildConfig(
        data_dir=args.data_dir or default_data_dir(),
        store_dir=args.store_dir,
        embedder=args.embedder,
        backend=args.backend,
        batch_size=args.batch_size,
        limit=args.limit,
        force=args.force,
        verify=not args.no_verify,
        current_only=args.current_only,
    )
    try:
        build(config)
    except SchemaError as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
