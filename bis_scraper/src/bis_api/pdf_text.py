"""Text extraction from uploaded PDFs, with an honest quality report.

Why this is not just ``fitz.open(...).get_text()``
--------------------------------------------------
``PyMuPDF`` is excellent and is used when installed. It is also an *optional*
dependency in this repository (see ``requirements.txt``: "only if you must read
scanned PDFs"), which means a deployment can legitimately not have it. Rather
than 500 on upload, this module falls back to a small extractor built on
``zlib`` and the PDF text operators, and **reports which extractor ran and how
much text it recovered**.

That report matters more than it looks. A scanned PDF has no text layer at all:
every extractor returns "" and the honest answer is "this is an image, run OCR",
not a 200 response with an empty query that silently retrieves the whole corpus.
:class:`ExtractionResult` therefore carries ``ok`` and a ``reason``, and the
upload endpoint refuses to search on nothing.
"""

from __future__ import annotations

import logging
import re
import zlib
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

__all__ = ["ExtractionResult", "extract_text", "extractor_name", "pdf_library_available"]

#: Below this many characters a PDF is treated as having no usable text layer.
#: The gap this separates is enormous -- a real spec sheet yields thousands of
#: characters, a scan yields exactly zero -- so the threshold only has to be
#: above zero and below a plausible one-line document. 40 rejected a legitimate
#: single-clause PDF ("Steel tubes shall comply with IS 1239." is 38 characters),
#: so it is 25: still far above the noise a broken extraction produces.
MIN_USABLE_CHARS = 25

_PDF_STRING_RE = re.compile(rb"\((?:\\.|[^\\()])*\)", re.DOTALL)
#: A text object runs from ``BT`` to ``ET``. Both must be *tokens*, not
#: substrings: a non-greedy ``BT.*?ET`` stops at the "ET" inside "SHEET" or
#: "CONCRETE", which silently truncates extraction on the first page of almost
#: any Indian Standard. ``(?<![A-Za-z0-9])`` is the token boundary.
_TEXT_OP_RE = re.compile(
    rb"(?s)(?<![A-Za-z0-9])BT(?![A-Za-z0-9])(.*?)(?<![A-Za-z0-9])ET(?![A-Za-z0-9])"
)
_STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)


@dataclass
class ExtractionResult:
    text: str = ""
    #: ``pymupdf`` | ``builtin`` | ``none``
    extractor: str = "none"
    pages: int = 0
    ok: bool = False
    reason: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def chars(self) -> int:
        return len(self.text)

    def as_dict(self) -> dict:
        return {
            "extractor": self.extractor,
            "pages": self.pages,
            "chars": self.chars,
            "ok": self.ok,
            "reason": self.reason,
            "warnings": self.warnings,
        }


def pdf_library_available() -> bool:
    import importlib.util

    return (importlib.util.find_spec("pymupdf") is not None
            or importlib.util.find_spec("fitz") is not None)


def extractor_name() -> str:
    return "pymupdf" if pdf_library_available() else "builtin (no pymupdf)"


def extract_text(data: bytes, *, max_chars: int = 20_000) -> ExtractionResult:
    """Extract text from PDF bytes.

    Tries PyMuPDF, then the built-in extractor. Never raises on malformed input:
    a corrupt or encrypted upload is a user error that deserves a 422 with a
    reason, not a traceback.
    """
    if not data:
        return ExtractionResult(extractor="none", ok=False, reason="the uploaded file is empty")
    if not data.lstrip()[:5].startswith(b"%PDF"):
        return ExtractionResult(
            extractor="none", ok=False,
            reason="the uploaded file is not a PDF (no %PDF header)",
        )

    if pdf_library_available():
        result = _extract_with_pymupdf(data, max_chars=max_chars)
        if result.ok:
            return result
        # PyMuPDF ran but found nothing; the built-in may still recover text
        # from a document PyMuPDF could not parse, so try before giving up.
        fallback = _extract_builtin(data, max_chars=max_chars)
        if fallback.ok:
            fallback.warnings.append(
                f"PyMuPDF found no text ({result.reason}); recovered by the built-in extractor"
            )
            return fallback
        return result

    result = _extract_builtin(data, max_chars=max_chars)
    if not result.ok and result.reason:
        result.warnings.append(
            "install PyMuPDF for more reliable PDF text extraction: "
            "pip install 'bis-pipeline[pdf]'"
        )
    return result


