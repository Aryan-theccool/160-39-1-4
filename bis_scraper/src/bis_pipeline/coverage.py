"""QCO coverage report: which mandatory standards do we already hold?

BIS lists ~769 products under compulsory certification, each naming one or more
IS numbers. Those documents split into two groups:

**Already free to index.** A large share of them are in archive.org's
`gov.in.is.*` collection -- CC0, published under the Right to Information Act
2005. No permission needed, no registration, nothing to scrape behind a login.

**Free after registration.** The rest are on `standardsbis.bsbedge.com`, where
BIS's own FAQ says you register and download Indian Standards PDFs for free.
That is a per-account entitlement with DRM on the files; it is yours to obtain
and read, and not something a scraper should bulk-mirror.

This module draws that line. It answers "of the standards BIS says I must
comply with, which can I actually put in a searchable index today" -- which is
the question that decides whether the rest of the pipeline is useful to you.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .http import HttpClient, iter_pages
from .iscode import Designation, parse_designation

log = logging.getLogger(__name__)

ADVANCED_SEARCH_URL = "https://archive.org/advancedsearch.php"


@dataclass(frozen=True)
class CoverageRow:
    """One QCO-mandated IS number and whether the corpus has it."""

    designation: str
    key: str
    product: str
    scheme: str
    #: Matching archive.org identifiers, newest first. Empty means not held.
    matches: tuple[str, ...] = ()

    @property
    def held(self) -> bool:
        return bool(self.matches)

    @property
    def best_match(self) -> str:
        return self.matches[0] if self.matches else ""


def _join_key(desig: Designation) -> str:
    """Year-independent key, so IS 10500:2012 matches any edition we hold."""
    return f"{desig.prefix}|{desig.number}|{desig.part}|{desig.section}"


def build_corpus_index(client: HttpClient, *, query: str = "identifier:gov.in.is.*",
                       page_size: int = 200, max_items: Optional[int] = None) -> dict[str, list[str]]:
    """Map join key -> archive.org identifiers, for the whole corpus.

    One listing pass over the collection (~111 requests for 22k items) instead
    of a metadata call per standard.
    """
    index: dict[str, list[str]] = {}

    def extract(payload):
        for doc in payload.get("response", {}).get("docs", []) or []:
            yield doc

    params = {"q": query, "fl[]": ["identifier"], "sort[]": "identifier asc", "output": "json"}
    count = 0
    for doc in iter_pages(client, ADVANCED_SEARCH_URL, params, page_size=page_size,
                          max_items=max_items, extract=extract):
        identifier = doc.get("identifier", "")
        desig = _designation_from_identifier(identifier)
        if desig is None:
            continue
        index.setdefault(_join_key(desig), []).append(identifier)
        count += 1

    for identifiers in index.values():
        identifiers.sort()
    log.info("corpus index: %d items across %d distinct standards", count, len(index))
    return index


def _designation_from_identifier(identifier: str) -> Optional[Designation]:
    from .iscode import designation_from_identifier
    return designation_from_identifier(identifier)


def report(mandatory_standards: Iterable, corpus_index: dict[str, list[str]]) -> list[CoverageRow]:
    """Cross-reference QCO standards against the corpus index."""
    rows: list[CoverageRow] = []
    seen: set[tuple[str, str]] = set()

    for ms in mandatory_standards:
        desig = getattr(ms, "designation", None)
        if desig is None:
            continue
        key = _join_key(desig)
        product = getattr(ms, "product_category", "") or getattr(ms, "title", "")
        dedupe = (key, product)
        if dedupe in seen:
            continue
        seen.add(dedupe)

        rows.append(CoverageRow(
            designation=desig.format(),
            key=key,
            product=product,
            scheme=getattr(ms, "scheme", ""),
            matches=tuple(reversed(corpus_index.get(key, []))),
        ))

    return rows


def summarise(rows: list[CoverageRow]) -> dict:
    """Headline numbers for the coverage report."""
    held = [r for r in rows if r.held]
    distinct = {r.key for r in rows}
    distinct_held = {r.key for r in held}
    return {
        "qco_standards": len(distinct),
        "held_in_cc0_corpus": len(distinct_held),
        "not_held": len(distinct - distinct_held),
        "coverage_pct": round(100.0 * len(distinct_held) / len(distinct), 1) if distinct else 0.0,
        "rows": len(rows),
    }


def write_report(rows: list[CoverageRow], out_dir: Path) -> dict:
    """Write held/not-held CSVs plus a summary JSON."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}

    for name, subset in (("qco_held", [r for r in rows if r.held]),
                         ("qco_missing", [r for r in rows if not r.held])):
        path = out_dir / f"{name}.csv"
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["designation", "is_number_key", "product", "scheme",
                             "archive_identifier", "archive_url"])
            for r in subset:
                writer.writerow([
                    r.designation, r.key, r.product, r.scheme, r.best_match,
                    f"https://archive.org/details/{r.best_match}" if r.best_match else "",
                ])
        paths[name] = path

    return paths
