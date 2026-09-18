"""Compliance checking against BIS Quality Control Orders (QCOs). Part 4.

Read this before trusting a verdict
-----------------------------------
A compliance checker is the one component in this system whose output can cost
someone money, or a licence. Two things follow from that.

**1. The mandatory-standard list is legal data, and this module prefers the
real source.** QCO status is created by government notification; it changes, and
a stale list produces a confident wrong answer. So the QCO set is resolved in
tiers, best first:

    tier 1  ``bis_data/mandatory/mandatory.json``
            The output of ``bis-pipeline mandatory``, scraped from BIS's own
            "products under compulsory certification" page. Each entry carries
            the ``source_url`` it came from, so a verdict can be audited.
    tier 2  ``is_compulsory`` in ``merged_standards.json``
            The same scrape, after a merge, for data directories where
            ``mandatory.json`` was not kept.
    tier 3  :data:`SEED_QCO`
            ~50 well-known product standards, hardcoded here so the checker does
            something useful before the scrape has been run. **Unverified**: no
            notification years, no source URLs, and possibly incomplete or out
            of date.

The tier in use is reported on every result (``qco_source``) and, when it is
``seed``, the report **cannot return a fully-compliant grade** -- because an
incomplete list of mandatory standards cannot prove compliance. It can still
report "this standard you are using is superseded" and "this standard is known
to be mandatory and is missing from your list", which is most of the value.

**2. Compliance is a conjunction, not an average.** If a product needs IS 269 and
IS 1786 and you are missing IS 269, you are not "67% compliant" in any sense a
regulator would accept, whatever the arithmetic says. :func:`ComplianceChecker.analyze`
therefore computes the score the brief specifies *and* applies a hard override:
any missing mandatory standard caps the grade at ``NON_COMPLIANT``. The score is
kept as a summary of how much work is left, not as a verdict.

What this does *not* do
-----------------------
It does not decide whether your product needs certification. It compares the
standards you are working to against the mandatory list the pipeline holds, and
tells you what it cannot see. Absence of a warning is not legal advice.
"""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from bis_pipeline import iscode

from .data import BisData
from .schema import Standard, load_json

log = logging.getLogger(__name__)

__all__ = [
    "QCOEntry", "QCODatabase", "SEED_QCO", "SECTOR_RULES", "detect_sector",
    "ComplianceReport", "ComplianceChecker", "render_html", "GRADE_BANDS",
]

#: Grade bands, highest first. Boundaries are inclusive lower bounds, so the
#: brief's overlapping ranges (0.7-0.9 and 0.9-1.0 both containing 0.9) resolve
#: deterministically. ``min_mandatory_present`` is the extra condition: without
#: it a product missing a mandatory standard could still score "fully
#: compliant", which is the one output this module must never produce.
GRADE_BANDS: tuple[tuple[float, str, bool], ...] = (
    (0.90, "FULLY COMPLIANT", True),
    (0.70, "MOSTLY COMPLIANT", False),
    (0.50, "PARTIALLY COMPLIANT", False),
    (0.00, "NON-COMPLIANT", False),
)

#: Score weights from the brief: mandatory presence dominates, edition currency
#: matters, conflicts are a smaller deduction.
WEIGHT_MANDATORY = 0.7
WEIGHT_CURRENCY = 0.2
WEIGHT_CONFLICTS = 0.1


# ----------------------------------------------------------------------
# the seed list (tier 3)
# ----------------------------------------------------------------------
#: Bootstrap QCO entries. product sectors named generically; no notification
#: years, because a wrong year is worse than no year and the authoritative
#: years live in the scrape. See the module docstring on why tier 3 cannot
#: produce a "fully compliant" verdict.
#:
#: Replace wholesale by running:  python -m bis_pipeline mandatory
SEED_QCO: dict[str, dict[str, str]] = {
    # -- construction materials ---------------------------------------
    "is 269": {"product": "33 grade ordinary Portland cement", "sector": "construction"},
    "is 455": {"product": "Portland slag cement", "sector": "construction"},
    "is 1489": {"product": "Portland pozzolana cement", "sector": "construction"},
    "is 8041": {"product": "rapid hardening Portland cement", "sector": "construction"},
    "is 8112": {"product": "43 grade ordinary Portland cement", "sector": "construction"},
    "is 12269": {"product": "53 grade ordinary Portland cement", "sector": "construction"},
    "is 383": {"product": "coarse and fine aggregates for concrete", "sector": "construction"},
    "is 1786": {"product": "high strength deformed steel bars for reinforcement",
                "sector": "construction"},
    "is 432": {"product": "mild steel bars for concrete reinforcement",
               "sector": "construction"},
    "is 458": {"product": "precast concrete pipes", "sector": "construction"},
    "is 1536": {"product": "centrifugally cast iron pressure pipes",
                "sector": "construction"},
    "is 1077": {"product": "common burnt clay building bricks", "sector": "construction"},
    "is 2185": {"product": "concrete masonry units", "sector": "construction"},
    # -- electrical and electronics ------------------------------------
    "is 302": {"product": "safety of household and similar electrical appliances",
               "sector": "electrical"},
    "is 694": {"product": "PVC insulated cables for working voltages up to 1100 V",
               "sector": "electrical"},
    "is 1554": {"product": "PVC insulated cables", "sector": "electrical"},
    "is 7098": {"product": "cross-linked polyethylene insulated cables",
                "sector": "electrical"},
    "is 1293": {"product": "plugs and socket outlets", "sector": "electrical"},
    "is 8828": {"product": "miniature circuit breakers", "sector": "electrical"},
    "is 616": {"product": "safety of audio, video and similar electronic apparatus",
               "sector": "electrical"},
    "is 13252": {"product": "safety of information technology equipment",
                 "sector": "electrical"},
    "is 14700": {"product": "electromagnetic compatibility of electrical equipment",
                 "sector": "electrical"},
    # -- water supply and plumbing -------------------------------------
    "is 4985": {"product": "unplasticized PVC pipes for potable water",
                "sector": "water_supply"},
    "is 1239": {"product": "steel tubes and tubular fittings", "sector": "water_supply"},
    "is 1879": {"product": "cast iron fittings for water and gas", "sector": "water_supply"},
    "is 14543": {"product": "packaged drinking water", "sector": "water_supply"},
    "is 13488": {"product": "water meters", "sector": "water_supply"},
    # -- mechanical, automotive and safety -----------------------------
    "is 14220": {"product": "submersible pumpsets", "sector": "mechanical"},
    "is 8472": {"product": "centrifugal pumps", "sector": "mechanical"},
    "is 5120": {"product": "gas cylinders", "sector": "mechanical"},
    "is 3196": {"product": "LPG cylinders", "sector": "mechanical"},
    "is 4151": {"product": "protective helmets for motorcycle riders",
                "sector": "mechanical"},
    "is 15298": {"product": "footwear", "sector": "mechanical"},
    "is 3055": {"product": "clinical thermometers", "sector": "mechanical"},
    "is 9873": {"product": "safety of toys", "sector": "mechanical"},
    # -- food and packaging --------------------------------------------
    "is 1165": {"product": "milk powder", "sector": "food"},
    "is 1479": {"product": "condensed milk", "sector": "food"},
    "is 14433": {"product": "infant milk substitutes", "sector": "food"},
    "is 4707": {"product": "food colours", "sector": "food"},
    "is 7215": {"product": "code of practice for food packaging", "sector": "food"},
    # -- textiles and other --------------------------------------------
    "is 121": {"product": "medium density fibre boards", "sector": "construction"},
    "is 1566": {"product": "hard drawn steel wire for prestressed concrete",
                "sector": "construction"},
    "is 6003": {"product": "cement concrete flooring tiles", "sector": "construction"},
    "is 2096": {"product": "non-load bearing gypsum partition slabs", "sector": "construction"},
}

