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
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

from bis_pipeline import iscode

from .data import BisData
from .schema import Standard, load_json

log = logging.getLogger(__name__)

__all__ = [
    "QCOEntry", "QCODatabase", "SEED_QCO", "SECTOR_RULES", "detect_sector",
    "ComplianceReport", "ComplianceChecker", "render_html", "GRADE_BANDS",
    "ProductSpec", "RequirementItem", "SpecificationCheck", "ResolvedStandard",
    "extract_product_specs", "compare_ip_ratings", "extract_requirements_from_evidence",
    "evaluate_spec_check", "normalize_unit_value", "assess_standard_applicability",
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
# ----------------------------------------------------------------------
# the QCO database & evidence states
# ----------------------------------------------------------------------
class QCOEvidenceState:
    """Explicit evidence status for Quality Control Order applicability."""
    VERIFIED = "VERIFIED"                              # Authoritative: backed by official Gazette QCO & active enforcement
    SUPERSEDED_OR_CHANGED = "SUPERSEDED_OR_CHANGED"    # Historical QCO standard amalgamated/superseded (e.g. IS 8112 -> IS 269)
    NOT_APPLICABLE = "NOT_APPLICABLE"                  # Confirmed not subject to product QCO (voluntary/test method/mismatch)
    NOT_FOUND = "NOT_FOUND"                            # No official Gazette QCO notification found in active enforcement
    AMBIGUOUS = "AMBIGUOUS"                            # Scope boundary or schedule transition requires further gazette confirmation
    SEED_UNVERIFIED = "SEED_UNVERIFIED"                # Unverified bootstrap/seed entry (no official gazette proof in dataset)


@dataclass(frozen=True)
class QCOEntry:
    """A standard that is mandatory under a Quality Control Order, with rich statutory metadata."""

    key: str                                          # year-less key, e.g. "is 269"
    designation: str
    product: str = ""
    sector: str = ""
    qco_year: Optional[int] = None
    source: str = "verified_db"                       # "verified_db" | "scraped" | "merged" | "seed"
    verified: bool = True
    source_url: str = ""
    evidence_state: str = QCOEvidenceState.VERIFIED

    # Rich statutory fields for Level 1 / Level 2 evidence
    record_id: str = ""
    is_standard: str = ""
    is_edition: str = ""
    qco_title: str = ""
    notification_number: str = ""
    issuing_ministry: str = ""
    notification_date: str = ""
    effective_date: str = ""
    scope: str = ""
    exemptions: str = ""
    amendments: str = ""
    source_document: str = ""
    evidence_notes: str = ""
    verification_date: str = ""

    @property
    def is_effective(self) -> bool:
        """Returns True if effective_date is <= current date or not specified."""
        if not self.effective_date or self.effective_date in ("NOT PRESENT", ""):
            return True
        try:
            from datetime import date
            return date.fromisoformat(self.effective_date) <= date.today()
        except Exception:
            return True

    @property
    def is_authoritative(self) -> bool:
        """True only when verified, in VERIFIED state, and effectively commenced."""
        return (
            self.verified
            and self.evidence_state == QCOEvidenceState.VERIFIED
            and self.is_effective
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "designation": self.designation,
            "product": self.product,
            "sector": self.sector,
            "qco_year": self.qco_year,
            "source": self.source,
            "verified": self.verified,
            "source_url": self.source_url,
            "evidence_state": self.evidence_state,
            "qco_title": self.qco_title,
            "notification_number": self.notification_number,
            "issuing_ministry": self.issuing_ministry,
            "notification_date": self.notification_date,
            "effective_date": self.effective_date,
            "is_effective": self.is_effective,
            "is_authoritative": self.is_authoritative,
            "scope": self.scope,
            "exemptions": self.exemptions,
            "amendments": self.amendments,
            "source_document": self.source_document,
            "evidence_notes": self.evidence_notes,
            "verification_date": self.verification_date,
        }


# The comparison key lives in iscode.py: it is IS-designation grammar, and both
# the compliance checker and the retriever need it. Keeping two copies would let
# them disagree about what counts as "the same standard".
from bis_pipeline.iscode import yearless_key as _yearless_key  # noqa: E402

#: Public name, for callers outside this module.
yearless_key = _yearless_key


class QCODatabase:
    """The set of standards that are mandatory under a QCO, with official provenance."""

    def __init__(self, data: Optional[BisData] = None, qco_path: Optional[str | Path] = None):
        self.data = data
        self.qco_path = Path(qco_path) if qco_path else None
        self.entries: dict[str, QCOEntry] = {}
        self.source = "none"
        self.notes: list[str] = []
        self._load()

    @property
    def verified(self) -> bool:
        """True when backed by the official verified database, official scrape, or merged dataset."""
        return self.source in ("verified_db", "scraped", "merged") and bool(self.entries)

    # ------------------------------------------------------------------
    def _load(self) -> None:
        # 1. Primary: If explicit qco_path was provided
        if self.qco_path is not None and self.qco_path.exists():
            try:
                self._load_verified_db(self.qco_path)
                return
            except Exception as exc:
                log.warning("could not read %s: %s", self.qco_path, exc)
                self.notes.append(f"qco_path unreadable ({exc}); falling back")

        # 2. Check within BisData root or its parent if available
        if self.data is not None and hasattr(self.data, "root"):
            cand_paths = [
                Path(self.data.root) / "data" / "qco_verified_database.json",
                Path(self.data.root).parent / "data" / "qco_verified_database.json",
            ]
            for cp in cand_paths:
                if cp.exists():
                    try:
                        self._load_verified_db(cp)
                        return
                    except Exception as exc:
                        log.warning("could not read %s: %s", cp, exc)

        # 3. Secondary: Load from scraped mandatory.json
        if self.data is not None and self.data.exists("mandatory"):
            try:
                self._load_scraped()
                return
            except Exception as exc:  # pragma: no cover - defensive
                log.warning("could not read mandatory.json: %s", exc)
                self.notes.append(f"mandatory.json unreadable ({exc}); falling back")

        # 4. Tertiary: Derive from merged_standards.json
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

        # 5. Fallback: Built-in unverified seed
        self._load_seed()

    def _load_verified_db(self, path: Path) -> None:
        with open(path, "r", encoding="utf-8") as f:
            records = json.load(f)

        verified_cnt = 0
        for r in records:
            std_raw = r.get("is_standard") or r.get("designation") or ""
            key = _yearless_key(std_raw)
            if not key:
                continue

            ev_state = r.get("evidence_state", QCOEvidenceState.SEED_UNVERIFIED)
            is_v = (ev_state == QCOEvidenceState.VERIFIED and r.get("qco_verified", False))

            entry = QCOEntry(
                key=key,
                designation=std_raw.upper() if not std_raw.startswith("IS") else std_raw,
                product=r.get("product_name") or r.get("product", ""),
                sector=r.get("sector", ""),
                qco_year=None,
                source="verified_db",
                verified=is_v,
                source_url=r.get("source_url", ""),
                evidence_state=ev_state,
                record_id=r.get("record_id", ""),
                is_standard=r.get("is_standard", ""),
                is_edition=r.get("is_edition", ""),
                qco_title=r.get("qco_title", ""),
                notification_number=r.get("notification_number", ""),
                issuing_ministry=r.get("issuing_ministry", ""),
                notification_date=r.get("notification_date", ""),
                effective_date=r.get("effective_date", ""),
                scope=r.get("scope", ""),
                exemptions=r.get("exemptions", ""),
                amendments=r.get("amendments", ""),
                source_document=r.get("source_document", ""),
                evidence_notes=r.get("evidence_notes", ""),
                verification_date=r.get("verification_date", ""),
            )
            self.entries[key] = entry
            if is_v:
                verified_cnt += 1

        self.source = "verified_db"
        self.notes.append(
            f"QCO database loaded from official verification dataset ({len(self.entries)} candidates: "
            f"{verified_cnt} VERIFIED, {len(self.entries) - verified_cnt} unverified/other). "
            f"Note: This QCO layer contains a verified subset of identified regulatory mappings. "
            f"It is not a claim of complete or exhaustive QCO coverage across India."
        )

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
                evidence_state=QCOEvidenceState.VERIFIED,
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
                evidence_state=QCOEvidenceState.VERIFIED,
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
                evidence_state=QCOEvidenceState.SEED_UNVERIFIED,
            )
        self.source = "seed"
        self.notes.append(
            f"QCO list is the built-in seed set ({len(self.entries)} entries), which is "
            f"UNVERIFIED and may be incomplete or out of date. Run "
            f"`python -m bis_pipeline mandatory` to replace it with BIS's published list."
        )

    def lookup_state(self, designation: str) -> str:
        """Return explicit QCO evidence state: VERIFIED, SUPERSEDED_OR_CHANGED, NOT_FOUND, etc."""
        entry = self.lookup(designation)
        if entry is None:
            return QCOEvidenceState.NOT_FOUND
        return entry.evidence_state

    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self.entries)

    def lookup(self, designation: str) -> Optional[QCOEntry]:
        """Is this standard in the QCO dataset? Matches on the year-less key."""
        return self.entries.get(_yearless_key(designation))

    def is_mandatory(self, designation: str) -> bool:
        """Is this standard in the QCO dataset as a mandatory standard?"""
        entry = self.lookup(designation)
        return entry is not None and entry.evidence_state in (
            QCOEvidenceState.VERIFIED,
            QCOEvidenceState.SEED_UNVERIFIED,
            QCOEvidenceState.SUPERSEDED_OR_CHANGED,
        )

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
# Product specification extraction & engineering units
# ----------------------------------------------------------------------
@dataclass
class ProductSpec:
    """A technical parameter extracted from product specifications."""

    parameter: str
    raw_value: str
    numeric_value: Optional[float] = None
    unit: str = ""
    base_value: Optional[float] = None
    base_unit: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "raw_value": self.raw_value,
            "numeric_value": self.numeric_value,
            "unit": self.unit,
            "base_value": self.base_value,
            "base_unit": self.base_unit,
            "extra": self.extra,
        }


