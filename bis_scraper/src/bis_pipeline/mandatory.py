"""Cross-reference BIS's compulsory-certification (QCO) standards against the
archive.org corpus.

This replaces the original plan's "OCR the BIS 2005 catalogue book" step.
That step cannot work: ``bis2005completec0000vari`` is a controlled-digital-
lending item whose PDF, hOCR and text derivatives are all ``private`` and
answer HTTP 401. See ``docs/CORRECTIONS.md``.

What we do instead is more useful. BIS publishes, on www.bis.gov.in, the list
of products under compulsory certification (187 Quality Control Orders covering
769 products). Those tables name the applicable IS numbers -- and a QCO-mandated
standard is exactly the kind of standard an engineer actually needs. Joining
that list against the archive.org corpus tells you, per IS number:

* is it compulsory (QCO-mandated)?
* do we have freely licensed full text for it?

The page structure is BIS's own WordPress markup and will drift; this module
therefore parses defensively and reports what it could not read rather than
silently returning nothing.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from bs4 import BeautifulSoup

from .http import HttpClient
from .iscode import Designation, find_all

log = logging.getLogger(__name__)

PRODUCTS_UNDER_CC_URL = (
    "https://www.bis.gov.in/product-certification/products-under-compulsory-certification/"
)

#: Cells that hold a product/notification description rather than an IS number.
_NON_IS_HEADINGS = ("sl. no", "sl no", "s. no", "s.no", "product category",
                    "notification", "product", "remarks")


@dataclass
class MandatoryStandard:
    """One IS number listed as applicable to a compulsory-certification product."""

    designation: Designation
    title: str = ""
    product_category: str = ""
    scheme: str = ""
    source_url: str = ""
    #: Free-text evidence from the page, for auditing a bad parse.
    raw_row: str = ""


@dataclass
class ParseReport:
    standards: list[MandatoryStandard] = field(default_factory=list)
    tables_seen: int = 0
    rows_seen: int = 0
    rows_with_is: int = 0

    def as_dict(self) -> dict:
        return {
            "standards": len(self.standards),
            "tables_seen": self.tables_seen,
            "rows_seen": self.rows_seen,
            "rows_with_is": self.rows_with_is,
        }


def parse_tables(html: str, *, scheme: str = "", source_url: str = "") -> ParseReport:
    """Extract IS numbers from every HTML table on a BIS compulsory-cert page.

    Deliberately tolerant: BIS tables vary between schemes, sometimes carry a
    leading "Sl. No." column, sometimes put several IS numbers in one cell
    (``IS 14286`` / ``IS/IEC 61730-1``). We take any well-formed designation
    from the cell that looks like an IS-number column, and keep the adjacent
    cells as title/product context.
    """
    report = ParseReport()
    if not html:
        return report

    soup = BeautifulSoup(html, "lxml")
    for table in soup.find_all("table"):
        report.tables_seen += 1
        headers = [th.get_text(" ", strip=True).lower() for th in table.find_all("th")]
        is_col = _guess_is_column(headers)

        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            report.rows_seen += 1
            texts = [c.get_text(" ", strip=True) for c in cells]

            target = texts[is_col] if (is_col is not None and is_col < len(texts)) else " ".join(texts)
            found = [d for d in find_all(target) if d.prefix.startswith("IS")]
            if not found:
                continue

            report.rows_with_is += 1
            title = _pick_context(texts, is_col)
            for desig in found:
                report.standards.append(MandatoryStandard(
                    designation=desig,
                    title=title,
                    scheme=scheme,
                    source_url=source_url,
                    raw_row=" | ".join(texts)[:500],
                ))

    return report


def _guess_is_column(headers: list[str]) -> Optional[int]:
    """Index of the column that holds IS numbers, or None to scan all cells."""
    for i, head in enumerate(headers):
        low = head.lower()
        if "is no" in low or low.strip() in ("is number", "is", "standard", "is no."):
            return i
        if "is" in low.split() and "no" in low.split():
            return i
    # No recognisable header: fall back to scanning, skipping obvious non-IS cells.
    for i, head in enumerate(headers):
        if any(head.startswith(p) for p in _NON_IS_HEADINGS):
            continue
        if head:
            return i
    return None


def _pick_context(texts: list[str], is_col: Optional[int]) -> str:
    """Best available title/product text for a row."""
    candidates = [t for i, t in enumerate(texts)
                  if i != is_col and t and not t.replace(".", "").isdigit()]
    if not candidates:
        return ""
    # Prefer the longest plausible prose cell; BIS puts the title there.
    return max(candidates, key=len)


def scrape_mandatory(client: HttpClient, *, urls: Optional[Iterable[str]] = None,
                     scheme: str = "QCO") -> ParseReport:
    """Fetch and parse one or more BIS compulsory-certification pages.

    ``urls=None`` means BIS's default pages. An explicit empty iterable also
    falls back to the defaults rather than scraping nothing.
    """
    combined = ParseReport()
    for url in (tuple(urls) if urls else (PRODUCTS_UNDER_CC_URL,)):
        try:
            html = client.get(url).text
        except Exception as exc:  # noqa: BLE001 - a dead page must not kill the run
            log.error("could not fetch %s: %s", url, exc)
            continue
        report = parse_tables(html, scheme=scheme, source_url=url)
        log.info("%s: %d tables, %d rows, %d IS numbers",
                 url, report.tables_seen, report.rows_seen, len(report.standards))
        combined.standards.extend(report.standards)
        combined.tables_seen += report.tables_seen
        combined.rows_seen += report.rows_seen
        combined.rows_with_is += report.rows_with_is
    return combined
