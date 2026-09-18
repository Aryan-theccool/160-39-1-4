"""Merge the sources into one deduplicated, RAG-ready dataset.

Join key
--------
Everything is joined on :attr:`Designation.canonical`. That is the whole point
of the IS grammar module: ``gov.in.is.302.2.15.2009``, ``IS 302-2-15:2009`` and
``IS 302 (Part 2 / Section 15):2009`` are one standard and must collapse to one
row.

Merging several *editions*
--------------------------
IS 14220 has a 1994 and a 2002 edition. Dropping one loses history; keeping both
as unrelated rows makes a retrieval system happily recommend a withdrawn
edition. So each row carries:

``is_current``
    True when no newer edition of the same ``key_without_year`` is present.
``superseded_by``
    The newer edition, when known.

Field precedence
----------------
When two sources describe the same standard we prefer the more authoritative
one: BIS/QCO-derived metadata beats archive.org metadata, which beats text
mining. That is what ``_SOURCE_RANK`` encodes.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from .iscode import Designation, parse_designation

log = logging.getLogger(__name__)

#: Higher rank wins when two sources disagree about a field.
_SOURCE_RANK = {
    "BIS_PORTAL": 40,
    "BIS_QCO": 30,
    "ARCHIVE_ORG": 20,
    "TEXT_MINED": 10,
}

_COMMITTEE_RE = re.compile(r"\b([A-Z]{2,4}\s?\d{1,3})\b")

#: Fields where a later, higher-ranked source may overwrite an earlier one.
_OVERWRITABLE = ("title", "division", "section_name", "committee", "product_category",
                 "status", "scheme", "superseded_by_text")


@dataclass
class StandardRecord:
    """The unified schema every source is mapped onto."""

    canonical: str
    key_without_year: str
    designation: str
    prefix: str = "IS"
    number: Optional[int] = None
    part: Optional[int] = None
    section: Optional[int] = None
    year: Optional[int] = None

    title: str = ""
    division: str = ""
    section_name: str = ""
    committee: str = ""
    status: str = "unknown"
    product_category: str = ""
    scheme: str = ""
    amendments: Optional[int] = None
    superseded_by_text: str = ""

    #: Provenance.
    sources: list[str] = field(default_factory=list)
    archive_identifier: str = ""
    archive_url: str = ""
    license_url: str = ""
    text_path: str = ""
    pdf_path: str = ""
    has_full_text: bool = False
    is_compulsory: bool = False

    #: Computed by `resolve_editions`.
    is_current: bool = True
    superseded_by: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def retrieval_text(self, *, content: str = "", content_chars: int = 4000) -> str:
        """Build the string that actually gets embedded.

        Metadata first: for a standards recommender the IS number, title and
        committee are far more discriminative than the first page of OCR, which
        is boilerplate (committee member lists, copyright notices).
        """
        head = (
            f"IS Code: {self.designation}\n"
            f"Title: {self.title}\n"
            f"Division: {self.division}\n"
            f"Committee: {self.section_name or self.committee}\n"
            f"Year: {self.year or 'unknown'}\n"
            f"Status: {self.status}\n"
            f"Compulsory (QCO): {'yes' if self.is_compulsory else 'no'}\n"
        )
        if content:
            head += f"Content: {content[:content_chars]}\n"
        return head.strip()


def _empty_record(desig: Designation) -> StandardRecord:
    return StandardRecord(
        canonical=desig.canonical,
        key_without_year=desig.key_without_year,
        designation=desig.format(),
        prefix=desig.prefix,
        number=desig.number,
        part=desig.part,
        section=desig.section,
        year=desig.year,
    )


# ----------------------------------------------------------------------
# source adapters
# ----------------------------------------------------------------------
def from_archive_items(items: Iterable, *, text_dir: Optional[Path] = None,
                       pdf_dir: Optional[Path] = None) -> list[StandardRecord]:
    """Map archive.org items onto the unified schema."""
    records: list[StandardRecord] = []
    for item in items:
        desig = item.designation
        if desig is None:
            log.debug("skipping %s: identifier is not an IS designation", item.identifier)
            continue

        rec = _empty_record(desig)
        rec.sources.append("ARCHIVE_ORG")
        rec.title = item.title
        rec.division = item.division
        rec.section_name = item.section
        rec.committee = _committee_from(item.section)
        rec.amendments = item.number_of_amendments
        rec.superseded_by_text = item.superceded_by
        rec.archive_identifier = item.identifier
        rec.archive_url = f"https://archive.org/details/{item.identifier}"
        rec.license_url = item.license_url
        rec.status = "published"
        rec.has_full_text = False

        if text_dir is not None:
            path = Path(text_dir) / f"{item.identifier}.txt"
            if path.exists():
                rec.text_path = str(path)
                rec.has_full_text = True
        if pdf_dir is not None:
            pdf = item.best_pdf_file()
            if pdf is not None:
                candidate = Path(pdf_dir) / pdf.name
                if candidate.exists():
                    rec.pdf_path = str(candidate)

        records.append(rec)
    return records


def from_mandatory(standards: Iterable) -> list[StandardRecord]:
    """Map BIS compulsory-certification rows onto the unified schema."""
    records: list[StandardRecord] = []
    for ms in standards:
        desig = ms.designation
        rec = _empty_record(desig)
        rec.sources.append("BIS_QCO")
        rec.title = ms.title
        rec.product_category = ms.product_category
        rec.scheme = ms.scheme or "QCO"
        rec.status = "mandatory"
        rec.is_compulsory = True
        records.append(rec)
    return records


def from_portal_rows(rows: Iterable[dict]) -> list[StandardRecord]:
    """Map rows scraped from a BIS portal/API onto the unified schema.

    Accepts the field names the BIS catalogue actually uses. Unparseable IS
    numbers are dropped and counted, not silently coerced.
    """
    records: list[StandardRecord] = []
    dropped = 0
    for row in rows:
        raw = row.get("is_number") or row.get("standard") or row.get("designation") or ""
        desig = parse_designation(str(raw))
        if desig is None:
            dropped += 1
            continue
        rec = _empty_record(desig)
        rec.sources.append("BIS_PORTAL")
        rec.title = str(row.get("title") or "")
        rec.committee = str(row.get("committee") or "")
        rec.status = str(row.get("status") or "unknown")
        rec.year = desig.year
        records.append(rec)
    if dropped:
        log.warning("portal: dropped %d rows with unparseable IS numbers", dropped)
    return records


def _committee_from(section_name: str) -> str:
    """Pull a committee code like ``TXD 13`` out of a section name."""
    if not section_name:
        return ""
    m = _COMMITTEE_RE.search(section_name)
    return m.group(1).strip() if m else ""


# ----------------------------------------------------------------------
# merge
# ----------------------------------------------------------------------
def merge(*record_lists: list[StandardRecord]) -> list[StandardRecord]:
    """Collapse records from every source onto one row per canonical key."""
    merged: dict[str, StandardRecord] = {}

    for records in record_lists:
        for rec in records:
            existing = merged.get(rec.canonical)
            if existing is None:
                merged[rec.canonical] = dataclasses.replace(rec)
                continue
            _fold_into(existing, rec)

    out = resolve_editions(list(merged.values()))
    log.info("merged %d records into %d unique standards",
             sum(len(r) for r in record_lists), len(out))
    return out


def _fold_into(target: StandardRecord, incoming: StandardRecord) -> None:
    """Fold `incoming` into `target`, honouring source rank."""
    for source in incoming.sources:
        if source not in target.sources:
            target.sources.append(source)

    target.is_compulsory = target.is_compulsory or incoming.is_compulsory
    target.has_full_text = target.has_full_text or incoming.has_full_text

    for attr in ("archive_identifier", "archive_url", "license_url", "text_path", "pdf_path"):
        if not getattr(target, attr) and getattr(incoming, attr):
            setattr(target, attr, getattr(incoming, attr))

    if _rank(incoming) >= _rank(target):
        for attr in _OVERWRITABLE:
            value = getattr(incoming, attr)
            if value:
                setattr(target, attr, value)
        if incoming.amendments is not None:
            target.amendments = incoming.amendments
    else:
        for attr in _OVERWRITABLE:
            if not getattr(target, attr) and getattr(incoming, attr):
                setattr(target, attr, getattr(incoming, attr))
        if target.amendments is None:
            target.amendments = incoming.amendments


def _rank(rec: StandardRecord) -> int:
    return max((_SOURCE_RANK.get(s, 0) for s in rec.sources), default=0)


def resolve_editions(records: list[StandardRecord]) -> list[StandardRecord]:
    """Flag which edition of each standard is the newest one we hold."""
    by_key: dict[str, list[StandardRecord]] = {}
    for rec in records:
        by_key.setdefault(rec.key_without_year, []).append(rec)

    for group in by_key.values():
        dated = [r for r in group if r.year is not None]
        if not dated:
            for rec in group:
                rec.is_current = True
                rec.superseded_by = ""
            continue

        newest = max(dated, key=lambda r: r.year)
        for rec in group:
            rec.is_current = rec is newest
            rec.superseded_by = "" if rec is newest else newest.designation

    return sorted(records, key=lambda r: (r.prefix, r.number or 0,
                                          r.part or 0, r.section or 0, r.year or 0))


# ----------------------------------------------------------------------
# IO
# ----------------------------------------------------------------------
def load_archive_jsonl(path: Path) -> list[dict]:
    """Read the ``items.jsonl`` written by the archive scraper."""
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def archive_items_from_jsonl(path: Path):
    """Rehydrate serialised archive items into objects with the needed attrs."""
    from .archive_scraper import ArchiveFile, ArchiveItem

    items = []
    for row in load_archive_jsonl(path):
        files = [ArchiveFile(**f) for f in row.pop("files", [])]
        row.pop("designation", None)
        row.pop("designation_canonical", None)
        row.pop("is_access_restricted", None)
        known = {f.name for f in dataclasses.fields(ArchiveItem)}
        items.append(ArchiveItem(files=files, **{k: v for k, v in row.items() if k in known}))
    return items


def to_dataframe(records: list[StandardRecord]) -> pd.DataFrame:
    return pd.DataFrame([r.to_dict() for r in records])


def write_outputs(records: list[StandardRecord], out_dir: Path, *,
                  write_xlsx: bool = False) -> dict:
    """Write the merged dataset as JSON, JSONL and CSV (and optionally XLSX)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df = to_dataframe(records)

    paths = {}
    paths["json"] = out_dir / "merged_standards.json"
    df.to_json(paths["json"], orient="records", indent=2, force_ascii=False)

    paths["jsonl"] = out_dir / "merged_standards.jsonl"
    with open(paths["jsonl"], "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")

    paths["csv"] = out_dir / "merged_standards.csv"
    df.to_csv(paths["csv"], index=False)

    if write_xlsx:
        paths["xlsx"] = out_dir / "merged_standards.xlsx"
        df.to_excel(paths["xlsx"], index=False)

    log.info("wrote %d standards to %s", len(records), out_dir)
    return paths