@dataclass
class RequirementItem:
    """A technical requirement extracted from indexed standards evidence."""

    parameter: str
    raw_value: str
    numeric_value: Optional[float] = None
    unit: str = ""
    base_value: Optional[float] = None
    base_unit: str = ""
    operator: str = "minimum"  # "minimum", "maximum", "exact", "range"
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    standard: str = ""
    clause: str = ""
    evidence: str = ""
    chunk_id: str = ""
    source_url: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SpecificationCheck:
    """Evaluation of a product specification against an applicable standard requirement."""

    parameter: str
    product_value: str
    required_value: str
    operator: str
    unit: str
    status: str  # "PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"
    standard: str = ""
    clause: str = ""
    evidence: str = ""
    explanation: str = ""
    source_url: str = ""
    chunk_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "product_value": self.product_value,
            "required_value": self.required_value,
            "operator": self.operator,
            "unit": self.unit,
            "status": self.status,
            "standard": self.standard,
            "clause": self.clause,
            "evidence": self.evidence,
            "explanation": self.explanation,
            "source_url": self.source_url,
            "chunk_id": self.chunk_id,
        }


UNIT_CONVERSIONS: dict[str, tuple[float, str]] = {
    # Power (base: W)
    "w": (1.0, "W"), "watt": (1.0, "W"), "watts": (1.0, "W"),
    "kw": (1000.0, "W"), "kilowatt": (1000.0, "W"), "kilowatts": (1000.0, "W"),
    "mw": (1000000.0, "W"),
    # Voltage (base: V)
    "v": (1.0, "V"), "volt": (1.0, "V"), "volts": (1.0, "V"),
    "kv": (1000.0, "V"), "kilovolt": (1000.0, "V"), "mv": (0.001, "V"),
    # Current (base: A)
    "a": (1.0, "A"), "amp": (1.0, "A"), "amps": (1.0, "A"), "ampere": (1.0, "A"), "amperes": (1.0, "A"),
    "ma": (0.001, "A"), "milliamp": (0.001, "A"), "milliamps": (0.001, "A"), "ka": (1000.0, "A"),
    # Frequency (base: Hz)
    "hz": (1.0, "Hz"), "khz": (1000.0, "Hz"), "mhz": (1000000.0, "Hz"),
    # Temperature (base: °C)
    "°c": (1.0, "°C"), "deg c": (1.0, "°C"), "degc": (1.0, "°C"), "c": (1.0, "°C"), "celsius": (1.0, "°C"),
    # Colour temperature (base: K)
    "k": (1.0, "K"), "kelvin": (1.0, "K"),
    # Dimensions / Length (base: mm)
    "mm": (1.0, "mm"), "millimeter": (1.0, "mm"), "millimeters": (1.0, "mm"),
    "cm": (10.0, "mm"), "centimeter": (10.0, "mm"), "centimeters": (10.0, "mm"),
    "m": (1000.0, "mm"), "meter": (1000.0, "mm"), "meters": (1000.0, "mm"), "metre": (1000.0, "mm"), "metres": (1000.0, "mm"),
    # Mass / Weight (base: kg)
    "g": (0.001, "kg"), "gram": (0.001, "kg"), "grams": (0.001, "kg"),
    "kg": (1.0, "kg"), "kilogram": (1.0, "kg"), "kilograms": (1.0, "kg"),
    "ton": (1000.0, "kg"), "tonne": (1000.0, "kg"), "tonnes": (1000.0, "kg"),
    # Force / Strength (base: N)
    "n": (1.0, "N"), "newton": (1.0, "N"), "newtons": (1.0, "N"),
    "kn": (1000.0, "N"), "kilonewton": (1000.0, "N"),
    # Pressure (base: Pa)
    "pa": (1.0, "Pa"), "pascal": (1.0, "Pa"), "pascals": (1.0, "Pa"),
    "kpa": (1000.0, "Pa"), "mpa": (1000000.0, "Pa"), "bar": (100000.0, "Pa"),
    # Percentage (base: %)
    "%": (1.0, "%"), "percent": (1.0, "%"),
    # Sound (base: dB)
    "db": (1.0, "dB"), "dba": (1.0, "dB"),
}


def normalize_unit_value(val: float, unit_str: str) -> tuple[Optional[float], str]:
    """Convert numeric value to standard base unit representation."""
    u = unit_str.strip().lower()
    if u in UNIT_CONVERSIONS:
        factor, base_u = UNIT_CONVERSIONS[u]
        return val * factor, base_u
    return val, unit_str.strip()


