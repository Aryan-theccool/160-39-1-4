"""Scraper for archive.org's `gov.in.is.*` collection.

What this collection is
-----------------------
Carl Malamud's Public.Resource.Org upload of Bureau of Indian Standards
documents, published under CC0 with the note "Published under the auspices of
the Right to Information Act 2005". As of writing the collection holds 22,025
items (`q=identifier:gov.in.is.*`).

Why this scraper looks nothing like a PDF+OCR pipeline
------------------------------------------------------
Three findings drove the design:

* **Every item already has a plain-text OCR derivative** (``*_djvu.txt``),
  produced by archive.org with Tesseract/ABBYY at ingest time. Downloading a
  scanned PDF and re-OCR-ing it with pytesseract reproduces that work far more
  slowly and *worse* -- a local `--psm 6` pass on a 600dpi 1985 scan will not
  beat the derivative.
* **Some items are access-restricted.** Controlled-digital-lending items (e.g.
  ``bis2005completec0000vari``) mark their ``.pdf``/``_hocr.html``/``_djvu.txt``
  files ``"private": true`` and answer ``401 Authorization Required``. Those must
  be detected and skipped, not retried forever.
* **The rich metadata is in the item's ``description`` field**, not the text
  layer. It carries structured fields -- Division Name, Section Name, Number of
  Amendments, Superceding, Superceded by -- which is exactly the committee and
  status data the original plan wanted to scrape out of BIS's portal.

So: metadata for identity and structure, ``_djvu.txt`` for retrieval content,
PDF only on request.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

from .http import HttpClient, HttpError, iter_pages
from .iscode import Designation, designation_from_identifier

log = logging.getLogger(__name__)

ADVANCED_SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata/{identifier}"
DOWNLOAD_URL = "https://archive.org/download/{identifier}/{name}"

#: `identifier:` scoping is what selects the collection. A bare full-text
#: `q=gov.in.is` also matches 21,340 items that merely *mention* the string.
DEFAULT_QUERY = "identifier:gov.in.is.*"

#: archive.org hard-caps `rows` at 200.
MAX_ROWS = 200

# Fields we want in the search listing itself, so that for many purposes we
# never need a per-item metadata call at all.
SEARCH_FIELDS = ["identifier", "title", "date", "year", "creator", "subject",
                 "description", "downloads", "item_size", "collection"]

# Ranked by usefulness-per-byte. `_djvu.txt` is full text at ~1/30th the size
# of the PDF.
TEXT_FORMATS = ("DjVuTXT", "Text", "Plain Text", "hOCR", "chOCR")
PDF_FORMATS = ("Text PDF", "PDF", "Additional Collections PDF")

_DESCRIPTION_LABELS = (
    "Name of Standards Organization",
    "Division Name",
    "Section Name",
    "Designator of Legally Binding Document",
    "Title of Legally Binding Document",
    "Number of Amendments",
    "Equivalence",
    "Superceding",
    "Superceded by",
)

# Labels are glued to their values in the source ("...BIS)Division Name:..."),
# so match on the label followed by a colon rather than splitting on ':'.
_DESCRIPTION_RE = re.compile(
    r"(?P<label>" + "|".join(re.escape(l) for l in _DESCRIPTION_LABELS) + r")\s*:\s*",
    re.IGNORECASE,
)


@dataclass
class ArchiveFile:
    name: str
    format: str
    size: Optional[int]
    md5: Optional[str]
    private: bool
    url: str

    @property
    def is_text(self) -> bool:
        return self.format in TEXT_FORMATS

    @property
    def is_pdf(self) -> bool:
        return self.format in PDF_FORMATS


@dataclass
class ArchiveItem:
    """One archive.org item, normalised."""

    identifier: str
    title: str = ""
    date: str = ""
    creator: str = ""
    description: str = ""
    downloads: int = 0
    license_url: str = ""
    rights: str = ""
    #: Set from archive.org's `access-restricted-item` metadata flag.
    access_restricted_flag: bool = False
    files: list[ArchiveFile] = field(default_factory=list)
    #: Fields parsed out of `description`.
    division: str = ""
    section: str = ""
    number_of_amendments: Optional[int] = None
    superceding: str = ""
    superceded_by: str = ""
    equivalence: str = ""

    # -- derived ------------------------------------------------------
    @property
    def designation(self) -> Optional[Designation]:
        return designation_from_identifier(self.identifier)

    @property
    def is_access_restricted(self) -> bool:
        """True when the item's content is gated (controlled digital lending).

        Detecting this up front is the difference between a run that skips a
        handful of restricted items and one that retries them for an hour.

        Two independent signals, because neither is sufficient on its own:

        * archive.org's ``access-restricted-item`` metadata flag;
        * no publicly-listed text or PDF derivative at all.

        The second matters because the ``private`` flags in an item's file list
        do not reliably predict what ``/download/`` will serve: on the BIS 2005
        catalogue the ``_djvu.txt`` derivative is listed without a ``private``
        flag and still answers ``401 Authorization Required``.
        """
        if self.access_restricted_flag:
            return True
        content = [f for f in self.files if f.is_text or f.is_pdf]
        return bool(content) and not any(not f.private for f in content)

    def best_text_file(self) -> Optional[ArchiveFile]:
        for fmt in TEXT_FORMATS:
            for f in self.files:
                if f.format == fmt and not f.private:
                    return f
        return None

    def best_pdf_file(self) -> Optional[ArchiveFile]:
        for fmt in PDF_FORMATS:
            for f in self.files:
                if f.format == fmt and not f.private:
                    return f
        return None


# ----------------------------------------------------------------------
# parsing
# ----------------------------------------------------------------------
def parse_description_fields(description: str) -> dict:
    """Pull the structured fields out of an item's ``description``.

    The Public.Resource.Org upload packs them into one run-on string with no
    separator between a value and the next label::

        ...Bureau of Indian Standards (BIS)Division Name: TextilesSection
        Name: Textile Materials for Aerospace Purposes (TXD 13)Designator of
        Legally Binding Document: IS 11367 ...Number of Amendments: 1...

    Returns a dict with the label names lowercased and spaced.
    """
    out = {label.lower(): "" for label in _DESCRIPTION_LABELS}
    if not description:
        return out

    matches = list(_DESCRIPTION_RE.finditer(description))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(description)
        out[m.group("label").lower()] = description[m.end():end].strip()
    return out


def parse_item(payload: dict, identifier: Optional[str] = None) -> ArchiveItem:
    """Normalise an ``/metadata/<id>`` payload (or a search doc) into ArchiveItem."""
    meta = payload.get("metadata") or {}
    ident = identifier or meta.get("identifier") or payload.get("identifier") or ""

    files = []
    for f in payload.get("files") or []:
        size = f.get("size")
        files.append(ArchiveFile(
            name=f.get("name", ""),
            format=f.get("format", ""),
            size=int(size) if size not in (None, "") else None,
            md5=f.get("md5"),
            private=str(f.get("private", "")).lower() == "true",
            url=DOWNLOAD_URL.format(identifier=ident, name=f.get("name", "")),
        ))

    item = ArchiveItem(
        identifier=ident,
        title=_scalar(meta.get("title") or payload.get("title")),
        date=_scalar(meta.get("date") or payload.get("date") or payload.get("year")),
        creator=_scalar(meta.get("creator") or payload.get("creator")),
        description=_scalar(meta.get("description") or payload.get("description")),
        downloads=_as_int(meta.get("downloads") or payload.get("downloads")),
        license_url=_scalar(meta.get("licenseurl")),
        rights=_scalar(meta.get("rights")),
        access_restricted_flag=str(
            meta.get("access-restricted-item") or payload.get("access-restricted-item") or ""
        ).lower() == "true",
        files=files,
    )

    fields = parse_description_fields(item.description)
    item.division = fields.get("division name", "")
    item.section = fields.get("section name", "")
    item.superceding = fields.get("superceding", "")
    item.superceded_by = fields.get("superceded by", "")
    item.equivalence = fields.get("equivalence", "")
    n_amd = fields.get("number of amendments", "").strip()
    item.number_of_amendments = _as_int(n_amd) if n_amd else None

    return item


def _scalar(value) -> str:
    """archive.org returns a str for single values and a list for repeated ones."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value)
    return str(value)


