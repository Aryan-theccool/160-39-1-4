"""BIS / Indian Standards data pipeline.

Three sources, one dataset:

``archive_scraper``
    archive.org's ``gov.in.is.*`` collection -- ~22k CC0-licensed BIS standards
    with metadata and ready-made OCR text.
``mandatory``
    BIS's compulsory-certification (QCO) IS numbers, from www.bis.gov.in.
``merger``
    Collapses both onto one row per IS designation, resolving which edition of
    each standard is current.

See ``docs/CORRECTIONS.md`` for what changed versus the original build guide
and why.
"""

__version__ = "1.0.0"

__all__ = [
    "archive_scraper",
    "http",
    "index",
    "iscode",
    "mandatory",
    "merger",
    "__version__",
]