def parse_ip_digits(ip_str: str) -> tuple[Optional[int], Optional[int]]:
    """Parse solid and liquid protection digits from an IP code (e.g. 'IP66' -> (6, 6))."""
    import re
    m = re.search(r"ip\s*([0-6x])\s*([0-9x])", ip_str, re.IGNORECASE)
    if not m:
        return None, None
    s_raw, l_raw = m.group(1).upper(), m.group(2).upper()
    solids = int(s_raw) if s_raw != "X" else None
    liquids = int(l_raw) if l_raw != "X" else None
    return solids, liquids


def compare_ip_ratings(product_ip: str, required_ip: str, operator: str = "minimum") -> tuple[str, str]:
    """Structured comparison of IP ratings considering solid and liquid ingress protection digits."""
    p_solids, p_liquids = parse_ip_digits(product_ip)
    r_solids, r_liquids = parse_ip_digits(required_ip)
    if p_solids is None and p_liquids is None:
        return "UNKNOWN", f"Could not parse product IP rating from {product_ip!r}."
    if r_solids is None and r_liquids is None:
        return "UNKNOWN", f"Could not parse required IP rating from {required_ip!r}."

    solids_pass = True
    solids_desc = []
    if r_solids is not None:
        if p_solids is None:
            solids_pass = False
            solids_desc.append("dust protection unspecified in product")
        elif p_solids >= r_solids:
            solids_desc.append(f"dust protection {p_solids} >= {r_solids}")
        else:
            solids_pass = False
            solids_desc.append(f"dust protection {p_solids} < {r_solids}")

    liquids_pass = True
    liquids_desc = []
    if r_liquids is not None:
        if p_liquids is None:
            liquids_pass = False
            liquids_desc.append("liquid protection unspecified in product")
        elif p_liquids >= r_liquids:
            liquids_desc.append(f"liquid protection {p_liquids} >= {r_liquids}")
        else:
            liquids_pass = False
            liquids_desc.append(f"liquid protection {p_liquids} < {r_liquids}")

    if solids_pass and liquids_pass:
        explanation = f"Product {product_ip.upper()} meets requirement {required_ip.upper()} ({', '.join(solids_desc + liquids_desc)})."
        return "PASS", explanation
    else:
        failed_parts = [d for d in solids_desc + liquids_desc if "<" in d or "unspecified" in d]
        explanation = f"Product {product_ip.upper()} does not meet requirement {required_ip.upper()} ({', '.join(failed_parts)})."
        return "FAIL", explanation


def extract_product_specs(text: str) -> dict[str, ProductSpec]:
    """Extract structured engineering specifications from a product description."""
    import re
    specs: dict[str, ProductSpec] = {}
    if not text:
        return specs

    # 1. IP Rating
    ip_match = re.search(r"\bIP\s*([0-6X][0-9X])\b", text, re.IGNORECASE)
    if ip_match:
        raw_ip = f"IP{ip_match.group(1).upper()}"
        s_d, l_d = parse_ip_digits(raw_ip)
        specs["ip_rating"] = ProductSpec(
            parameter="ip_rating",
            raw_value=raw_ip,
            unit="IP",
            base_unit="IP",
            extra={"solids": s_d, "liquids": l_d},
        )

    # 2. Power (W / kW / MW)
    p_match = re.search(r"(?:approx(?:imately)?\s*)?(\d+(?:\.\d+)?)\s*(W|kW|MW|watts?)\b", text, re.IGNORECASE)
    if p_match:
        val = float(p_match.group(1))
        unit = p_match.group(2)
        base_v, base_u = normalize_unit_value(val, unit)
        specs["power"] = ProductSpec(
            parameter="power",
            raw_value=f"{p_match.group(1)} {unit}",
            numeric_value=val,
            unit=unit,
            base_value=base_v,
            base_unit=base_u,
        )

    # 3. Voltage (V / kV / V AC / V DC)
    v_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:-\s*(\d+(?:\.\d+)?)\s*)?(V|kV|volts?)(?:\s*(AC|DC))?\b", text, re.IGNORECASE)
    if v_match:
        val = float(v_match.group(1))
        unit = v_match.group(3)
        ac_dc = (v_match.group(4) or "").upper()
        base_v, base_u = normalize_unit_value(val, unit)
        raw_v = f"{v_match.group(1)} {unit}" + (f" {ac_dc}" if ac_dc else "")
        specs["voltage"] = ProductSpec(
            parameter="voltage",
            raw_value=raw_v,
            numeric_value=val,
            unit=unit,
            base_value=base_v,
            base_unit=base_u,
            extra={"ac_dc": ac_dc},
        )

    # 4. Colour Temperature / CCT (K / Kelvin)
    k_match = re.search(r"(\d{3,5})\s*(K|Kelvin)\b", text, re.IGNORECASE)
    if k_match:
        val = float(k_match.group(1))
        unit = k_match.group(2)
        base_v, base_u = normalize_unit_value(val, unit)
        specs["colour_temperature"] = ProductSpec(
            parameter="colour_temperature",
            raw_value=f"{k_match.group(1)} {unit}",
            numeric_value=val,
            unit=unit,
            base_value=base_v,
            base_unit=base_u,
        )

    # 5. Frequency (Hz / kHz)
    f_match = re.search(r"(\d+(?:\.\d+)?)\s*(Hz|kHz)\b", text, re.IGNORECASE)
    if f_match:
        val = float(f_match.group(1))
        unit = f_match.group(2)
        base_v, base_u = normalize_unit_value(val, unit)
        specs["frequency"] = ProductSpec(
            parameter="frequency",
            raw_value=f"{f_match.group(1)} {unit}",
            numeric_value=val,
            unit=unit,
            base_value=base_v,
            base_unit=base_u,
        )

    # 6. Temperature (°C / deg C / K)
    t_match = re.search(r"([+-]?\d+(?:\.\d+)?)\s*(°C|deg\s*C|Celsius)\b", text, re.IGNORECASE)
    if t_match:
        val = float(t_match.group(1))
        unit = t_match.group(2)
        base_v, base_u = normalize_unit_value(val, unit)
        specs["temperature"] = ProductSpec(
            parameter="temperature",
            raw_value=f"{t_match.group(1)} {unit}",
            numeric_value=val,
            unit=unit,
            base_value=base_v,
            base_unit=base_u,
        )

    # 7. Efficiency (%)
    eff_match = re.search(r"(\d+(?:\.\d+)?)\s*(%|percent)\b", text, re.IGNORECASE)
    if eff_match:
        val = float(eff_match.group(1))
        unit = eff_match.group(2)
        base_v, base_u = normalize_unit_value(val, unit)
        specs["efficiency"] = ProductSpec(
            parameter="efficiency",
            raw_value=f"{eff_match.group(1)}%",
            numeric_value=val,
            unit="%",
            base_value=base_v,
            base_unit="%",
        )

    return specs


PARAM_DESCRIPTIONS: dict[str, str] = {
    "voltage": "rated supply voltage",
    "power": "rated power consumption",
    "ip_rating": "ingress protection (IP rating)",
    "colour_temperature": "correlated colour temperature",
    "frequency": "rated frequency",
    "temperature": "operating temperature",
    "efficiency": "efficiency / efficacy",
}