#: Sector -> indicative standard numbers, used for *routing and suggestions*.
#: Deliberately separate from :data:`SEED_QCO`: a sector list may name a code of
#: practice that is not itself QCO-mandated (IS 732, IS 456), and conflating the
#: two would turn a suggestion into a false legal claim.
SECTOR_RULES: dict[str, tuple[str, ...]] = {
    "construction": ("IS 456", "IS 1786", "IS 383", "IS 269", "IS 1489", "IS 458"),
    "electrical": ("IS 302", "IS 694", "IS 732", "IS 616", "IS 1293", "IS 8828"),
    "water_supply": ("IS 4985", "IS 10500", "IS 1239", "IS 14543", "IS 13488"),
    "mechanical": ("IS 14220", "IS 1608", "IS 8472", "IS 4151"),
    "food": ("IS 1165", "IS 1479", "IS 4707"),
}

#: BIS division -> sector, for QCO entries that carry no sector of their own
#: (the scrape and the merged dataset record a division, not our sector label).
#: Only unambiguous mappings are listed: "Chemical Engineering" covers both
#: water and food standards, so it is deliberately absent rather than guessed --
#: a wrong sector silently produces wrong suggestions, which is worse than none.
_DIVISION_TO_SECTOR: dict[str, str] = {
    "civil engineering": "construction",
    "electrical": "electrical",
    "electronics and information technology": "electrical",
    "electrotechnical": "electrical",
    "mechanical engineering": "mechanical",
    "production and general engineering": "mechanical",
}

#: Minimum shared tokens before a product description is taken to *name* a QCO
#: product. One shared word is not identification: "electrical cable" shares
#: exactly one token with "safety of household and similar electrical
#: appliances", and asserting IS 302 as a requirement for it would be a guess
#: dressed as a finding. Below this threshold the entry is offered as a
#: candidate instead.
MIN_PRODUCT_MATCH = 2

#: Keyword -> sector, for auto-detection from a product description.
#:
#: Every keyword belongs to exactly **one** sector (asserted by a test). When a
#: term appeared in two lists, detection became a coin flip: "water pump"
#: scored one hit in each and whichever dict came first won. Longer, more
#: specific phrases are also weighted more, so "submersible" outweighs the
#: generic "water".
_SECTOR_KEYWORDS: dict[str, tuple[str, ...]] = {
    "construction": ("cement", "concrete", "aggregate", "steel bar", "reinforcement",
                     "brick", "masonry", "tile", "slab", "builder", "building",
                     "civil", "column", "beam", "foundation", "rcc", "tmt",
                     "portland", "pozzolana"),
    "electrical": ("electrical", "electric", "appliance", "cable", "wire", "switch",
                   "socket", "plug", "circuit breaker", "mcb", "transformer",
                   "led", "lamp", "voltage", "insulated", "household",
                   "electronics", "earthing"),
    "water_supply": ("water", "drinking", "potable", "plumbing", "sanitary", "tap",
                     "supply", "bottling", "packaged water", "pipe", "pipeline"),
    "mechanical": ("pump", "pumpset", "submersible", "motor", "helmet", "cylinder",
                   "valve", "gear", "bearing", "machine", "equipment", "toy",
                   "footwear", "thermometer", "compressor", "boiler"),
    "food": ("food", "milk", "edible", "colour", "additive", "beverage", "dairy",
             "infant", "packaging", "confectionery"),
}


