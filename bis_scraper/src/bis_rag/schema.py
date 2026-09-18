"""The data contract between ``bis_data/`` and the RAG engine.

Why this module exists
----------------------
The RAG files are written by ``create_rag_dataset.py`` and ``create_semantic_index.py``
at the repository root. Their field names are **not** the names you would guess:

======================  ==========================  =============================
Guessed name            Actual field                Written by
======================  ==========================  =============================
``text`` / ``content``  ``chunk``                   ``create_rag_dataset.py:64``
``is_number``           ``designation``             ``create_rag_dataset.py:60``
``status``              ``is_current`` (bool)       ``create_rag_dataset.py:69``
``text`` (KB entry)     *absent* -- KB entries carry ``keywords`` only; the
                        summary text lives in ``search_corpus.jsonl``
                        as ``text_snippet``
======================  ==========================  =============================

Reading a file with the wrong key does not raise. It returns ``None``, which
flows into the embedding text as an empty string, and the pipeline happily
indexes 9,043 vectors of near-identical header boilerplate. Semantic search
then returns confident nonsense. This module makes that failure mode
**impossible**: every loader reports field coverage and refuses to return a
dataset in which a load-bearing field is broadly empty.

Tolerance is deliberate too. ``chunk`` and ``text`` are both accepted, because
downstream users regenerate these files and a hard failure over a rename is
its own kind of unhelpful. The rule is: *accept aliases, but never accept
silence*. If we had to fall back to an alias, that is recorded in the coverage
report and surfaced by the CLI.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

__all__ = [
    "SchemaError",
    "FieldCoverage",
    "coverage",
    "load_json",
    "load_jsonl",
    "Chunk",
    "Standard",
    "first_present",
    "as_bool",
    "as_int",
    "as_text",
]


class SchemaError(Exception):
    """Raised when a dataset does not match the contract in a load-bearing way.

    Carries a human-readable explanation of what was expected, what was found,
    and what to do about it -- this string is the entire value of the module.
    """


# ----------------------------------------------------------------------
# primitive coercion
# ----------------------------------------------------------------------
_MISSING = object()


def first_present(raw: dict, *names: str, default: Any = None) -> Any:
    """Return the first of ``names`` present in ``raw`` with a non-empty value.

    ``None``, ``""`` and empty containers count as absent, because that is how
    pandas serialises the blank cells in ``merged_standards.csv``.
    """
    for name in names:
        if name in raw:
            value = raw[name]
            if value is None:
                continue
            if isinstance(value, float) and math.isnan(value):
                continue
            if isinstance(value, str) and not value.strip():
                continue
            if isinstance(value, (list, dict)) and not value:
                continue
            return value
    return default


def as_text(value: Any, default: str = "") -> str:
    if value is _MISSING or value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    text = str(value).strip()
    # pandas writes missing values as the literal strings "nan"/"None".
    if text.lower() in {"nan", "none", "null"}:
        return default
    return text


def as_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value is None or value is _MISSING:
        return default
    try:
        if isinstance(value, float) and math.isnan(value):
            return default
        if isinstance(value, str):
            value = value.strip()
            if not value or value.lower() in {"nan", "none", "null"}:
                return default
            # "2009.0" arrives whenever a year column survived a float round-trip.
            value = value.split(".")[0]
        return int(value)
    except (TypeError, ValueError):
        return default


def as_bool(value: Any, default: bool = True) -> bool:
    """Coerce the many ways a boolean reaches us out of CSV/JSON.

    ``is_current`` is a real bool in the JSON output, but a CSV round-trip turns
    it into ``"True"``/``"true"``/``1``/``"yes"``.
    """
    if value is None or value is _MISSING:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return default
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "t", "yes", "y", "1", "current"}:
        return True
    if text in {"false", "f", "no", "n", "0", "superseded", "withdrawn"}:
        return False
    return default


# ----------------------------------------------------------------------
# coverage reporting
# ----------------------------------------------------------------------
@dataclass
class FieldCoverage:
    """How well a dataset satisfied one logical field."""

    field: str
    total: int
    filled: int
    source_key: str = ""

    @property
    def ratio(self) -> float:
        return self.filled / self.total if self.total else 0.0

    def __str__(self) -> str:
        key = f" <- {self.source_key!r}" if self.source_key else ""
        return f"{self.field}: {self.filled}/{self.total} ({self.ratio:.0%}){key}"


def coverage(records: Sequence[dict], aliases: dict[str, Sequence[str]]) -> list[FieldCoverage]:
    """Report, per logical field, how many records carry a usable value.

    Also records *which* alias supplied the value, so a rename in the upstream
    generator shows up as ``text <- 'chunk'`` becoming ``text <- 'content'``
    rather than as a silent behaviour change.
    """
    out: list[FieldCoverage] = []
    for logical, names in aliases.items():
        filled = 0
        seen: dict[str, int] = {}
        for rec in records:
            value = first_present(rec, *names)
            if value is not None:
                filled += 1
                for name in names:
                    if name in rec and first_present(rec, name) is not None:
                        seen[name] = seen.get(name, 0) + 1
                        break
        source = max(seen, key=lambda k: seen[k]) if seen else (names[0] if names else "")
        out.append(FieldCoverage(logical, len(records), filled, source))
    return out


def _require(cover: list[FieldCoverage], field_name: str, *, minimum: float,
             path: Optional[Path], hint: str = "") -> FieldCoverage:
    for entry in cover:
        if entry.field == field_name:
            if entry.ratio < minimum:
                raise SchemaError(
                    f"{path or '<memory>'}: field {field_name!r} is empty in "
                    f"{entry.total - entry.filled} of {entry.total} records "
                    f"({entry.ratio:.0%} filled, need >= {minimum:.0%}).\n"
                    f"  looked for keys: {hint}\n"
                    f"  This usually means the file was produced by a different "
                    f"generator than expected. Refusing to build an index from it: "
                    f"embeddings of empty text all collapse onto the same vector, "
                    f"so search would return confident nonsense instead of an error."
                )
            return entry
    raise SchemaError(f"internal: no coverage entry for {field_name!r}")


# ----------------------------------------------------------------------
# file readers
# ----------------------------------------------------------------------
def load_json(path: Path | str) -> Any:
    path = Path(path)
    if not path.exists():
        raise SchemaError(f"missing required file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SchemaError(f"{path}: not valid JSON ({exc})") from exc


def load_jsonl(path: Path | str) -> list[dict]:
    """Read JSONL, skipping only blank lines and reporting bad ones precisely."""
    path = Path(path)
    if not path.exists():
        raise SchemaError(f"missing required file: {path}")
    out: list[dict] = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SchemaError(f"{path}:{lineno}: not valid JSON ({exc})") from exc
            if isinstance(obj, dict):
                out.append(obj)
    return out


# ----------------------------------------------------------------------
# chunk records  (bis_data/rag/chunked_documents.jsonl)
# ----------------------------------------------------------------------
#: Logical field -> accepted source keys, in priority order. The first entry is
#: what ``create_rag_dataset.py`` actually writes; the rest are aliases that
#: appeared in hand-written build scripts and are kept so those keep working.
CHUNK_ALIASES: dict[str, tuple[str, ...]] = {
    "text": ("chunk", "text", "content", "body", "passage"),
    "designation": ("designation", "is_number", "is_code", "standard_designation"),
    "title": ("title", "standard_title", "name"),
    "chunk_id": ("chunk_id", "id"),
    "standard_id": ("standard_id", "canonical", "parent_id"),
    "division": ("division", "domain", "sector"),
    "committee": ("committee", "technical_committee", "tc"),
    "year": ("year", "publication_year"),
    "is_current": ("is_current", "current"),
    "status": ("status",),
    "archive_url": ("archive_url", "url", "source_url"),
}

#: Texts shorter than this are front-matter noise, not retrievable content.
MIN_CHUNK_CHARS = 40


@dataclass(frozen=True)
class Chunk:
    """One retrievable passage, plus the metadata a citation needs."""

    chunk_id: str
    text: str
    designation: str = ""
    standard_id: str = ""
    title: str = ""
    division: str = ""
    committee: str = ""
    year: Optional[int] = None
    is_current: bool = True
    archive_url: str = ""
    chunk_index: int = 0
    total_chunks: int = 0

    @property
    def status(self) -> str:
        return "current" if self.is_current else "superseded"

    @classmethod
    def from_record(cls, raw: dict, *, fallback_id: str = "") -> "Chunk":
        text = as_text(first_present(raw, *CHUNK_ALIASES["text"]))
        is_current = as_bool(first_present(raw, *CHUNK_ALIASES["is_current"]), default=True)
        status = as_text(first_present(raw, *CHUNK_ALIASES["status"]))
        if status and first_present(raw, *CHUNK_ALIASES["is_current"]) is None:
            # A file that carries only a status string still tells us the truth.
            is_current = status.strip().lower() == "current"

        designation = as_text(first_present(raw, *CHUNK_ALIASES["designation"]))
        standard_id = as_text(first_present(raw, *CHUNK_ALIASES["standard_id"]))
        chunk_id = as_text(first_present(raw, *CHUNK_ALIASES["chunk_id"]))
        if not chunk_id:
            chunk_id = f"{standard_id or 'chunk'}__{as_int(first_present(raw, 'chunk_index'), 0)}"
        if not standard_id and not designation:
            standard_id = fallback_id

        return cls(
            chunk_id=chunk_id,
            text=text,
            designation=designation,
            standard_id=standard_id,
            title=as_text(first_present(raw, *CHUNK_ALIASES["title"])),
            division=as_text(first_present(raw, *CHUNK_ALIASES["division"])),
            committee=as_text(first_present(raw, *CHUNK_ALIASES["committee"])),
            year=as_int(first_present(raw, *CHUNK_ALIASES["year"])),
            is_current=is_current,
            archive_url=as_text(first_present(raw, *CHUNK_ALIASES["archive_url"])),
            chunk_index=as_int(first_present(raw, "chunk_index", "index"), 0) or 0,
            total_chunks=as_int(first_present(raw, "total_chunks", "n_chunks"), 0) or 0,
        )

    def embedding_text(self) -> str:
        """The string that actually gets embedded.

        Metadata comes first and the passage last. Two reasons:

        * a chunk that opens with ``IS 1239`` is far easier to filter by eye
          when debugging retrieval than one that opens mid-sentence;
        * BGE-style models pool towards the front of the input, and the IS
          number, title and division are the most discriminative tokens we
          hold -- OCR body text is mostly tables and committee rosters.

        Note this is *not* what the original ``build_chromadb.py`` draft
        produced: it read ``chunk.get("text", chunk.get("content", ""))``,
        neither of which exists, so every one of the 9,043 documents would have
        ended at ``Content:`` with nothing after it.
        """
        header = [f"IS Code: {self.designation or self.standard_id}"]
        if self.title:
            header.append(f"Title: {self.title}")
        if self.division:
            header.append(f"Division: {self.division}")
        if self.committee:
            header.append(f"Committee: {self.committee}")
        if self.year:
            header.append(f"Year: {self.year}")
        header.append(f"Status: {self.status}")
        return "\n".join(header) + f"\nContent: {self.text}"

    def as_metadata(self) -> dict[str, Any]:
        """Metadata shaped for a vector store.

        Types are preserved rather than stringified, so that range and boolean
        filters work. ChromaDB accepts ``str | int | float | bool``; writing
        every field as ``str`` (as the earlier draft did) makes
        ``where={"year": {"$gte": 2010}}`` match nothing, because in a
        lexicographic comparison ``"1994" > "2010"``.
        """
        return {
            "chunk_id": self.chunk_id,
            "standard_id": self.standard_id,
            "designation": self.designation,
            "title": self.title,
            "division": self.division,
            "committee": self.committee,
            "year": int(self.year) if self.year else -1,
            "is_current": bool(self.is_current),
            "status": self.status,
            "archive_url": self.archive_url,
            "chunk_index": int(self.chunk_index),
        }


def load_chunks(path: Path | str, *, min_text_ratio: float = 0.9,
                drop_short: bool = True) -> tuple[list[Chunk], list[FieldCoverage]]:
    """Load ``chunked_documents.jsonl``, refusing to proceed on empty text.

    Returns ``(chunks, coverage_report)``. The report is what the CLI prints;
    keep an eye on whether ``text <- 'chunk'`` still holds.
    """
    raw = load_jsonl(path)
    if not raw:
        raise SchemaError(f"{path}: no records found")
    report = coverage(raw, CHUNK_ALIASES)
    _require(report, "text", minimum=min_text_ratio, path=Path(path),
             hint=", ".join(repr(a) for a in CHUNK_ALIASES["text"]))

    chunks: list[Chunk] = []
    for i, rec in enumerate(raw):
        chunk = Chunk.from_record(rec, fallback_id=f"chunk_{i}")
        if not chunk.text:
            continue
        if drop_short and len(chunk.text) < MIN_CHUNK_CHARS:
            # OCR dumps carry a lot of single-word "chunks" (page furniture,
            # stray numerals). Indexing them costs latency and adds nothing.
            continue
        chunks.append(chunk)

    if not chunks:
        raise SchemaError(
            f"{path}: every record was filtered out (empty or shorter than "
            f"{MIN_CHUNK_CHARS} characters). Nothing to index."
        )
    return chunks, report


# ----------------------------------------------------------------------
# standard-level records (knowledge_base.json / search_corpus.jsonl / merged)
# ----------------------------------------------------------------------
STANDARD_ALIASES: dict[str, tuple[str, ...]] = {
    "canonical": ("canonical", "id", "standard_id"),
    "designation": ("designation", "is_number", "is_code"),
    "title": ("title", "standard_title", "name"),
    "keywords": ("keywords", "tags"),
    "division": ("division", "domain", "sector"),
    "committee": ("committee", "technical_committee", "tc"),
    "year": ("year", "publication_year"),
    "is_current": ("is_current", "current"),
    "superseded_by": ("superseded_by", "superseded_by_text", "replaced_by"),
    "summary": ("text", "text_snippet", "summary", "abstract", "description"),
    "archive_url": ("archive_url", "url", "source_url"),
    "is_compulsory": ("is_compulsory", "compulsory", "mandatory"),
}


@dataclass(frozen=True)
class Standard:
    """A standard as the *standards* collection sees it: one row per IS code."""

    canonical: str
    designation: str
    title: str = ""
    keywords: tuple[str, ...] = ()
    division: str = ""
    committee: str = ""
    part: Optional[int] = None
    section: Optional[int] = None
    year: Optional[int] = None
    is_current: bool = True
    superseded_by: str = ""
    summary: str = ""
    archive_url: str = ""
    is_compulsory: bool = False

    @property
    def status(self) -> str:
        return "current" if self.is_current else "superseded"

    @classmethod
    def from_record(cls, raw: dict) -> "Standard":
        keywords = first_present(raw, *STANDARD_ALIASES["keywords"], default=())
        if isinstance(keywords, str):
            keywords = tuple(k.strip() for k in keywords.split(",") if k.strip())
        elif isinstance(keywords, Iterable):
            keywords = tuple(as_text(k) for k in keywords if as_text(k))
        else:
            keywords = ()

        is_current = as_bool(first_present(raw, *STANDARD_ALIASES["is_current"]), default=True)
        superseded_by = as_text(first_present(raw, *STANDARD_ALIASES["superseded_by"]))
        if superseded_by:
            # A standard that names its replacement is not the current edition,
            # whatever the flag says. Trust the explicit chain over the flag.
            is_current = False

        return cls(
            canonical=as_text(first_present(raw, *STANDARD_ALIASES["canonical"])),
            designation=as_text(first_present(raw, *STANDARD_ALIASES["designation"])),
            title=as_text(first_present(raw, *STANDARD_ALIASES["title"])),
            keywords=keywords,
            division=as_text(first_present(raw, *STANDARD_ALIASES["division"])),
            committee=as_text(first_present(raw, *STANDARD_ALIASES["committee"])),
            part=as_int(first_present(raw, "part")),
            section=as_int(first_present(raw, "section")),
            year=as_int(first_present(raw, *STANDARD_ALIASES["year"])),
            is_current=is_current,
            superseded_by=superseded_by,
            summary=as_text(first_present(raw, *STANDARD_ALIASES["summary"])),
            archive_url=as_text(first_present(raw, *STANDARD_ALIASES["archive_url"])),
            is_compulsory=as_bool(first_present(raw, *STANDARD_ALIASES["is_compulsory"]),
                                  default=False),
        )

    def embedding_text(self, *, summary_chars: int = 1200) -> str:
        """The string embedded for the standards collection.

        Unlike a chunk, a standard *does* want its keyword list and the opening
        of its text: this record is the one returned for "what is IS 1239?".
        """
        parts = [
            f"IS Code: {self.designation or self.canonical}",
            f"Title: {self.title}",
        ]
        if self.division:
            parts.append(f"Division: {self.division}")
        if self.committee:
            parts.append(f"Committee: {self.committee}")
        if self.year:
            parts.append(f"Year: {self.year}")
        parts.append(f"Status: {self.status}")
        if not self.is_current and self.superseded_by:
            parts.append(f"Superseded by: {self.superseded_by}")
        parts.append(f"Compulsory (QCO): {'yes' if self.is_compulsory else 'no'}")
        if self.keywords:
            parts.append("Keywords: " + ", ".join(self.keywords))
        if self.summary:
            parts.append(f"Summary: {self.summary[:summary_chars]}")
        return "\n".join(parts)

    def as_metadata(self) -> dict[str, Any]:
        return {
            "canonical": self.canonical,
            "designation": self.designation,
            "title": self.title,
            "division": self.division,
            "committee": self.committee,
            "year": int(self.year) if self.year else -1,
            "is_current": bool(self.is_current),
            "status": self.status,
            "superseded_by": self.superseded_by,
            "is_compulsory": bool(self.is_compulsory),
            "archive_url": self.archive_url,
            "keywords": ", ".join(self.keywords),
        }


def dedupe_standards(standards: Iterable[Standard]) -> list[Standard]:
    """Collapse to one row per canonical id, preferring the richest row.

    ``knowledge_base.json``, ``search_corpus.jsonl`` and ``merged_standards.json``
    overlap heavily but each carries something the others lack -- keywords,
    text snippets, QCO flags. Merging them is the point; duplicating ids in a
    vector store is not.
    """
    best: dict[str, Standard] = {}
    for std in standards:
        key = std.canonical or std.designation
        if not key:
            continue
        current = best.get(key)
        if current is None:
            best[key] = std
            continue
        best[key] = Standard(
            canonical=current.canonical or std.canonical,
            designation=current.designation or std.designation,
            title=current.title or std.title,
            keywords=current.keywords or std.keywords,
            division=current.division or std.division,
            committee=current.committee or std.committee,
            part=current.part if current.part is not None else std.part,
            section=current.section if current.section is not None else std.section,
            year=current.year if current.year is not None else std.year,
            is_current=current.is_current and std.is_current,
            superseded_by=current.superseded_by or std.superseded_by,
            summary=current.summary if len(current.summary) >= len(std.summary) else std.summary,
            archive_url=current.archive_url or std.archive_url,
            is_compulsory=current.is_compulsory or std.is_compulsory,
        )
    return sorted(best.values(), key=lambda s: (s.designation or s.canonical))