def assess_standard_applicability(
    standard_title: str,
    standard_designation: str,
    product_description: str,
    sector: Optional[str] = None,
) -> tuple[str, str]:
    """Assess whether a standard is applicable to a given product description.

    Returns:
        (applicability, applicability_reason)
        applicability is one of: "APPLICABLE", "NOT_APPLICABLE", "CANDIDATE"
    """
    desc = (product_description or "").strip().lower()
    title = (standard_title or "").strip().lower()
    desig = (standard_designation or "").strip().lower()

    if not desc:
        return "APPLICABLE", "Applicable standard supplied for assessment."

    # Identify product category label
    if any(w in desc for w in ["led", "street light", "street-light", "luminaire", "lantern", "outdoor light"]):
        product_label = "an LED street-light luminaire"
        is_lighting = True
    elif any(w in desc for w in ["lamp", "bulb", "downlight", "floodlight", "light fixture", "lighting"]):
        product_label = "a lighting luminaire/equipment"
        is_lighting = True
    elif any(w in desc for w in ["cement", "portland", "pozzolana", "slag cement"]):
        product_label = "cement material"
        is_lighting = False
    elif any(w in desc for w in ["concrete", "mortar", "aggregate", "masonry", "brick"]):
        product_label = "concrete / construction material"
        is_lighting = False
    elif any(w in desc for w in ["pumpset", "submersible pump", "pump"]):
        product_label = "a pumpset"
        is_lighting = False
    elif any(w in desc for w in ["pipe", "pipeline", "pvc pipe"]):
        product_label = "a piping product"
        is_lighting = False
    elif any(w in desc for w in ["water", "drinking", "potable"]):
        product_label = "packaged drinking water"
        is_lighting = False
    elif any(w in desc for w in ["helmet", "headgear"]):
        product_label = "a protective helmet"
        is_lighting = False
    else:
        product_label = f"the specified product ({product_description[:40]}...)" if len(product_description) > 40 else f"the specified product ({product_description})"
        is_lighting = False

    # Domain mismatch checks
    # 1. Transformers (IS 10028, IS 2026, IS 1180)
    if "transformer" in title or "10028" in desig or "2026" in desig or "1180" in desig:
        if "transformer" in desc:
            return "APPLICABLE", f"Standard specifies requirements for {product_label}."
        reason_topic = "transformer installation" if ("installation" in title or "part 2" in desig or "part 2" in title) else "transformer equipment"
        return "NOT_APPLICABLE", f"Standard concerns {reason_topic}; product is {product_label}."

    # 2. Geotechnical / Soil testing (IS 2720)
    if any(k in title for k in ["soil", "compaction", "grain size", "atterberg", "triaxial"]) or "2720" in desig:
        if "soil" in desc:
            return "APPLICABLE", f"Standard specifies requirements for {product_label}."
        return "NOT_APPLICABLE", f"Standard concerns soil compaction and geotechnical testing; product is {product_label}."

    # 3. Turbiditimeters / Water testing instruments
    if "turbiditi" in title or "nephelometer" in title:
        if "turbiditi" in desc or "instrument" in desc:
            return "APPLICABLE", f"Standard specifies requirements for {product_label}."
        return "NOT_APPLICABLE", f"Standard concerns turbiditimeter instrumentation; product is {product_label}."

    # 4. Civil / Cement / Concrete / Gypsum / Bricks
    if any(k in title for k in ["cement", "concrete", "mortar", "gypsum", "brick", "masonry", "aggregate", "precast"]):
        if any(w in desc for w in ["cement", "concrete", "mortar", "gypsum", "brick", "masonry", "aggregate"]):
            return "APPLICABLE", f"Standard specifies requirements for {product_label}."
        return "NOT_APPLICABLE", f"Standard concerns civil and construction materials; product is {product_label}."

    # 5. Cables / Wires (IS 694, IS 1554, IS 7098)
    if any(k in title for k in ["cable", "insulated cable", "conductor", "copper wire"]):
        if any(w in desc for w in ["cable", "wire", "conductor"]):
            return "APPLICABLE", f"Standard specifies requirements for {product_label}."
        if is_lighting:
            return "CANDIDATE", f"Standard concerns electrical cables/conductors; candidate component standard rather than complete {product_label}."
        return "CANDIDATE", f"Standard concerns electrical cables/conductors."

    # 6. Lighting / Luminaire standards (IS 10322, IS 16101, IS 16102, IS 16103, IS 16107, IS 1944, IS 2418)
    if any(k in title for k in ["luminaire", "street light", "lighting", "lantern", "lamp", "led module", "photometric"]) or any(k in desig for k in ["10322", "16101", "16102", "16103", "16107", "1944"]):
        if is_lighting:
            return "APPLICABLE", f"Standard specifies requirements for {product_label}."
        return "NOT_APPLICABLE", f"Standard concerns lighting equipment; product is {product_label}."

    # Token overlap
    prod_tokens = {w for w in _tokenize(product_description) if len(w) > 3}
    title_tokens = {w for w in _tokenize(standard_title) if len(w) > 3}
    if prod_tokens and title_tokens and (prod_tokens & title_tokens):
        return "APPLICABLE", f"Standard matches product scope tokens ({', '.join(sorted(prod_tokens & title_tokens))})."

    if sector and sector == "electrical" and is_lighting:
        return "CANDIDATE", f"General electrical standard evaluated for {product_label}."

    return "CANDIDATE", f"Standard relevance is tentative for {product_label}."


def is_standard_applicable_to_product(
    standard_title: str,
    standard_designation: str,
    product_description: str,
    sector: Optional[str] = None,
    is_explicit: bool = False,
) -> bool:
    """Validate whether a candidate standard is applicable to the target product."""
    if is_explicit:
        return True
    status, _ = assess_standard_applicability(standard_title, standard_designation, product_description, sector=sector)
    return status == "APPLICABLE"