def detect_sector(description: str) -> tuple[Optional[str], dict[str, int]]:
    """Guess the sector from a product description.

    Returns ``(sector, keyword_hits)``. The scores are returned rather than
    hidden because sector detection is a heuristic and anything it feeds should
    be debuggable. Scoring is the **sum of matched keyword lengths**, so a
    specific term beats a generic one: "submersible pumpset" scores 14 for
    mechanical against 5 for water_supply from the bare word "water", which is
    the right call. Ties break alphabetically so the result is deterministic
    across runs.

    Returns ``(None, {})`` when nothing matches -- that is a real answer, and
    callers should not substitute a default sector for it.
    """
    text = (description or "").lower()
    if not text.strip():
        return None, {}
    hits: dict[str, int] = {}
    for sector, keywords in _SECTOR_KEYWORDS.items():
        score = sum(len(keyword) for keyword in keywords if keyword in text)
        if score:
            hits[sector] = score
    if not hits:
        return None, {}
    best = max(sorted(hits.items()), key=lambda kv: kv[1])
    return best[0], hits


# ----------------------------------------------------------------------
# the QCO database
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class QCOEntry:
    """A standard that is mandatory under a Quality Control Order."""

    key: str                      # year-less key, e.g. "is 269"
    designation: str
    product: str = ""
    sector: str = ""
    #: Notification year, when known. ``None`` from the seed list on purpose:
    #: only the scraped data carries a date we can attribute.
    qco_year: Optional[int] = None
    source: str = "seed"          # "scraped" | "merged" | "seed"
    verified: bool = False
    source_url: str = ""

    @property
    def is_authoritative(self) -> bool:
        return self.verified and self.source in ("scraped", "merged")

    def as_dict(self) -> dict[str, Any]:
        return {
            "designation": self.designation,
            "product": self.product,
            "sector": self.sector,
            "qco_year": self.qco_year,
            "source": self.source,
            "verified": self.verified,
            "source_url": self.source_url,
        }


# The comparison key lives in iscode.py: it is IS-designation grammar, and both
# the compliance checker and the retriever need it. Keeping two copies would let
# them disagree about what counts as "the same standard".
from bis_pipeline.iscode import yearless_key as _yearless_key  # noqa: E402

#: Public name, for callers outside this module.
yearless_key = _yearless_key


class QCODatabase:
    """The set of standards that are mandatory under a QCO, with provenance."""

    def __init__(self, data: Optional[BisData] = None):
        self.data = data
        self.entries: dict[str, QCOEntry] = {}
        self.source = "none"
        self.notes: list[str] = []
        self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        if self.data is not None and self.data.exists("mandatory"):
            try:
                self._load_scraped()
                return
            except Exception as exc:  # pragma: no cover - defensive
                log.warning("could not read mandatory.json: %s", exc)
                self.notes.append(f"mandatory.json unreadable ({exc}); falling back")

        if self.data is not None:
            derived = self._load_from_merged()
            if derived:
                self.source = "merged"
                self.notes.append(
                    "QCO list derived from is_compulsory in merged_standards.json. "
                    "Run `python -m bis_pipeline mandatory` to refresh it with "
                    "source URLs."
                )
                return

        self._load_seed()

    def _load_scraped(self) -> None:
        rows = load_json(self.data.path("mandatory"))
        for row in rows:
            designation = str(row.get("designation") or "").strip()
            key = _yearless_key(row.get("canonical") or designation)
            if not key:
                continue
            self.entries[key] = QCOEntry(
                key=key,
                designation=designation,
                product=str(row.get("scheme") or row.get("product_category") or ""),
                sector="",
                qco_year=None,
                source="scraped",
                verified=True,
                source_url=str(row.get("source_url") or ""),
            )
        self.source = "scraped" if self.entries else "none"
        if not self.entries:
            raise ValueError("mandatory.json contained no usable rows")
        self.notes.append(
            f"{len(self.entries)} QCO standards loaded from the BIS scrape "
            f"(authoritative, with source URLs)."
        )

    def _load_from_merged(self) -> int:
        found = 0
        try:
            standards = self.data.standards()
        except Exception:
            return 0
        for standard in standards:
            if not standard.is_compulsory:
                continue
            key = _yearless_key(standard.canonical or standard.designation)
            if not key:
                continue
            self.entries[key] = QCOEntry(
                key=key,
                designation=standard.designation,
                product=standard.title,
                sector=_DIVISION_TO_SECTOR.get(standard.division.strip().lower(), ""),
                source="merged",
                verified=True,
                source_url=standard.archive_url,
            )
            found += 1
        return found

    def _load_seed(self) -> None:
        for key, info in SEED_QCO.items():
            normalised = " ".join(key.lower().split())
            self.entries[normalised] = QCOEntry(
                key=normalised,
                designation=normalised.upper(),
                product=info.get("product", ""),
                sector=info.get("sector", ""),
                qco_year=None,
                source="seed",
                verified=False,
                source_url="",
            )
        self.source = "seed"
        self.notes.append(
            f"QCO list is the built-in seed set ({len(self.entries)} entries), which is "
            f"UNVERIFIED and may be incomplete or out of date. Run "
            f"`python -m bis_pipeline mandatory` to replace it with BIS's published list."
        )

    # ------------------------------------------------------------------
    @property
    def verified(self) -> bool:
        return self.source in ("scraped", "merged") and bool(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def lookup(self, designation: str) -> Optional[QCOEntry]:
        """Is this standard mandatory? Matches on the year-less key."""
        return self.entries.get(_yearless_key(designation))

    def is_mandatory(self, designation: str) -> bool:
        return self.lookup(designation) is not None

    def for_sector(self, sector: str) -> list[QCOEntry]:
        wanted = " ".join(sector.lower().split())
        return [e for e in self.entries.values() if e.sector == wanted]

    def match_product(self, description: str) -> list[tuple[int, QCOEntry]]:
        """Score QCO entries against a free-text product description.

        Token overlap rather than substring matching, so "submersible pump set"
        finds "submersible pumpsets". Short *numeric* tokens are kept while
        short words are dropped: "33 grade cement" and "43 grade cement" are
        different products, and dropping the grade makes them indistinguishable.
        """
        words = {w for w in _tokenize(description) if len(w) > 3 or w.isdigit()}
        if not words:
            return []
        scored: list[tuple[int, QCOEntry]] = []
        for entry in self.entries.values():
            product_words = set(_tokenize(entry.product))
            overlap = len(words & product_words)
            if overlap:
                scored.append((overlap, entry))
        scored.sort(key=lambda pair: (-pair[0], pair[1].designation))
        return scored

    def for_product(self, description: str) -> list[QCOEntry]:
        """Entries matching a product description, best match first."""
        return [entry for _, entry in self.match_product(description)]

    def describe(self) -> str:
        flag = "authoritative" if self.verified else "UNVERIFIED (seed)"
        return f"{len(self)} QCO standards, source={self.source} ({flag})"



def _tokenize(text: str) -> list[str]:
    """Lowercase word tokens, with a light plural fold.

    Folding a trailing "s" on longer tokens makes "appliances" match
    "appliance" and "pipes" match "pipe". A real stemmer would be better, but
    product names are short and this captures the common case without a
    dependency -- and it only affects matching, never what is displayed.
    """
    import re

    tokens = []
    for token in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        tokens.append(token)
    return tokens


# ----------------------------------------------------------------------
# results
# ----------------------------------------------------------------------
@dataclass
class ResolvedStandard:
    """One of the caller's recommended standards, matched to the dataset."""

    input_text: str
    designation: str = ""
    canonical: str = ""
    title: str = ""
    found_in_dataset: bool = False
    is_current: bool = True
    is_mandatory: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "input": self.input_text,
            "designation": self.designation or self.input_text,
            "canonical": self.canonical,
            "title": self.title,
            "found_in_dataset": self.found_in_dataset,
            "is_current": self.is_current,
            "is_mandatory": self.is_mandatory,
        }