# ----------------------------------------------------------------------
def _extract_with_pymupdf(data: bytes, *, max_chars: int) -> ExtractionResult:
    # `fitz` is the historical PyMuPDF module name and is deprecated in current
    # releases; prefer `pymupdf` where it exists, and fall back for old installs.
    try:
        import pymupdf as fitz
    except ImportError:                                     # PyMuPDF < 1.24
        import fitz  # type: ignore[no-redef]

    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        return ExtractionResult(extractor="pymupdf", ok=False,
                                reason=f"PyMuPDF could not open the file ({exc})")

    try:
        if document.needs_pass:
            return ExtractionResult(
                extractor="pymupdf", pages=document.page_count, ok=False,
                reason="the PDF is password-protected; remove the password and retry",
            )
        pages = document.page_count
        chunks: list[str] = []
        total = 0
        for page in document:
            text = page.get_text() or ""
            chunks.append(text)
            total += len(text)
            if total >= max_chars:
                break
        joined = "\n".join(chunks).strip()
    finally:
        document.close()

    warnings: list[str] = []
    if len(joined) > max_chars:
        warnings.append(f"text truncated to {max_chars} characters")
    joined = joined[:max_chars]

    if len(joined) < MIN_USABLE_CHARS:
        return ExtractionResult(
            extractor="pymupdf", pages=pages, text=joined, ok=False,
            reason=("no text layer found -- this looks like a scanned document. "
                    "Upload a text-based PDF, or run OCR first"),
        )
    return ExtractionResult(text=joined, extractor="pymupdf", pages=pages, ok=True,
                            warnings=warnings)


def _extract_builtin(data: bytes, *, max_chars: int) -> ExtractionResult:
    """Dependency-free extraction: inflate content streams, read text operators.

    Handles the common cases -- uncompressed streams and FlateDecode streams
    with simple ``(string) Tj`` / ``[array] TJ`` operators. It does **not**
    resolve font encodings or ``ToUnicode`` CMaps, so a PDF using an embedded
    CID font can come back as mojibake or empty. That limitation is the reason
    the PyMuPDF path exists and the reason this reports its extractor name.
    """
    warnings: list[str] = []
    pieces: list[str] = []

    for match in _STREAM_RE.finditer(data):
        raw = match.group(1)
        stream = raw
        if not raw.lstrip().startswith(b"BT"):
            # Probably a compressed content stream.
            for candidate in (raw, raw.strip()):
                try:
                    stream = zlib.decompress(candidate)
                    break
                except zlib.error:
                    stream = raw
        if b"Tj" not in stream and b"TJ" not in stream:
            continue
        found: list[str] = []
        for text_op in _TEXT_OP_RE.finditer(stream):
            found.extend(_strings_in(text_op.group(1)))
        if not found:
            # The BT/ET scan found nothing usable -- an unusual or broken stream
            # layout, not necessarily an empty one. Take every literal string in
            # the stream rather than reporting "no text layer" and telling the
            # user to go install OCR for a PDF that has perfectly good text.
            found = _strings_in(stream)
            if found:
                warnings.append(
                    "recovered text by scanning the raw content stream; text "
                    "ordering may be approximate"
                )
        pieces.extend(found)

    text = _tidy(" ".join(pieces))
    if len(text) > max_chars:
        text = text[:max_chars]
        warnings.append(f"text truncated to {max_chars} characters")

    if len(text) < MIN_USABLE_CHARS:
        return ExtractionResult(
            extractor="builtin", text=text, ok=False, warnings=warnings,
            reason=("no text layer found with the built-in extractor. The PDF may be "
                    "scanned, encrypted, or use font encoding it cannot resolve -- "
                    "install PyMuPDF to retry: pip install pymupdf"),
        )
    warnings.append(
        "text extracted without PyMuPDF; ordering and special characters may be imperfect"
    )
    return ExtractionResult(text=text, extractor="builtin", ok=True, warnings=warnings)


def _strings_in(block: bytes) -> list[str]:
    out: list[str] = []
    for match in _PDF_STRING_RE.finditer(block):
        raw = match.group(0)[1:-1]
        raw = raw.replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\")
        # Octal escapes, e.g. \351 for a Latin-1 accented character.
        raw = re.sub(rb"\\([0-7]{1,3})", lambda m: bytes([int(m.group(1), 8) & 0xFF]), raw)
        try:
            out.append(raw.decode("latin-1"))
        except Exception:  # pragma: no cover - latin-1 decodes everything
            continue
    return out


def _tidy(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def build_query(text: str, *, max_chars: int) -> str:
    """Reduce extracted document text to something worth searching with.

    A whole spec sheet used verbatim as a retrieval query performs *worse* than
    a short one: BM25 term counts get dominated by boilerplate ("page 1 of 12",
    revision tables) and the dense embedding is an average over unrelated
    sections. Taking the head of the document is a crude but effective proxy --
    in a standard or spec sheet the Scope and title are in the first page.
    """
    flat = " ".join(text.split())
    if len(flat) <= max_chars:
        return flat
    return flat[:max_chars]