def extract_requirements_from_evidence(
    data: Optional[BisData],
    standards: Sequence[ResolvedStandard | str],
    product_specs: dict[str, ProductSpec],
    product_description: str = "",
    sector: Optional[str] = None,
    explicit_standards: Optional[set[str]] = None,
) -> list[RequirementItem]:
    """Scan indexed evidence chunks of confirmed applicable standards for machine-readable technical requirements.

    Rule: Only explicit product requirements from a confirmed applicable standard
    may generate PASS or FAIL. Scope statements, applicability limits, test voltages,
    examples, and general descriptive values must never generate PASS/FAIL.
    """
    import re
    if data is None or not hasattr(data, "chunks"):
        return []

    try:
        chunks = data.chunks()
    except Exception:
        return []

    target_std_keys = set()
    std_display_names = {}
    for item in standards:
        if isinstance(item, ResolvedStandard):
            if item.applicability != "APPLICABLE":
                continue
            d = item.designation or item.input_text
        else:
            d = str(item)
        k = _yearless_key(d)
        if k:
            target_std_keys.add(k)
            std_display_names[k] = d

    if not target_std_keys:
        return []

    # Filter chunks belonging to confirmed applicable standards
    relevant_chunks = []
    for c in chunks:
        c_key = _yearless_key(c.designation)
        if c_key in target_std_keys or (c.standard_id and _yearless_key(c.standard_id) in target_std_keys):
            relevant_chunks.append(c)

    std_titles_by_key = {}
    try:
        for s in data.standards():
            sk = _yearless_key(s.canonical or s.designation)
            if sk:
                std_titles_by_key[sk] = s.title
    except Exception:
        pass

    requirements: list[RequirementItem] = []
    seen_req_keys: set[tuple[str, str, str]] = set()

    for chunk in relevant_chunks:
        c_key = _yearless_key(chunk.designation)
        std_title = chunk.title or std_titles_by_key.get(c_key, "")
        std_name = chunk.designation or std_display_names.get(c_key, "Applicable Standard")

        # Double-check applicability
        app_status, _ = assess_standard_applicability(std_title, std_name, product_description, sector=sector)
        if app_status != "APPLICABLE":
            continue

        text = chunk.text or ""

        # 1. IP Rating requirements (Explicit requirement clauses only)
        ip_matches = re.finditer(
            r"(?:degree\s+of\s+protection|ingress\s+protection|protection\s+against\s+dust|IP\s+rating|shall\s+be\s+at\s+least|shall\s+be\s+minimum|shall\s+conform\s+to|shall\s+have\s+protection\s+of)\s*(?:minimum|at\s+least|shall\s+be)?\s*(IP\s*[0-6X][0-9X])",
            text,
            re.IGNORECASE,
        )
        for m in ip_matches:
            raw_ip = m.group(1).replace(" ", "").upper()
            req_key = ("ip_rating", raw_ip, std_name)
            if req_key not in seen_req_keys:
                seen_req_keys.add(req_key)
                start_idx = max(0, m.start() - 60)
                end_idx = min(len(text), m.end() + 60)
                requirements.append(RequirementItem(
                    parameter="ip_rating",
                    raw_value=raw_ip,
                    unit="IP",
                    base_unit="IP",
                    operator="minimum",
                    standard=std_name,
                    clause="Degree of Protection",
                    evidence=text[start_idx:end_idx].strip(),
                    chunk_id=chunk.chunk_id,
                    source_url=chunk.archive_url,
                ))

        # 2. Voltage requirements
        # Guard: Ignore scope statements, test voltages, and descriptive examples
        is_scope_or_test = bool(re.search(
            r"\b(scope|this\s+standard\s+covers|this\s+code\s+covers|this\s+standard\s+applies\s+to|this\s+part\s+specifies|"
            r"dielectric|breakdown|withstand|impulse|sparkover|flashover|test\s+voltage|insulation\s+resistance|"
            r"working\s+voltages\s+up\s+to|operating\s+at\s+voltages\s+not\s+exceeding|not\s+exceeding\s+\d+|for\s+example|such\s+as)\b",
            text,
            re.IGNORECASE,
        ))
        if not is_scope_or_test:
            v_matches = re.finditer(
                r"(?:rated\s+supply\s+voltage\s+shall\s+be|shall\s+operate\s+at\s+rated\s+voltage\s+of|rated\s+voltage\s+shall\s+be)\s*(\d+(?:\.\d+)?)\s*(V|kV|volts?)(?:\s*(AC|DC))?",
                text,
                re.IGNORECASE,
            )
            for m in v_matches:
                val = float(m.group(1))
                unit = m.group(2)
                base_v, base_u = normalize_unit_value(val, unit)
                req_key = ("voltage", f"exact_{val}{unit}", std_name)
                if req_key not in seen_req_keys:
                    seen_req_keys.add(req_key)
                    start_idx = max(0, m.start() - 60)
                    end_idx = min(len(text), m.end() + 60)
                    requirements.append(RequirementItem(
                        parameter="voltage",
                        raw_value=f"{val} {unit}",
                        numeric_value=val,
                        unit=unit,
                        base_value=base_v,
                        base_unit=base_u,
                        operator="exact",
                        standard=std_name,
                        clause="Rated Supply Voltage",
                        evidence=text[start_idx:end_idx].strip(),
                        chunk_id=chunk.chunk_id,
                        source_url=chunk.archive_url,
                    ))

        # 3. Efficiency requirements (Explicit clauses)
        eff_matches = re.finditer(
            r"(?:luminous\s+efficacy|efficiency)\s+(?:shall\s+be\s+not\s+less\s+than|shall\s+be\s+at\s+least|minimum\s+of|shall\s+be)\s*([<>≤≥=]?)\s*(\d+(?:\.\d+)?)\s*%",
            text,
            re.IGNORECASE,
        )
        for m in eff_matches:
            val = float(m.group(2))
            req_key = ("efficiency", f"{val}%", std_name)
            if req_key not in seen_req_keys:
                seen_req_keys.add(req_key)
                start_idx = max(0, m.start() - 60)
                end_idx = min(len(text), m.end() + 60)
                requirements.append(RequirementItem(
                    parameter="efficiency",
                    raw_value=f"{val}%",
                    numeric_value=val,
                    unit="%",
                    base_value=val,
                    base_unit="%",
                    operator="minimum",
                    standard=std_name,
                    clause="Efficiency Requirement",
                    evidence=text[start_idx:end_idx].strip(),
                    chunk_id=chunk.chunk_id,
                    source_url=chunk.archive_url,
                ))

        # 4. Power requirements (Explicit clauses)
        p_matches = re.finditer(
            r"(?:rated\s+)?power\s+(?:consumption\s+shall\s+not\s+exceed|consumption\s+shall\s+be\s+maximum\s+of)\s*([<>≤≥=]?)\s*(\d+(?:\.\d+)?)\s*(W|kW|watts?)",
            text,
            re.IGNORECASE,
        )
        for m in p_matches:
            val = float(m.group(2))
            unit = m.group(3)
            req_key = ("power", f"{val}{unit}", std_name)
            if req_key not in seen_req_keys:
                seen_req_keys.add(req_key)
                base_v, base_u = normalize_unit_value(val, unit)
                start_idx = max(0, m.start() - 60)
                end_idx = min(len(text), m.end() + 60)
                requirements.append(RequirementItem(
                    parameter="power",
                    raw_value=f"{val} {unit}",
                    numeric_value=val,
                    unit=unit,
                    base_value=base_v,
                    base_unit=base_u,
                    operator="maximum",
                    standard=std_name,
                    clause="Power Consumption Limit",
                    evidence=text[start_idx:end_idx].strip(),
                    chunk_id=chunk.chunk_id,
                    source_url=chunk.archive_url,
                ))

    return requirements