@dataclass
class ComplianceReport:
    product_description: str
    sector: Optional[str] = None
    sector_hits: dict[str, int] = field(default_factory=dict)

    qco_source: str = "none"
    qco_verified: bool = False
    qco_size: int = 0
    qco_basis: str = ""

    standards: list[ResolvedStandard] = field(default_factory=list)
    mandatory_expected: list[QCOEntry] = field(default_factory=list)
    mandatory_present: list[str] = field(default_factory=list)
    mandatory_missing: list[str] = field(default_factory=list)

    #: QCO standards in the detected sector that the caller did not supply.
    #: Informational only -- deliberately NOT counted as "missing", because a
    #: sector list is not a product-specific requirement. Treating it as one
    #: claimed a cement product was failing 15 standards including bricks and
    #: flooring tiles.
    sector_candidates: list[str] = field(default_factory=list)
    #: QCO entries the product description *might* refer to, when more than one
    #: matched equally well. Surfaced as a question rather than a requirement:
    #: "cement" alone cannot tell us whether the product is 33, 43 or 53 grade,
    #: and guessing would produce a false compliance failure.
    mandatory_candidates: list[str] = field(default_factory=list)
    #: ``[{"used", "replace_with", "replacement_in_dataset"}]``
    superseded_used: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, str]] = field(default_factory=list)

    compliance_score: float = 0.0
    grade: str = "UNKNOWN"
    weights: dict[str, float] = field(default_factory=dict)
    weights_redistributed: bool = False
    grade_capped_by: str = ""

    action_items: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    @property
    def total_mandatory(self) -> int:
        return len(self.mandatory_expected)

    @property
    def is_compliant(self) -> bool:
        return not self.mandatory_missing and not self.superseded_used and not self.conflicts

    def as_dict(self) -> dict[str, Any]:
        return {
            "product_description": self.product_description,
            "sector": self.sector,
            "qco_source": self.qco_source,
            "qco_verified": self.qco_verified,
            "qco_size": self.qco_size,
            "compliance_status": self.status(),
            "mandatory_expected": [e.designation for e in self.mandatory_expected],
            "mandatory_present": self.mandatory_present,
            "mandatory_missing": self.mandatory_missing,
            "sector_candidates": self.sector_candidates,
            "mandatory_candidates": self.mandatory_candidates,
            "superseded_used": self.superseded_used,
            "conflicts": self.conflicts,
            "compliance_score": round(self.compliance_score, 4),
            "grade": self.grade,
            "weights": self.weights,
            "weights_redistributed": self.weights_redistributed,
            "grade_capped_by": self.grade_capped_by,
            "action_items": self.action_items,
            "standards": [s.as_dict() for s in self.standards],
            "notes": self.notes,
            "limitations": self.limitations,
        }

    def status(self) -> str:
        """Coarse status string, matching the brief's vocabulary."""
        if self.grade.startswith("FULLY"):
            return "COMPLIANT"
        if self.mandatory_missing:
            return "NON_COMPLIANT"
        if self.superseded_used or self.conflicts:
            return "PARTIAL"
        return "REVIEW"

    def grade_emoji(self) -> str:
        return {
            "FULLY COMPLIANT": "✅",
            "MOSTLY COMPLIANT": "⚠️",
            "PARTIALLY COMPLIANT": "🟡",
            "NON-COMPLIANT": "❌",
        }.get(self.grade, "•")