def _as_int(value) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


# ----------------------------------------------------------------------
# scraping
# ----------------------------------------------------------------------
def iter_collection(client: HttpClient, *, query: str = DEFAULT_QUERY,
                    max_items: Optional[int] = None,
                    page_size: int = MAX_ROWS) -> Iterator[dict]:
    """Yield raw search docs for the whole `gov.in.is.*` collection.

    Only metadata fields are fetched here -- no per-item HTTP calls -- so
    listing all 22k items costs ~111 requests.
    """
    params = {
        "q": query,
        "fl[]": SEARCH_FIELDS,
        "sort[]": "identifier asc",
        "output": "json",
    }
    yield from iter_pages(
        client, ADVANCED_SEARCH_URL, params,
        page_size=page_size, max_items=max_items,
        extract=lambda payload: iter(payload.get("response", {}).get("docs", []) or []),
    )


def get_item(client: HttpClient, identifier: str) -> ArchiveItem:
    """Fetch and normalise full metadata (including the file list) for one item."""
    payload = client.get_json(METADATA_URL.format(identifier=identifier))
    return parse_item(payload, identifier=identifier)


def fetch_text(client: HttpClient, item: ArchiveItem) -> Optional[str]:
    """Return the item's OCR text, or None if it is restricted or has none."""
    target = item.best_text_file()
    if target is None:
        log.info("%s: no unrestricted text derivative", item.identifier)
        return None
    try:
        return client.get(target.url, use_cache=False).text
    except HttpError as exc:
        if exc.status in (401, 403):
            log.warning("%s: %s is access-restricted (HTTP %s), skipping",
                        item.identifier, target.name, exc.status)
            return None
        raise


