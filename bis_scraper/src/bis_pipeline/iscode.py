"""Grammar for Indian Standard (IS) designations.

This module is deliberately *narrow*. Its only job is to turn the many ways an
IS designation gets written -- by BIS, by OCR engines, by archive.org
identifiers, by hand -- into one canonical key so records from different
sources can be joined.

The corpus this runs against is archive.org's `gov.in.is.*` collection, which
is Carl Malamud's Public.Resource.Org upload of BIS standards. Those items are
1960s-1990s scans run through ABBYY FineReader, so the OCR text is *not*
trustworthy for identifiers. All three of these lines appear in the same
document and name the same standard:

    IS 11367 (1985)            <- correct, from archive.org metadata
    IS 1 113C7 - 1905          <- the same thing in the OCR text layer
    IS : 11367 . IMS           <- ditto

That is why `parse_designation` returns ``None`` rather than guessing, and why
nothing in this pipeline ever recovers an IS number *from* OCR text.
Identifiers come from metadata; OCR text is used for retrieval only.

Grammar accepted (case-insensitive):

    IS   14220
    IS   14220 : 1994
    IS   12970-3-2 : 1992
    IS   15844 (Part 1) : 2023
    IS   10322 (Part 5 / Section 9) : 2017
    IS   302-2-15 : 2009
    IS   11367 (1985)
    IS   4503 (Part 1) : 2001 (Reaffirmed 2012)
    IS/IEC 61730-1 : 2012
    SP   7 : 2026
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

#: Prefixes BIS uses for its own publications. `IS` is an Indian Standard,
#: `SP` a Special Publication (handbooks / codes of practice), `IS/IEC` and
#: `IS/ISO` are adopted international standards.
KNOWN_PREFIXES = ("IS/IEC", "IS/ISO", "IS", "SP")

_YEAR = r"(?:18|19|20)\d{2}"
_SEP = r"[:\-.\u2013]"

# A dotted-or-dashed numeric chain: 302, 302-2, 12970.3.2
_CHAIN = r"\d+(?:\s*[-.\u2013]\s*\d+)*"

# Three ordered alternatives. Order matters: the parenthesised `Part`/`Section`
# spelling is tried first so that a bare `(1985)` cannot be mistaken for
# `Part 1985`.
#
# `kw`/`part`/`section`  <- parenthesised: "(Part 5 / Section 9)", "(Section 2)"
# `paren_year`           <- "(1985)"
# `bkw`/`bpart`/`bsection`<- BIS's unparenthesised form: "Part 1: 2012"
_PART = (
    rf"(?:"
    rf"\s*\(\s*(?P<kw>Part|Sec(?:tion)?\.?)\s*(?P<part>\d+)"
    rf"(?:\s*/\s*Sec(?:tion)?\.?\s*(?P<section>\d+))?\s*\)"
    rf"|\s*\(\s*(?P<paren_year>{_YEAR})\s*\)"
    rf"|\s+(?P<bkw>Part|Sec(?:tion)?\.?)\s*(?P<bpart>\d+)"
    rf"(?:\s*/\s*Sec(?:tion)?\.?\s*(?P<bsection>\d+))?"
    rf")?"
)

# A year may follow a separator (`: 2009`) or sit bare in parens (`(1985)`).
_YEAR_PART = (
    rf"(?:\s*{_SEP}\s*(?P<year>{_YEAR})"
    rf"|\s+(?P<year_spaced>{_YEAR})(?![\d.])"
    rf")?"
)

# A trailing `(Reaffirmed 2012)` / `(Reaffirmation 2012)` annotation.
_REAFFIRM = rf"(?:\s*\(\s*Reaffirm(?:ed|ation)?\.?\s*(?P<reaffirmed>{_YEAR})\s*\))?"

_CORE = (
    rf"(?P<prefix>IS/IEC|IS/ISO|IS|SP)\s*:?\s*"
    rf"(?P<number>{_CHAIN})"
    rf"{_PART}"
    rf"{_YEAR_PART}"
    rf"{_REAFFIRM}"
)

# Whole-string form. The leading `\b` and trailing `\s*$` make this refuse
# anything with trailing junk.
_FULL_RE = re.compile(rf"\b{_CORE}\s*$", re.IGNORECASE)

# Scanning form, for `find_all`. Deliberately NOT anchored at the end, so it can
# find several designations in one blob of body text.
#
# The lookahead does two jobs:
#   * `(?!\s*\d)` rejects a mangled scan like "IS 1 113C7 - 1905", which would
#     otherwise yield a bogus `IS 1`.
#   * `(?!\s*(?:part|sec|reaffirm|:|-)\b)` stops the engine from *backtracking*
#     to a shorter match. Without it, "IS 16103 Part 1: 2012" scans as a bare
#     `IS 16103` -- the Part and year silently vanish, which would merge
#     different parts of the same standard into one record.
_SCAN_RE = re.compile(
    rf"\b{_CORE}(?!\s*\d)(?!\s*(?:part|sec(?:tion)?|reaffirm(?:ed|ation)?|:|-)\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Designation:
    """A parsed IS designation.

    `canonical` is the join key. Two strings naming the same standard produce
    the same canonical value:

        >>> parse_designation("IS 302-2-15 : 2009").canonical
        'IS|302|2|15|2009|None'
        >>> parse_designation("is 302 (part 2 / section 15):2009").canonical
        'IS|302|2|15|2009|None'
    """

    prefix: str
    number: int
    part: Optional[int] = None
    section: Optional[int] = None
    year: Optional[int] = None
    reaffirmed: Optional[int] = None

    @property
    def key_without_year(self) -> str:
        """Canonical key ignoring publication year and reaffirmation.

        Use this to group every edition of a standard together, e.g. to work
        out which edition of IS 14220 is the newest.
        """
        return self._key(include_year=False)

    @property
    def canonical(self) -> str:
        return self._key(include_year=True)

    def _key(self, *, include_year: bool) -> str:
        parts = [self.prefix, str(self.number), str(self.part), str(self.section)]
        if include_year:
            parts.append(str(self.year))
            parts.append(str(self.reaffirmed))
        return "|".join(parts)

    def format(self) -> str:
        """Render back to canonical BIS notation, e.g. ``IS 302-2-15:2009``."""
        out = f"{self.prefix} {self.number}"
        if self.part is not None:
            out += f" (Part {self.part}"
            if self.section is not None:
                out += f" / Section {self.section}"
            out += ")"
        elif self.section is not None:
            out += f" (Section {self.section})"
        if self.year is not None:
            out += f":{self.year}"
        if self.reaffirmed is not None:
            out += f" (Reaffirmed {self.reaffirmed})"
        return out

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.format()


def _as_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:  # pragma: no cover - the regex already constrains this
        return None


def _first_int(gd: dict, *names: str) -> Optional[int]:
    for name in names:
        value = gd.get(name)
        if value is not None:
            return _as_int(value)
    return None


def _build(m: "re.Match[str]") -> Optional[Designation]:
    gd = m.groupdict()
    prefix = gd["prefix"].upper().replace(" ", "")

    # `number` may be a whole chain ("302-2-15"). Split it: the head is the IS
    # number and any further segments are an implicit part/section.
    segments = [s for s in re.split(r"\s*[-.\u2013]\s*", gd["number"].strip()) if s]
    if not segments:
        return None
    try:
        numbers = [int(s) for s in segments]
    except ValueError:  # pragma: no cover - the regex already constrains this
        return None

    number = numbers[0]
    chain_part = numbers[1] if len(numbers) > 1 else None
    chain_section = numbers[2] if len(numbers) > 2 else None

    explicit_part = _as_int(gd.get("part"))
    explicit_section = _as_int(gd.get("section"))

    # BIS's own tables also write "IS 16103 Part 1: 2012" without parentheses.
    if explicit_part is None and gd.get("bpart") is not None:
        bare_section = _as_int(gd.get("bsection"))
        if (gd.get("bkw") or "").lower().rstrip(".").startswith("sec") and bare_section is None:
            explicit_section = _as_int(gd.get("bpart"))
        else:
            explicit_part = _as_int(gd.get("bpart"))
            explicit_section = bare_section

    # `(Section 2)` with no Part means an unnamed part's section 2, not part 2.
    kw = (gd.get("kw") or "").lower().rstrip(".")
    paren_was_section = kw.startswith("sec") and explicit_section is None
    if paren_was_section:
        explicit_section, explicit_part = explicit_part, None

    paren_year = _as_int(gd.get("paren_year"))
    year = _first_int(gd, "year", "year_spaced") or paren_year
    reaffirmed = _as_int(gd.get("reaffirmed"))

    if explicit_part is None and chain_part is not None:
        if paren_was_section:
            # "IS 302-2 (Section 9)": chain is the part, parens the section.
            # `explicit_section` already holds 9 -- do not overwrite it.
            if chain_section is not None:
                return None
            explicit_part, chain_part = chain_part, None
        elif explicit_section is not None:
            # "IS 302-2 (Part 5 / Section 9)" written with a bare `(5 / Section 9)`.
            if chain_section is not None:
                return None
            explicit_part, chain_part = chain_part, None
        elif re.fullmatch(_YEAR, str(chain_part)) and chain_section is None:
            if year is not None or paren_year is not None:
                # Both a part-looking and a year-looking reading exist and they
                # contradict each other. Refuse rather than pick one.
                return None
            # "IS 232-1985" means IS 232:1985, not Part 1985.
            year, chain_part = chain_part, None

    part = explicit_part if explicit_part is not None else chain_part
    section = explicit_section if explicit_section is not None else chain_section

    # Two spellings of the same field that disagree -> malformed, do not guess.
    if explicit_part is not None and chain_part is not None and explicit_part != chain_part:
        return None
    if explicit_section is not None and chain_section is not None and explicit_section != chain_section:
        return None

    return Designation(
        prefix=prefix,
        number=number,
        part=part,
        section=section,
        year=year,
        reaffirmed=reaffirmed,
    )


def parse_designation(raw: str) -> Optional[Designation]:
    """Parse a single IS designation string.

    Returns ``None`` when the string is not a well-formed designation instead of
    raising, because callers routinely feed this OCR output and free text.

        >>> parse_designation("IS 11367 (1985)").format()
        'IS 11367:1985'
        >>> parse_designation("IS 1 113C7 - 1905") is None
        True
        >>> parse_designation("hello world") is None
        True
    """
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    m = _FULL_RE.match(text)
    return _build(m) if m else None


def designation_from_identifier(identifier: str) -> Optional[Designation]:
    """Derive a designation from an archive.org ``gov.in.is.*`` identifier.

    Identifiers in this collection are mechanically derived and far more
    reliable than the OCR text:

        gov.in.is.11367.1985      -> IS 11367:1985
        gov.in.is.12970.3.2.1992  -> IS 12970 (Part 3 / Section 2):1992
        gov.in.is.104.1979        -> IS 104:1979

    Returns ``None`` for identifiers outside this scheme, so callers can tell
    "not an IS item" apart from "failed to parse".
    """
    if not identifier or not identifier.lower().startswith("gov.in.is."):
        return None

    chunks = [c for c in identifier[len("gov.in.is."):].split(".") if c]
    if not chunks or not all(c.isdigit() for c in chunks):
        return None

    numbers = [int(c) for c in chunks]

    # A trailing 4-digit chunk in a plausible year range is the publication year.
    year = None
    if len(numbers) >= 2 and re.fullmatch(_YEAR, str(numbers[-1])):
        year = numbers.pop()

    if not numbers:
        return None

    return Designation(
        prefix="IS",
        number=numbers[0],
        part=numbers[1] if len(numbers) > 1 else None,
        section=numbers[2] if len(numbers) > 2 else None,
        year=year,
    )


def find_all(raw: str) -> list[Designation]:
    """Extract every well-formed designation appearing in free text.

    Use this to pull *cross-references* out of a standard's body -- a Foreword
    typically cites a dozen other IS numbers. Never use it to decide which
    standard a document *is*; see the module docstring.
    """
    if not raw:
        return []
    return [d for d in (_build(m) for m in _SCAN_RE.finditer(raw)) if d is not None]


def yearless_key(text: str) -> str:
    """Reduce a designation, canonical id, or bare number to a comparison key.

    Handles all three shapes the codebase produces:

        "IS 269:1989"                    -> "is 269"
        "IS|269|None|None|1989|None"     -> "is 269"          (canonical id)
        "is 269"                         -> "is 269"
        "IS 302 (Part 2):2009"           -> "is 302 (part 2)"

    Matching on a year-less key is not a shortcut: a QCO names a *standard*, not
    an edition, so the notification for IS 269 applies to whichever edition is
    current. Matching the year would make the check silently edition-dependent.
    """
    if not text:
        return ""
    raw = text.strip()

    if "|" in raw:
        parts = raw.split("|")
        prefix, number = parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""
        key = f"{prefix} {number}".lower()
        if len(parts) > 2 and parts[2] not in ("None", "", "nan"):
            key += f" (part {parts[2]})"
        if len(parts) > 3 and parts[3] not in ("None", "", "nan"):
            key += f" (section {parts[3]})"
        return key

    parsed = parse_designation(raw)
    if parsed is not None:
        key = f"{parsed.prefix} {parsed.number}".lower()
        if parsed.part is not None:
            key += f" (part {parsed.part})"
        if parsed.section is not None:
            key += f" (section {parsed.section})"
        return key

    # Bare input such as "IS 269" or a product name: normalise what we can.
    return " ".join(raw.lower().split())