# ----------------------------------------------------------------------
# the checker
# ----------------------------------------------------------------------
class ComplianceChecker:
    """Compare a set of standards against the mandatory list."""

    def __init__(self, data: BisData, qco: Optional[QCODatabase] = None):
        self.data = data
        self.qco = qco if qco is not None else QCODatabase(data)

    # ------------------------------------------------------------------
    def resolve(self, item: str | Standard) -> ResolvedStandard:
        """Match one recommended standard to the dataset, tolerantly."""
        if isinstance(item, Standard):
            standard = item
            text = item.designation or item.canonical
        else:
            text = str(item)
            standard = self.data.resolve_designation(text)
            if standard is None:
                # Fall back to the year-less form: "IS 269" should find IS 269:2015.
                key = _yearless_key(text)
                for candidate in self.data.standards():
                    if _yearless_key(candidate.designation) == key:
                        standard = candidate
                        break

        entry = self.qco.lookup(text) if self.qco else None
        if standard is None:
            return ResolvedStandard(
                input_text=text,
                designation=text.strip(),
                found_in_dataset=False,
                is_mandatory=entry is not None,
            )
        return ResolvedStandard(
            input_text=text,
            designation=standard.designation,
            canonical=standard.canonical,
            title=standard.title,
            found_in_dataset=True,
            is_current=standard.is_current,
            is_mandatory=entry is not None,
        )

    # ------------------------------------------------------------------
    def analyze(self, product_description: str = "",
                standards: Sequence[str | Standard] = (),
                *, sector: Optional[str] = None) -> ComplianceReport:
        """Assess a standard set against the QCO list for the product."""
        report = ComplianceReport(
            product_description=product_description or "",
            qco_source=self.qco.source,
            qco_verified=self.qco.verified,
            qco_size=len(self.qco),
            qco_basis=self.qco.describe(),
        )
        report.notes.extend(self.qco.notes)
        report.limitations.extend(self._limitations())

        # -- sector ----------------------------------------------------
        if sector:
            report.sector = sector
        else:
            report.sector, report.sector_hits = detect_sector(product_description)
        if report.sector:
            report.notes.append(
                f"sector detected as {report.sector!r} "
                f"(keyword hits: {report.sector_hits})"
            )

        # -- resolve the caller's standards ----------------------------
        # Deduplicated by *edition*, first occurrence wins. Callers routinely
        # pass one entry per retrieved passage, so IS 269:1989 could arrive five
        # times and produce five identical "superseded" findings.
        #
        # The key deliberately keeps the year. Keying on the year-less form would
        # also collapse IS 456:1978 together with IS 456:2000 -- which is exactly
        # the pair the conflict check exists to detect.
        seen_editions: set[str] = set()
        unique_items: list[str | Standard] = []
        for item in standards:
            text = item.designation if isinstance(item, Standard) else str(item)
            parsed = iscode.parse_designation(text)
            key = parsed.canonical if parsed else _yearless_key(text)
            if key and key in seen_editions:
                continue
            if key:
                seen_editions.add(key)
            unique_items.append(item)
        report.standards = [self.resolve(item) for item in unique_items]

        # -- which mandatory standards does this product need? ----------
        expected: dict[str, QCOEntry] = {}
        for resolved in report.standards:
            entry = self.qco.lookup(resolved.designation) or self.qco.lookup(resolved.input_text)
            if entry:
                expected[entry.key] = entry
        if product_description:
            matches = self.qco.match_product(product_description)
            # Drop matches that are too weak to be identification. They still
            # appear as candidates below, so nothing is hidden.
            strong = [(score, entry) for score, entry in matches if score >= MIN_PRODUCT_MATCH]
            if strong:
                top_score = strong[0][0]
                tied = [entry for score, entry in strong if score == top_score]
                if len(tied) == 1:
                    expected.setdefault(tied[0].key, tied[0])
                else:
                    # Equal top scores mean the description does not identify one
                    # product. Report as candidates and say why, instead of
                    # asserting every possibility as a requirement.
                    report.mandatory_candidates = sorted(e.designation for e in tied)
                    report.notes.append(
                        f"the product description matches {len(tied)} QCO entries equally "
                        f"well ({', '.join(report.mandatory_candidates)}); none is asserted "
                        f"as required. Disambiguate (e.g. by grade or use) or name the "
                        f"standard explicitly."
                    )
            elif matches:
                # Matched, but only on a word or two. Offered, never asserted.
                report.mandatory_candidates = sorted(
                    entry.designation for _, entry in matches[:5])
                report.notes.append(
                    f"the product description shares too few terms with any QCO entry to "
                    f"identify a requirement (needs {MIN_PRODUCT_MATCH}); the closest are "
                    f"listed as candidates. Name the standard explicitly for a definite "
                    f"check."
                )
        report.mandatory_expected = sorted(expected.values(), key=lambda e: e.designation)

        # -- present vs missing ----------------------------------------
        present_keys = {
            _yearless_key(s.designation or s.input_text) for s in report.standards
        }
        for entry in report.mandatory_expected:
            if entry.key in present_keys:
                report.mandatory_present.append(entry.designation)
            else:
                report.mandatory_missing.append(entry.designation)

        # -- sector suggestions (never counted as missing) --------------
        if report.sector:
            supplied_keys = {_yearless_key(s.designation or s.input_text)
                             for s in report.standards} | set(expected)
            report.sector_candidates = sorted(
                entry.designation for entry in self.qco.for_sector(report.sector)
                if entry.key not in supplied_keys
            )

        # -- superseded editions ---------------------------------------
        for resolved in report.standards:
            if resolved.found_in_dataset and not resolved.is_current:
                info = self.data.supersession(resolved.canonical)
                report.superseded_used.append({
                    "used": info.designation if info else resolved.designation,
                    "replace_with": info.replacement_designation if info else "a newer edition",
                    "replacement_in_dataset": bool(info and info.in_dataset),
                })

        # -- conflicts -------------------------------------------------
        report.conflicts = self._detect_conflicts(report.standards)

        # -- score, weights, grade -------------------------------------
        self._score(report)
        self._actions(report)
        return report

    # ------------------------------------------------------------------
    @staticmethod
    def _limitations() -> list[str]:
        return [
            "This compares the standards supplied against the QCO list this dataset "
            "holds; it does not determine whether your product requires certification.",
            "The dataset holds a subset of BIS's catalogue, so a standard absent from "
            "the results may simply not be indexed here.",
            "Absence of a warning is not legal advice -- confirm requirements with BIS "
            "or the relevant Quality Control Order.",
        ]

    def _detect_conflicts(self, standards: Sequence[ResolvedStandard]) -> list[dict[str, str]]:
        """Report two standards that should not both be in use.

        Two checkable cases, both data-derived rather than heuristic:

        * **two editions of one standard** -- IS 456:1978 *and* IS 456:2000;
        * **a standard alongside its own replacement** -- IS 456:1978 plus IS 456:2000
          is the same condition, but reached through the supersession chain rather
          than the key, so it catches editions whose keys differ (part/section).
        """
        conflicts: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()

        by_key: dict[str, list[ResolvedStandard]] = {}
        for resolved in standards:
            if not resolved.found_in_dataset:
                continue
            key = _yearless_key(resolved.designation)
            by_key.setdefault(key, []).append(resolved)
        for key, group in by_key.items():
            if len(group) > 1:
                editions = sorted({g.designation for g in group})
                pair = ("editions", "|".join(editions))
                if pair not in seen:
                    seen.add(pair)
                    conflicts.append({
                        "type": "multiple_editions",
                        "standards": " + ".join(editions),
                        "detail": f"{len(editions)} editions of the same standard are in "
                                  f"use together; only the current one applies.",
                    })

        present = {_yearless_key(s.designation) for s in standards if s.found_in_dataset}
        for resolved in standards:
            if not resolved.found_in_dataset or resolved.is_current:
                continue
            info = self.data.supersession(resolved.canonical)
            if info and info.replacement_canonical:
                # Same key means the first check already reported this pair.
                if _yearless_key(info.replacement_designation) == \
                        _yearless_key(resolved.designation):
                    continue
                if _yearless_key(info.replacement_designation) in present:
                    pair = ("superseded-with-replacement", resolved.designation)
                    if pair not in seen:
                        seen.add(pair)
                        conflicts.append({
                            "type": "superseded_and_replacement",
                            "standards": f"{resolved.designation} + {info.replacement_designation}",
                            "detail": f"{resolved.designation} is superseded by "
                                      f"{info.replacement_designation}, which is also in "
                                      f"this set. Drop the older edition.",
                        })
        return conflicts

    def _score(self, report: ComplianceReport) -> None:
        """Compute the score and apply the mandatory-missing grade cap."""
        total_mandatory = len(report.mandatory_expected)
        weights = {"mandatory": WEIGHT_MANDATORY, "currency": WEIGHT_CURRENCY,
                   "conflicts": WEIGHT_CONFLICTS}

        if total_mandatory:
            mandatory_ratio = len(report.mandatory_present) / total_mandatory
        else:
            # No mandatory standards identified for this product. Leaving the
            # 0.7 term at zero would score an unclassified product 0/0 -> 0.0
            # and grade it NON-COMPLIANT, which would be a claim we cannot
            # support: it means "we have no QCO row for this", not "you fail".
            mandatory_ratio = None
            weights = {"mandatory": 0.0, "currency": 0.5, "conflicts": 0.5}
            report.weights_redistributed = True
            report.notes.append(
                "No mandatory standards were identified for this product, so the "
                "mandatory-presence term carries no weight and the remaining weights "
                "are redistributed. This means the score reflects edition currency and "
                "conflicts only -- it is not a statement about QCO coverage."
            )

        resolved = [s for s in report.standards if s.found_in_dataset]
        current_ratio = (sum(1 for s in resolved if s.is_current) / len(resolved)
                         if resolved else 1.0)
        conflict_free = 0.0 if report.conflicts else 1.0

        score = conflict_free * weights["conflicts"] + current_ratio * weights["currency"]
        if mandatory_ratio is not None:
            score += mandatory_ratio * weights["mandatory"]
        report.compliance_score = max(0.0, min(1.0, score))
        report.weights = weights

        report.grade = self._grade(report)

    def _grade(self, report: ComplianceReport) -> str:
        """Grade, with the mandatory-missing cap applied.

        The cap is the one deliberate deviation from the brief's formula. A set
        that is missing a mandatory standard cannot be "fully compliant" however
        good its currency ratio is, because compliance is a conjunction: IS 269
        *and* IS 1786, not 67% of them.
        """
        grade = "NON-COMPLIANT"
        for threshold, label, needs_all_mandatory in GRADE_BANDS:
            if report.compliance_score >= threshold:
                grade = label
                break

        if report.mandatory_missing:
            # Recorded whenever a mandatory standard is missing, not only when
            # the cap actually bites. The user needs to know the ceiling
            # regardless of where the score happened to land, and an empty
            # explanation next to a missing mandatory standard reads as "no
            # problem here".
            report.grade_capped_by = (
                f"{len(report.mandatory_missing)} mandatory standard(s) missing "
                f"({', '.join(report.mandatory_missing)}); a missing mandatory "
                f"standard cannot grade above PARTIALLY COMPLIANT"
            )
            if grade in ("FULLY COMPLIANT", "MOSTLY COMPLIANT"):
                return "PARTIALLY COMPLIANT" if report.compliance_score >= 0.5 \
                    else "NON-COMPLIANT"
            return grade

        if grade == "FULLY COMPLIANT" and not self.qco.verified:
            # An unverified mandatory list cannot prove completeness.
            report.grade_capped_by = (
                "the QCO list is the built-in seed set, which may be incomplete; a "
                "fully-compliant verdict needs the scraped list "
                "(`python -m bis_pipeline mandatory`)"
            )
            return "MOSTLY COMPLIANT"
        return grade

    @staticmethod
    def _actions(report: ComplianceReport) -> None:
        """Ordered by severity: missing mandatory, then editions, then conflicts."""
        for designation in report.mandatory_missing:
            report.action_items.append(
                f"Obtain and comply with {designation} -- mandatory under a Quality "
                f"Control Order for this product category."
            )
        for item in report.superseded_used:
            when = "" if item["replacement_in_dataset"] else \
                " (the replacement is not in this dataset; get it from BIS)"
            report.action_items.append(
                f"Replace {item['used']} with {item['replace_with']}{when}."
            )
        for conflict in report.conflicts:
            report.action_items.append(
                f"Resolve conflicting use of {conflict['standards']}: {conflict['detail']}"
            )
        if report.sector_candidates:
            report.action_items.append(
                "Other QCO standards recorded for the "
                f"{report.sector} sector, which are worth checking against your product "
                "if it falls in the same category: "
                + ", ".join(report.sector_candidates) + "."
            )
        if not report.action_items:
            report.action_items.append(
                "No missing mandatory standards, superseded editions or conflicts were "
                "found in the supplied set. Confirm the mandatory list for your product "
                "independently before relying on this."
            )