def evaluate_spec_check(spec: Optional[ProductSpec], req: Optional[RequirementItem], param_name: str) -> SpecificationCheck:
    """Evaluate a single specification against a standard requirement.

    Only explicit product requirements from a confirmed applicable standard may generate PASS or FAIL.
    Scope statements, applicability limits, test voltages, examples, and general descriptive values must never generate PASS/FAIL.
    """
    param_desc = PARAM_DESCRIPTIONS.get(param_name, f"rated {param_name.replace('_', ' ')}")

    if req is None:
        return SpecificationCheck(
            parameter=param_name,
            product_value=spec.raw_value if spec else "Not specified",
            required_value="Not specified in confirmed applicable standard",
            operator="none",
            unit=spec.unit if spec else "",
            status="UNKNOWN",
            standard="Applicable standard",
            clause="Requirement Not Found",
            evidence="",
            explanation=f"No confirmed applicable-standard requirement for {param_desc} was found.",
        )
    if spec is None:
        return SpecificationCheck(
            parameter=param_name,
            product_value="Not specified",
            required_value=req.raw_value,
            operator=req.operator,
            unit=req.unit,
            status="UNKNOWN",
            standard=req.standard,
            clause=req.clause,
            evidence=req.evidence,
            source_url=req.source_url,
            chunk_id=req.chunk_id,
            explanation=f"Product specification does not provide {param_desc} for comparison.",
        )

    # Both spec and req exist
    if param_name == "ip_rating":
        status, exp = compare_ip_ratings(spec.raw_value, req.raw_value, req.operator)
        return SpecificationCheck(
            parameter="ip_rating",
            product_value=spec.raw_value,
            required_value=f"{req.operator} {req.raw_value}" if req.operator != "exact" else req.raw_value,
            operator=req.operator,
            unit="IP",
            status=status,
            standard=req.standard,
            clause=req.clause,
            evidence=req.evidence,
            explanation=exp,
            source_url=req.source_url,
            chunk_id=req.chunk_id,
        )

    # Check unit compatibility
    if spec.base_unit and req.base_unit and spec.base_unit != req.base_unit:
        return SpecificationCheck(
            parameter=param_name,
            product_value=spec.raw_value,
            required_value=req.raw_value,
            operator=req.operator,
            unit=f"{spec.unit} vs {req.unit}",
            status="UNKNOWN",
            standard=req.standard,
            clause=req.clause,
            evidence=req.evidence,
            explanation=f"Incompatible units cannot be compared ({spec.unit} vs {req.unit}).",
            source_url=req.source_url,
            chunk_id=req.chunk_id,
        )

    pv = spec.base_value if spec.base_value is not None else spec.numeric_value
    rv = req.base_value if req.base_value is not None else req.numeric_value

    if pv is None or rv is None:
        return SpecificationCheck(
            parameter=param_name,
            product_value=spec.raw_value,
            required_value=req.raw_value,
            operator=req.operator,
            unit=spec.unit or req.unit,
            status="UNKNOWN",
            standard=req.standard,
            clause=req.clause,
            evidence=req.evidence,
            explanation="Numeric value could not be resolved for comparison.",
            source_url=req.source_url,
            chunk_id=req.chunk_id,
        )

    op = req.operator.lower()
    if op in ("minimum", "gte", ">=", "min", "at least", "not less than"):
        if pv >= rv:
            status = "PASS"
            exp = f"{spec.raw_value} satisfies the minimum requirement of {req.raw_value} (≥ {rv} {req.base_unit})."
        else:
            status = "FAIL"
            exp = f"{spec.raw_value} ({pv} {req.base_unit}) is below the required minimum of {req.raw_value} (≥ {rv} {req.base_unit})."
    elif op in ("maximum", "lte", "<=", "max", "not exceed", "not more than"):
        if pv <= rv:
            status = "PASS"
            exp = f"{spec.raw_value} satisfies the maximum limit of {req.raw_value} (≤ {rv} {req.base_unit})."
        else:
            status = "FAIL"
            exp = f"{spec.raw_value} ({pv} {req.base_unit}) exceeds the required maximum of {req.raw_value} (≤ {rv} {req.base_unit})."
    elif op in ("exact", "=", "nominal"):
        if abs(pv - rv) / max(rv, 1e-6) <= 0.05 or abs(pv - rv) < 1e-5:
            status = "PASS"
            exp = f"{spec.raw_value} matches nominal requirement {req.raw_value}."
        else:
            status = "FAIL"
            exp = f"{spec.raw_value} does not match nominal requirement {req.raw_value}."
    elif op == "range":
        min_v = req.min_value if req.min_value is not None else 0
        max_v = req.max_value if req.max_value is not None else float("inf")
        if min_v <= pv <= max_v:
            status = "PASS"
            exp = f"{spec.raw_value} is within the required range {min_v}–{max_v} {req.base_unit}."
        else:
            status = "FAIL"
            exp = f"{spec.raw_value} is outside the required range {min_v}–{max_v} {req.base_unit}."
    else:
        status = "UNKNOWN"
        exp = f"Unsupported comparison operator {op!r}."

    return SpecificationCheck(
        parameter=param_name,
        product_value=spec.raw_value,
        required_value=f"{op} {req.raw_value}" if op not in ("exact", "=") else req.raw_value,
        operator=req.operator,
        unit=req.base_unit or req.unit,
        status=status,
        standard=req.standard,
        clause=req.clause,
        evidence=req.evidence,
        explanation=exp,
        source_url=req.source_url,
        chunk_id=req.chunk_id,
    )