def scrape(client: HttpClient, out_dir: Path, *, query: str = DEFAULT_QUERY,
           max_items: Optional[int] = None, download_text: bool = True,
           download_pdfs: bool = False, on_progress=None) -> list[ArchiveItem]:
    """Run the archive.org scrape end to end.

    Writes ``items.jsonl`` (one normalised item per line, resumable) plus, when
    requested, the OCR text and/or PDF for each item.
    """
    out_dir = Path(out_dir)
    (out_dir / "text").mkdir(parents=True, exist_ok=True)
    if download_pdfs:
        (out_dir / "pdf").mkdir(parents=True, exist_ok=True)

    jsonl = out_dir / "items.jsonl"
    done = _load_done(jsonl)
    if done:
        log.info("resuming: %d items already recorded", len(done))

    items: list[ArchiveItem] = []
    skipped_restricted = 0

    with open(jsonl, "a", encoding="utf-8") as sink:
        for doc in iter_collection(client, query=query, max_items=max_items):
            identifier = doc.get("identifier")
            if not identifier or identifier in done:
                continue

            try:
                item = get_item(client, identifier)
            except HttpError as exc:
                log.warning("%s: metadata fetch failed (%s)", identifier, exc)
                continue

            if item.is_access_restricted:
                skipped_restricted += 1
                log.info("%s: access-restricted, skipping", identifier)
                continue

            if download_text:
                text = fetch_text(client, item)
                if text is not None:
                    (out_dir / "text" / f"{identifier}.txt").write_text(text, encoding="utf-8")

            if download_pdfs:
                pdf = item.best_pdf_file()
                if pdf is not None:
                    try:
                        client.download(pdf.url, out_dir / "pdf" / pdf.name,
                                        expected_md5=pdf.md5)
                    except HttpError as exc:
                        log.warning("%s: pdf download failed (%s)", identifier, exc)

            items.append(item)
            sink.write(json.dumps(_serialise(item)) + "\n")
            sink.flush()
            if on_progress:
                on_progress(len(items))

    log.info("archive.org: %d items, %d skipped as access-restricted",
             len(items), skipped_restricted)
    return items


def _serialise(item: ArchiveItem) -> dict:
    data = dataclasses.asdict(item)
    desig = item.designation
    data["designation"] = desig.format() if desig else None
    data["designation_canonical"] = desig.canonical if desig else None
    return data


def _load_done(jsonl: Path) -> set[str]:
    if not jsonl.exists():
        return set()
    out = set()
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        try:
            out.add(json.loads(line)["identifier"])
        except (ValueError, KeyError):
            continue
    return out