# ----------------------------------------------------------------------
# HTML gap report
# ----------------------------------------------------------------------
_CSS = """
  :root { color-scheme: light; }
  body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         line-height: 1.5; color: #1a1a1a; margin: 0; padding: 2rem;
         max-width: 60rem; margin-inline: auto; }
  h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
  h2 { font-size: 1.05rem; margin-top: 2rem; border-bottom: 1px solid #ddd;
       padding-bottom: 0.25rem; }
  .meta { color: #666; font-size: 0.85rem; margin-bottom: 1.5rem; }
  .grade { font-size: 1.25rem; font-weight: 600; padding: 0.75rem 1rem;
           border-radius: 6px; display: inline-block; margin: 0.5rem 0; }
  .grade.FULLY { background: #e6f4ea; color: #12602b; }
  .grade.MOSTLY { background: #fef7e0; color: #8a5a00; }
  .grade.PARTIALLY { background: #fff4e5; color: #8a4b00; }
  .grade.NON { background: #fce8e6; color: #a50e0e; }
  table { border-collapse: collapse; width: 100%; margin-top: 0.5rem;
          font-size: 0.9rem; }
  th, td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #eee;
           vertical-align: top; }
  th { background: #f7f7f7; font-weight: 600; }
  .banner { background: #fef7e0; border-left: 4px solid #f0b400; padding: 0.75rem 1rem;
            margin: 1rem 0; font-size: 0.9rem; }
  .warn { color: #a50e0e; font-weight: 600; }
  .ok { color: #12602b; }
  code { background: #f4f4f4; padding: 0.1rem 0.3rem; border-radius: 3px; }
  ol, ul { padding-left: 1.25rem; }
  footer { margin-top: 2.5rem; border-top: 1px solid #ddd; padding-top: 0.75rem;
           color: #666; font-size: 0.8rem; }
  @media print { body { padding: 0; } .banner { break-inside: avoid; } }
"""