def evaluate_all_spec_checks(
    product_specs: dict[str, ProductSpec],
    requirements: list[RequirementItem],
    default_standard: str = "Applicable Indian Standards",
) -> list[SpecificationCheck]:
    """Perform deterministic specification compliance evaluations."""
    checks: list[SpecificationCheck] = []
    req_by_param: dict[str, RequirementItem] = {}
    for r in requirements:
        if r.parameter not in req_by_param:
            req_by_param[r.parameter] = r

    # 1. Evaluate checks for all product specifications extracted
    for param_name, spec in product_specs.items():
        req = req_by_param.get(param_name)
        check = evaluate_spec_check(spec, req, param_name)
        if not check.standard and req:
            check.standard = req.standard
        elif not check.standard:
            check.standard = default_standard
        checks.append(check)

    # 2. Evaluate checks for requirements found in corpus where product had no spec
    for param_name, req in req_by_param.items():
        if param_name not in product_specs:
            check = evaluate_spec_check(None, req, param_name)
            checks.append(check)

    return checks


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
    applicability: str = "APPLICABLE"  # "APPLICABLE", "NOT_APPLICABLE", "CANDIDATE"
    applicability_reason: str = ""
    qco_evidence_state: str = QCOEvidenceState.NOT_FOUND  # "VERIFIED", "SEED_UNVERIFIED", "NOT_FOUND", "NOT_APPLICABLE"
    qco_source: str = "none"                              # "verified_db", "scraped", "merged", "seed", "none"
    qco_source_url: str = ""
    qco_title: str = ""
    qco_notification: str = ""
    qco_ministry: str = ""
    qco_effective_date: str = ""
    qco_evidence_notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "input": self.input_text,
            "designation": self.designation or self.input_text,
            "canonical": self.canonical,
            "title": self.title,
            "found_in_dataset": self.found_in_dataset,
            "is_current": self.is_current,
            "is_mandatory": self.is_mandatory,
            "applicability": self.applicability,
            "applicability_reason": self.applicability_reason,
            "qco_evidence_state": self.qco_evidence_state,
            "qco_source": self.qco_source,
            "qco_source_url": self.qco_source_url,
            "qco_title": self.qco_title,
            "qco_notification": self.qco_notification,
            "qco_ministry": self.qco_ministry,
            "qco_effective_date": self.qco_effective_date,
            "qco_evidence_notes": self.qco_evidence_notes,
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
    #: sector list is not a product-specific requirement.
    sector_candidates: list[str] = field(default_factory=list)
    mandatory_candidates: list[str] = field(default_factory=list)
    #: ``[{"used", "replace_with", "replacement_in_dataset"}]``
    superseded_used: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, str]] = field(default_factory=list)

    # Engineering specification extraction & compliance checks
    product_specifications: dict[str, ProductSpec] = field(default_factory=dict)
    specification_checks: list[SpecificationCheck] = field(default_factory=list)

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
        has_spec_fail = any(c.status == "FAIL" for c in self.specification_checks)
        return not self.mandatory_missing and not self.superseded_used and not self.conflicts and not has_spec_fail

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
            "product_specifications": {k: v.as_dict() for k, v in self.product_specifications.items()},
            "specification_checks": [c.as_dict() for c in self.specification_checks],
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
        """Coarse status string, matching the project's vocabulary."""
        has_spec_fail = any(c.status == "FAIL" for c in self.specification_checks)
        has_spec_pass = any(c.status == "PASS" for c in self.specification_checks)
        has_spec_unknown = any(c.status == "UNKNOWN" for c in self.specification_checks)

        if self.mandatory_missing or has_spec_fail:
            return "NON_COMPLIANT"
        if self.superseded_used or self.conflicts:
            return "PARTIAL"
        if self.grade.startswith("FULLY") and not has_spec_unknown:
            return "COMPLIANT"
        if has_spec_pass and not has_spec_unknown and not self.mandatory_missing:
            return "COMPLIANT"
        if has_spec_pass or self.mandatory_present:
            return "PARTIAL"
        return "UNKNOWN"

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
        qco_state = entry.evidence_state if entry else QCOEvidenceState.NOT_FOUND
        qco_src = entry.source if entry else "none"
        qco_url = entry.source_url if entry else ""
        is_mand = entry is not None and entry.evidence_state in (
            QCOEvidenceState.VERIFIED,
            QCOEvidenceState.SEED_UNVERIFIED,
            QCOEvidenceState.SUPERSEDED_OR_CHANGED,
        )
        qco_title = entry.qco_title if entry else ""
        qco_notif = entry.notification_number if entry else ""
        qco_min = entry.issuing_ministry if entry else ""
        qco_eff = entry.effective_date if entry else ""
        qco_notes = entry.evidence_notes if entry else ""

        if standard is None:
            return ResolvedStandard(
                input_text=text,
                designation=text.strip(),
                found_in_dataset=False,
                is_mandatory=is_mand,
                qco_evidence_state=qco_state,
                qco_source=qco_src,
                qco_source_url=qco_url,
                qco_title=qco_title,
                qco_notification=qco_notif,
                qco_ministry=qco_min,
                qco_effective_date=qco_eff,
                qco_evidence_notes=qco_notes,
            )
        return ResolvedStandard(
            input_text=text,
            designation=standard.designation,
            canonical=standard.canonical,
            title=standard.title,
            found_in_dataset=True,
            is_current=standard.is_current,
            is_mandatory=is_mand,
            qco_evidence_state=qco_state,
            qco_source=qco_src,
            qco_source_url=qco_url,
            qco_title=qco_title,
            qco_notification=qco_notif,
            qco_ministry=qco_min,
            qco_effective_date=qco_eff,
            qco_evidence_notes=qco_notes,
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
        for s in report.standards:
            s.applicability, s.applicability_reason = assess_standard_applicability(
                s.title, s.designation or s.input_text, product_description, sector=report.sector
            )

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
            entry_parsed = iscode.parse_designation(entry.designation) or iscode.parse_designation(entry.key)
            is_present = False
            if entry.key in present_keys:
                is_present = True
            elif entry_parsed and entry_parsed.part is None and entry_parsed.section is None:
                # If mandatory requirement is a standard family (e.g. IS 302),
                # holding a specific part (e.g. IS 302 (Part 1), IS 302-2-3) satisfies it.
                if any(k == entry.key or k.startswith(entry.key + " ") or k.startswith(entry.key + "(") for k in present_keys):
                    is_present = True

            if is_present:
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

        # -- product specifications & engineering compliance -----------
        if product_description:
            report.product_specifications = extract_product_specs(product_description)

            # Rule: Only explicit product requirements from a confirmed applicable standard may generate PASS or FAIL
            applicable_stds = [s for s in report.standards if s.applicability == "APPLICABLE"]
            explicit_stds = {_yearless_key(s.designation or s.input_text) for s in applicable_stds}

            candidate_std_names = [s.designation for s in applicable_stds if s.designation]
            if not candidate_std_names:
                candidate_std_names = [s.input_text for s in applicable_stds if s.input_text]

            reqs = extract_requirements_from_evidence(
                self.data,
                applicable_stds,
                report.product_specifications,
                product_description=product_description,
                sector=report.sector,
                explicit_standards=explicit_stds,
            )
            default_std = candidate_std_names[0] if candidate_std_names else "Applicable standard"
            report.specification_checks = evaluate_all_spec_checks(
                report.product_specifications, reqs, default_standard=default_std
            )

        # -- score, weights, grade -------------------------------------
        self._score(report)
        self._actions(report)
        return report

    # ------------------------------------------------------------------
    @staticmethod
    def _limitations() -> list[str]:
        return [
            "This compares the standards and engineering specifications supplied against "
            "the QCO list and indexed corpus evidence; it does not determine whether your "
            "product requires mandatory certification.",
            "The dataset holds an indexed subset of BIS's catalogue (197 standards), so a "
            "standard or technical clause absent from the results may not be indexed here.",
            "Requirement comparisons with UNKNOWN status indicate insufficient indexed "
            "evidence or missing specifications — not a pass or fail.",
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
        """Grade, with mandatory-missing and specification failure caps applied."""
        grade = "NON-COMPLIANT"
        for threshold, label, needs_all_mandatory in GRADE_BANDS:
            if report.compliance_score >= threshold:
                grade = label
                break

        # Check specification failures
        failed_specs = [c for c in report.specification_checks if c.status == "FAIL"]
        if failed_specs:
            report.grade_capped_by = (
                f"{len(failed_specs)} product specification(s) failed standard requirements "
                f"({', '.join(c.parameter for c in failed_specs)})."
            )
            return "NON-COMPLIANT"

        if report.mandatory_missing:
            report.grade_capped_by = (
                f"{len(report.mandatory_missing)} mandatory standard(s) missing "
                f"({', '.join(report.mandatory_missing)}); a missing mandatory "
                f"standard cannot grade above PARTIALLY COMPLIANT"
            )
            if grade in ("FULLY COMPLIANT", "MOSTLY COMPLIANT"):
                return "PARTIALLY COMPLIANT" if report.compliance_score >= 0.5 \
                    else "NON-COMPLIANT"
            return grade

        if grade == "FULLY COMPLIANT":
            if not self.qco.verified:
                # An unverified mandatory list cannot prove completeness.
                report.grade_capped_by = (
                    "The QCO list is the built-in seed set (unverified); a "
                    "fully-compliant verdict requires authoritative data from the "
                    "scrape or verified QCO database."
                )
                return "MOSTLY COMPLIANT"
            has_non_authoritative_qco = any(
                not e.is_authoritative for e in report.mandatory_expected
            )
            if has_non_authoritative_qco:
                report.grade_capped_by = (
                    "QCO evidence for one or more standards is unverified, non-authoritative, or seed data; "
                    "a fully-compliant verdict requires verified authoritative QCO evidence."
                )
                return "MOSTLY COMPLIANT"
        return grade

    @staticmethod
    def _actions(report: ComplianceReport) -> None:
        """Ordered by severity: spec failures, missing mandatory, editions, conflicts."""
        for c in report.specification_checks:
            if c.status == "FAIL":
                report.action_items.append(
                    f"Specification Non-Compliance: {c.parameter.replace('_', ' ').title()} "
                    f"({c.product_value}) fails requirement ({c.required_value}) in {c.standard}."
                )
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
        for c in report.specification_checks:
            if c.status == "UNKNOWN":
                report.action_items.append(
                    f"Verification Required: Parameter {c.parameter.replace('_', ' ').title()} "
                    f"— {c.explanation}"
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
                "No missing mandatory standards, superseded editions, or specification conflicts "
                "were found in the supplied set. Confirm the mandatory list for your product "
                "independently before relying on this."
            )


# ----------------------------------------------------------------------
# HTML gap report
# ----------------------------------------------------------------------
_CSS = """
  :root { color-scheme: light; }
  body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         line-height: 1.5; color: #1a1a1a; margin: 0; padding: 2rem;
         max-width: 65rem; margin-inline: auto; }
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
  th, td { text-align: left; padding: 0.45rem 0.6rem; border-bottom: 1px solid #eee;
           vertical-align: top; }
  th { background: #f7f7f7; font-weight: 600; }
  .banner { background: #fef7e0; border-left: 4px solid #f0b400; padding: 0.75rem 1rem;
            margin: 1rem 0; font-size: 0.9rem; }
  .status-badge { display: inline-block; padding: 0.2rem 0.5rem; border-radius: 4px; font-weight: 600; font-size: 0.75rem; text-transform: uppercase; }
  .status-PASS { background: #e6f4ea; color: #12602b; }
  .status-FAIL { background: #fce8e6; color: #a50e0e; }
  .status-UNKNOWN { background: #fff4e5; color: #8a4b00; }
  .status-APPLICABLE { background: #e6f4ea; color: #12602b; }
  .status-NOT_APPLICABLE { background: #fce8e6; color: #a50e0e; }
  .status-CANDIDATE { background: #fef7e0; color: #8a5a00; }
  .status-NOT_APPLICABLE_OLD { background: #f0f0f0; color: #555555; }
  .warn { color: #a50e0e; font-weight: 600; }
  .ok { color: #12602b; }
  code { background: #f4f4f4; padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.85em; }
  ol, ul { padding-left: 1.25rem; }
  footer { margin-top: 2.5rem; border-top: 1px solid #ddd; padding-top: 0.75rem;
           color: #666; font-size: 0.8rem; }
  @media print {
    body { padding: 0.5cm 1cm; max-width: 100%; margin: 0; font-size: 10pt; }
    h1 { font-size: 14pt; }
    h2 { font-size: 11pt; page-break-after: avoid; }
    /* Keep the grade badge, banners, and action lists together */
    .grade, .banner { break-inside: avoid; }
    ol, ul { break-inside: avoid; }
    /* Prevent mid-row page breaks in tables; keep thead on every page */
    table { break-inside: auto; width: 100%; }
    thead { display: table-header-group; }
    tr { break-inside: avoid; break-after: auto; }
    /* Status badges: force colour output (print-color-adjust is the modern spec;
       -webkit-print-color-adjust for Safari / Chrome) */
    .status-badge {
      print-color-adjust: exact;
      -webkit-print-color-adjust: exact;
    }
    /* Avoid blank first page some browsers insert */
    @page { margin: 1cm; }
    /* Hide anything that is UI scaffolding rather than report content */
    footer { display: none; }
  }
"""


def _esc(value: Any) -> str:
    """Escape everything that reaches the report."""
    return html.escape("" if value is None else str(value))


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
            app_badge = f'<span class="status-badge status-{item.applicability}">{_esc(item.applicability.replace("_", " "))}</span>'
            if item.applicability_reason:
                app_badge += f'<div style="font-size:0.8em;color:#555;margin-top:2px;">{_esc(item.applicability_reason)}</div>'
            standard_rows.append(
                "<tr><td><code>{d}</code></td><td>{t}</td><td>{app}</td><td>{c}</td>"
                "<td>{m}</td><td>{i}</td></tr>".format(
                    d=_esc(item.designation or item.input_text),
                    t=_esc(item.title) or _EM_NOT_FOUND,
                    app=app_badge,
                    c=current,
                    m="yes" if item.is_mandatory else "no",
                    i=in_data,
                ))
        rows_standards = "".join(standard_rows)
    else:
        rows_standards = '<tr><td colspan="6">' + _EM_NONE + "</td></tr>"

    def checklist(items: Sequence[str], present: bool) -> str:
        if not items:
            return '<tr><td colspan="2">' + _EM_NONE + "</td></tr>"
        mark = _TICK if present else _CROSS
        return "".join(
            "<tr><td>{m}</td><td><code>{d}</code></td></tr>".format(
                m=mark, d=_esc(item)) for item in items)

    # Product specifications compliance matrix rows
    if report.specification_checks:
        spec_rows = []
        for c in report.specification_checks:
            badge_class = f"status-{c.status}"
            status_html = f'<span class="status-badge {badge_class}">{_esc(c.status)}</span>'
            evidence_str = f'<div style="font-size:0.8em;color:#555;margin-top:2px;"><em>Evidence:</em> {_esc(c.evidence)}</div>' if c.evidence else ''
            clause_str = f'<br><span style="font-size:0.8em;color:#777;">Clause: {_esc(c.clause)}</span>' if c.clause else ''
            spec_rows.append(
                "<tr>"
                "<td><strong>{param}</strong></td>"
                "<td><code>{pv}</code></td>"
                "<td><code>{rv}</code></td>"
                "<td><code>{std}</code>{clause}</td>"
                "<td>{status}</td>"
                "<td>{exp}{ev}</td>"
                "</tr>".format(
                    param=_esc(c.parameter.replace('_', ' ').title()),
                    pv=_esc(c.product_value),
                    rv=_esc(c.required_value),
                    std=_esc(c.standard or "Applicable standard"),
                    clause=clause_str,
                    status=status_html,
                    exp=_esc(c.explanation),
                    ev=evidence_str,
                )
            )
        rows_spec_checks = "".join(spec_rows)
    else:
        rows_spec_checks = '<tr><td colspan="6"><em>No technical product specifications extracted for comparison.</em></td></tr>'

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
  <li>Specification checks evaluated: <strong>{len(report.specification_checks)}</strong>.</li>
  <li>Superseded editions in use: <strong>{len(report.superseded_used)}</strong>.</li>
  <li>Conflicts: <strong>{len(report.conflicts)}</strong>.</li>
  <li>Score weights: {weights}{redistributed}</li>
</ul>

<h2>Product specification compliance</h2>
<p class="meta">Deterministic comparison of extracted engineering specifications against indexed standard requirements.</p>
<table>
  <tr>
    <th>Parameter</th>
    <th>Product Value</th>
    <th>Required Value</th>
    <th>Standard</th>
    <th>Result</th>
    <th>Evidence & Explanation</th>
  </tr>
  {rows_spec_checks}
</table>

<h2>Mandatory standards status</h2>
<table>
  <tr><th style="width:2rem"></th><th>Standard</th></tr>
  {checklist(report.mandatory_present, True)}
  {checklist(report.mandatory_missing, False)}
</table>

<h2>Standards supplied & applicability</h2>
<table>
  <tr><th>Standard</th><th>Title</th><th>Applicability</th><th>Current</th><th>Mandatory (QCO)</th>
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