def _esc(value: Any) -> str:
    """Escape everything that reaches the report.

    The product description is caller-supplied free text and in a web context is
    attacker-controlled. ``html.escape`` on every interpolation is not
    optional.
    """
    return html.escape("" if value is None else str(value))


#: HTML fragments used inside f-strings. Kept as module constants because
#: Python 3.11 forbids backslashes inside f-string expressions, which rules out
#: writing escaped quotes inline.
_WARN_SUPERSEDED = '<span class="warn">superseded</span>'
_WARN_NO = '<span class="warn">no</span>'
_EM_NONE = "<em>none</em>"
_EM_NOT_FOUND = "<em>not found in dataset</em>"
_EM_SPECIFY = "<em>not specified</em>"
_EM_DETECT = "<em>not detected</em>"
_TICK = "\u2705"
_CROSS = '<span class="warn">\u274c</span>'


def render_html(report: ComplianceReport, *, title: str = "BIS Compliance Gap Report") -> str:
    """Render the gap report as a standalone, printable HTML document."""
    grade_key = next((p for p in ("FULLY", "MOSTLY", "PARTIALLY", "NON")
                      if report.grade.upper().startswith(p)), "NON")

    # -- tables, built outside the main f-string ------------------------
    if report.standards:
        standard_rows = []
        for item in report.standards:
            current = "yes" if item.is_current else _WARN_SUPERSEDED
            in_data = "yes" if item.found_in_dataset else _WARN_NO
            standard_rows.append(
                "<tr><td><code>{d}</code></td><td>{t}</td><td>{c}</td>"
                "<td>{m}</td><td>{i}</td></tr>".format(
                    d=_esc(item.designation or item.input_text),
                    t=_esc(item.title) or _EM_NOT_FOUND,
                    c=current,
                    m="yes" if item.is_mandatory else "no",
                    i=in_data,
                ))
        rows_standards = "".join(standard_rows)
    else:
        rows_standards = '<tr><td colspan="5">' + _EM_NONE + "</td></tr>"

    def checklist(items: Sequence[str], present: bool) -> str:
        if not items:
            return '<tr><td colspan="2">' + _EM_NONE + "</td></tr>"
        mark = _TICK if present else _CROSS
        return "".join(
            "<tr><td>{m}</td><td><code>{d}</code></td></tr>".format(
                m=mark, d=_esc(item)) for item in items)

    if report.superseded_used:
        rows_superseded = "".join(
            "<tr><td><code>{u}</code></td><td><code>{r}</code></td><td>{a}</td></tr>".format(
                u=_esc(item["used"]), r=_esc(item["replace_with"]),
                a="yes" if item["replacement_in_dataset"] else "no -- obtain from BIS")
            for item in report.superseded_used)
    else:
        rows_superseded = ('<tr><td colspan="3"><em>No superseded editions in use.</em>'
                           "</td></tr>")

    if report.conflicts:
        rows_conflicts = "".join(
            "<tr><td>{t}</td><td><code>{s}</code></td><td>{d}</td></tr>".format(
                t=_esc(item["type"]), s=_esc(item["standards"]), d=_esc(item["detail"]))
            for item in report.conflicts)
    else:
        rows_conflicts = ('<tr><td colspan="3"><em>No conflicts detected.</em></td></tr>')

    if report.mandatory_candidates:
        rows_candidates = "".join(
            "<tr><td><code>{d}</code></td></tr>".format(d=_esc(item))
            for item in report.mandatory_candidates)
    else:
        rows_candidates = '<tr><td><em>none</em></td></tr>'

    if report.sector_candidates:
        rows_sector = "".join(
            "<tr><td><code>{d}</code></td></tr>".format(d=_esc(item))
            for item in report.sector_candidates)
    else:
        rows_sector = '<tr><td>' + _EM_NONE + "</td></tr>"

    actions = "".join(f"<li>{_esc(a)}</li>" for a in report.action_items) \
        or "<li>Nothing to action.</li>"
    limitations = "".join(f"<li>{_esc(x)}</li>" for x in report.limitations)
    notes = "".join(f"<li>{_esc(x)}</li>" for x in report.notes)
    weights = " &middot; ".join(f"{_esc(k)} {v:.2f}" for k, v in report.weights.items())
    redistributed = (" (redistributed -- no mandatory standards identified)"
                     if report.weights_redistributed else "")

    caveats = ""
    if not report.qco_verified:
        caveats = (
            '<div class="banner"><strong>Unverified mandatory list.</strong> '
            f"The QCO set in use is <code>{_esc(report.qco_source)}</code> "
            f"({report.qco_size} entries) and is not authoritative, so this report "
            "cannot confirm that the mandatory list is complete. Run "
            "<code>python -m bis_pipeline mandatory</code> to load the published "
            "BIS list with source URLs.</div>"
        )

    cap = ""
    if report.grade_capped_by:
        cap = ('<div class="banner"><strong>Grade capped.</strong> '
               f"{_esc(report.grade_capped_by)}</div>")

    product = _esc(report.product_description) or _EM_SPECIFY
    sector = _esc(report.sector) or _EM_DETECT
    missing_marked = f'<span class="warn">{len(report.mandatory_missing)} missing</span>'
    sector_label = _esc(report.sector) or "unclassified"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>{_esc(title)}</h1>
<p class="meta">
  Product: {product} &nbsp;&middot;&nbsp;
  Sector: {sector} &nbsp;&middot;&nbsp;
  QCO list: {_esc(report.qco_basis)}
</p>

<div class="grade {grade_key}">{_esc(report.grade)} {report.grade_emoji()}
  &nbsp;<span style="font-weight:400;font-size:0.9rem">
  (score {report.compliance_score:.2f})</span></div>
{caveats}
{cap}

<h2>Executive summary</h2>
<ul>
  <li>Status: <strong>{_esc(report.status())}</strong>, grade
      <strong>{_esc(report.grade)}</strong>, score
      <strong>{report.compliance_score:.2f}</strong>.</li>
  <li>Mandatory standards identified: <strong>{report.total_mandatory}</strong>
      ({len(report.mandatory_present)} present, {missing_marked}).</li>
  <li>Superseded editions in use: <strong>{len(report.superseded_used)}</strong>.</li>
  <li>Conflicts: <strong>{len(report.conflicts)}</strong>.</li>
  <li>Score weights: {weights}{redistributed}</li>
</ul>

<h2>Mandatory standards status</h2>
<table>
  <tr><th style="width:2rem"></th><th>Standard</th></tr>
  {checklist(report.mandatory_present, True)}
  {checklist(report.mandatory_missing, False)}
</table>

<h2>Standards supplied</h2>
<table>
  <tr><th>Standard</th><th>Title</th><th>Current</th><th>Mandatory (QCO)</th>
      <th>In dataset</th></tr>
  {rows_standards}
</table>

<h2>Superseded standards warning</h2>
<table>
  <tr><th>In use</th><th>Replace with</th><th>Replacement available</th></tr>
  {rows_superseded}
</table>

<h2>Conflicts</h2>
<table>
  <tr><th>Type</th><th>Standards</th><th>Detail</th></tr>
  {rows_conflicts}
</table>

<h2>Possible matches (not asserted)</h2>
<p class="meta">QCO entries the description may refer to, but which the
  description does not identify unambiguously.</p>
<table>
  <tr><th>Standard</th></tr>
  {rows_candidates}
</table>

<h2>Sector suggestions</h2>
<p class="meta">QCO standards recorded for the
  {sector_label} sector that were not supplied. Informational: a sector list is
  not a product-specific requirement.</p>
<table>
  <tr><th>Standard</th></tr>
  {rows_sector}
</table>

<h2>Action items</h2>
<ol>{actions}</ol>

<h2>Limitations</h2>
<ul>{limitations}</ul>

<h2>Provenance</h2>
<ul>{notes}</ul>

<footer>
  Generated by <code>bis_rag.compliance</code> from the BIS standards dataset.
  QCO data source: {_esc(report.qco_source)}. This report is a screening aid, not
  legal advice.
</footer>
</body>
</html>
"""
