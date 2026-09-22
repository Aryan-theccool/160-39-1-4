"""Turn a typed question into structured retrieval instructions. Part 2, first half.

What "query processing" has to do here
--------------------------------------
A standards assistant gets questions like:

    "What is IS 1239:2004?"
    "Is cement covered under mandatory BIS certification?"
    "Which standard should I use for drinking water testing?"
    "Has IS 456:1978 been superseded?"
    "Give me the latest electrical appliance safety standard"

Each needs something different from retrieval. The first is an exact lookup and
should not go near a vector index. The second is a compliance question that the
QCO flag answers. The third is a topical search that should be filtered to
current editions. The fourth is a supersession question answered from the
cross-reference table. The fifth wants a division filter plus a recency sort.

This module classifies the question, extracts those constraints, and hands the
retriever a :class:`ProcessedQuery`. It uses the semantic indices that already
exist in ``bis_data`` rather than a hardcoded vocabulary: divisions and
committees come from ``category_hierarchy.json``, synonym expansion comes from
``domain_ontology.json`` concepts, and filter values are validated against
``search_facets.json``.

No ML model is involved. For a closed domain with ~200 standards and a known
vocabulary of divisions and IS numbers, rule-based extraction is more accurate
*and* more debuggable than a fine-tuned classifier -- and it degrades
predictably, which a small intent model does not.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from bis_pipeline import iscode
from bis_pipeline.iscode import Designation

from .data import BisData

log = logging.getLogger(__name__)

__all__ = ["Intent", "ProcessedQuery", "QueryProcessor"]


class Intent(str):
    """Intent, as a string so it serialises into API responses for free."""

    LOOKUP = "lookup"                 # "what is IS 1239?"           -> exact standard
    TOPIC_SEARCH = "topic_search"     # "cement standard"            -> passage retrieval
    COMPLIANCE = "compliance"         # "is X mandatory?"            -> QCO / certification
    SUPERSESSION = "supersession"     # "has X been superseded?"     -> edition chain
    LATEST = "latest"                 # "latest drinking water std"  -> current + recency
    EXPLAIN = "explain"               # "what does IS 456 cover?"    -> standards + passages
    LIST_BY_DOMAIN = "list_by_domain" # "standards for textiles"     -> filtered browse


# ----------------------------------------------------------------------
# patterns
# ----------------------------------------------------------------------
#: Words that mark a question as *about editions* rather than about content.
_SUPERSESSION_RE = re.compile(
    r"\b(supersed\w*|obsolet\w*|outdat\w*|withdrawn|replaced?\s+by|"
    r"latest|newest|current\s+edition|new\s+version|old\s+version|"
    r"still\s+valid|which\s+edition|revised)\b", re.I)

#: Compliance / certification / regulatory language.
_COMPLIANCE_RE = re.compile(
    r"\b(mandatory|compulsor\w*|qco|quality\s+control\s+order|bis\s+(?:mark|licen\w*|"
    r"certif\w*|registration)|certif\w*|isi\s+mark|regulat\w*|required\s+by\s+law|"
    r"legally\s+required|enforce\w*)\b", re.I)

_EXPLAIN_RE = re.compile(
    r"\b(what\s+does|explain|summari[sz]e|tell\s+me\s+about|describe|"
    r"what\s+is\s+covered|scope\s+of|overview)\b", re.I)

_LIST_RE = re.compile(
    r"\b(list|show|browse|all\s+standards|which\s+standards|standards\s+for|"
    r"related\s+standards)\b", re.I)

#: "since 2010", "after 2005", "before 1990", "between 2000 and 2010", "2010 or later"
_YEAR_TERMS = {
    "from": re.compile(r"\b(?:from|after|since|later\s+than|newer\s+than)\s+(\d{4})\b", re.I),
    "to": re.compile(r"\b(?:before|until|up\s+to|earlier\s+than|older\s+than)\s+(\d{4})\b", re.I),
    "gte": re.compile(r"\b(\d{4})\s+or\s+(?:later|newer|above)\b", re.I),
    "lte": re.compile(r"\b(\d{4})\s+or\s+(?:earlier|older|before)\b", re.I),
    "between": re.compile(r"\bbetween\s+(\d{4})\s+and\s+(\d{4})\b", re.I),
}
_BARE_YEAR_RE = re.compile(r"\b(19[2-9]\d|20[0-4]\d)\b")

#: Question words and fillers, stripped before keyword matching.
_STOPWORDS = frozenset("""
a an and are as at be been by can could do does for from get give has have how i
in into is it its me my of on or our please should show so some tell than that the
their them then there these this to use used using was we were what when where which
who why will with would you your need needs want about regarding covered
cover under per any all if whether
""".split())

#: Tokens that appear in almost every standard title and so carry no signal.
_GENERIC = frozenset("""
code codes specification specifications spec standard standards method methods
part parts section sections practice requirement requirements test testing
indian bureau general guide guidelines code of practice
""".split())


@dataclass
class ProcessedQuery:
    """Everything retrieval and generation need, and nothing they don't."""

    raw: str
    normalized: str = ""
    intent: str = Intent.TOPIC_SEARCH
    #: IS designations the user typed, e.g. ``IS 1239:2004``.
    designations: list[Designation] = field(default_factory=list)
    #: Division / committee filters resolved against the real values on disk.
    divisions: list[str] = field(default_factory=list)
    committees: list[str] = field(default_factory=list)
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    #: Whether to suppress superseded editions. False when the user is asking
    #: about history -- "has IS 456:1978 been superseded?" must be able to see
    #: the 1978 edition, so this is intent-dependent rather than always-on.
    current_only: bool = True
    #: Ontology terms added to the query text to improve recall.
    expansions: list[str] = field(default_factory=list)
    #: Content words that survive stopword and boilerplate removal.
    keywords: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def retrieval_text(self) -> str:
        """Query text for the sparse/dense retrievers, with expansions appended.

        Expansions are appended rather than replacing the original: if the
        ontology is wrong about a synonym, the original phrasing still carries
        the query, so recall can only improve.
        """
        if not self.expansions:
            return self.normalized
        return f"{self.normalized} {' '.join(self.expansions)}"

    @property
    def search_text(self) -> str:
        """Query text without expansions -- used for BM25 exact-ish matching."""
        return self.normalized

    def where(self) -> Optional[dict[str, Any]]:
        """Chroma-style metadata filter implied by the query."""
        clauses: list[dict] = []
        if self.divisions:
            clauses.append({"division": {"$in": list(self.divisions)}})
        if self.committees:
            clauses.append({"committee": {"$in": list(self.committees)}})
        if self.current_only:
            clauses.append({"is_current": True})
        if self.year_from and self.year_to and self.year_from == self.year_to:
            clauses.append({"year": self.year_from})
        else:
            if self.year_from:
                clauses.append({"year": {"$gte": self.year_from}})
            if self.year_to:
                clauses.append({"year": {"$lte": self.year_to}})
        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw,
            "intent": str(self.intent),
            "designations": [d.format() for d in self.designations],
            "divisions": self.divisions,
            "committees": self.committees,
            "year_from": self.year_from,
            "year_to": self.year_to,
            "current_only": self.current_only,
            "expansions": self.expansions,
            "keywords": self.keywords,
            "filter": self.where(),
            "notes": self.notes,
        }


class QueryProcessor:
    """Rule-based query understanding, grounded in the on-disk semantic indices."""

    def __init__(self, data: BisData, *, max_expansions: int = 6):
        self.data = data
        self.max_expansions = max_expansions
        self._division_names = self._load_division_names()
        self._committee_names = self._load_committee_names()
        self._concepts = self._load_concepts()

    # ------------------------------------------------------------------
    # vocabulary, loaded from the semantic indices (never hardcoded)
    # ------------------------------------------------------------------
    def _load_division_names(self) -> list[str]:
        names = set(self.data.divisions())
        hierarchy = self.data.category_hierarchy() or {}
        names |= set((hierarchy.get("divisions") or {}).keys())
        # Longest first so "Civil Engineering" wins over a hypothetical "Civil".
        return sorted((n for n in names if n), key=len, reverse=True)

    def _load_committee_names(self) -> list[str]:
        names = set(self.data.committees())
        hierarchy = self.data.category_hierarchy() or {}
        names |= set((hierarchy.get("committees") or {}).keys())
        return sorted((n for n in names if n), key=len, reverse=True)

    def _load_concepts(self) -> dict[str, list[str]]:
        try:
            return self.data.concepts()
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("could not load ontology concepts: %s", exc)
            return {}

    def vocabulary_size(self) -> dict[str, int]:
        return {
            "divisions": len(self._division_names),
            "committees": len(self._committee_names),
            "concepts": len(self._concepts),
        }

    # ------------------------------------------------------------------
    # main entry point
    # ------------------------------------------------------------------
    def process(self, query: str) -> ProcessedQuery:
        raw = (query or "").strip()
        normalized = self._normalize(raw)
        out = ProcessedQuery(raw=raw, normalized=normalized)

        out.designations = self._designations(raw)
        self._years(raw, out)
        self._divisions(normalized, out)
        self._committees(raw, out)
        out.intent = self._intent(raw, out)
        out.current_only = self._current_only(raw, out)
        out.keywords = self._keywords(normalized, out)
        self._expand(out)

        if out.designations:
            out.notes.append(
                "explicit designation(s): "
                + ", ".join(d.format() for d in out.designations)
                + " -- resolve these exactly first, before semantic search"
            )
        return out

    # ------------------------------------------------------------------
    # steps
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize(text: str) -> str:
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _designations(text: str) -> list[Designation]:
        """Every IS designation mentioned, deduplicated and order-preserved.

        Only :func:`~bis_pipeline.iscode.find_all`, never a hand-rolled regex:
        it already knows that ``IS 16103`` and ``IS 16103 (Part 1)`` differ, and
        that OCR noise like ``IS 1 113C7 - 1905`` is not a designation at all.
        """
        seen: set[str] = set()
        out: list[Designation] = []
        for parsed in iscode.find_all(text):
            key = parsed.canonical if parsed.year else parsed.key_without_year
            if key in seen:
                continue
            seen.add(key)
            out.append(parsed)
        return out

    @staticmethod
    def _years(text: str, out: ProcessedQuery) -> None:
        match = _YEAR_TERMS["between"].search(text)
        if match:
            out.year_from, out.year_to = int(match.group(1)), int(match.group(2))
            return
        for key, attr in (("from", "year_from"), ("gte", "year_from"),
                          ("to", "year_to"), ("lte", "year_to")):
            match = _YEAR_TERMS[key].search(text)
            if match:
                setattr(out, attr, int(match.group(1)))
        if out.year_from is None and out.year_to is None:
            # A bare 4-digit year is only a *filter* when the question is about
            # editions; "IS 456:2000" is handled as a designation instead.
            bare = _BARE_YEAR_RE.search(text)
            if bare and _SUPERSESSION_RE.search(text):
                out.year_from = int(bare.group(1))

    def _divisions(self, text: str, out: ProcessedQuery) -> None:
        lowered = text.lower()
        for name in self._division_names:
            if name.lower() in lowered and name not in out.divisions:
                out.divisions.append(name)

    def _committees(self, text: str, out: ProcessedQuery) -> None:
        lowered = text.lower()
        for name in self._committee_names:
            # Committee codes are short and collision-prone ("CED 2" appears
            # inside "CED 25"), so require a word boundary on the right.
            if re.search(rf"\b{re.escape(name.lower())}\b", lowered) and name not in out.committees:
                out.committees.append(name)

    @staticmethod
    def _intent(text: str, out: ProcessedQuery) -> str:
        has_designation = bool(out.designations)
        if _COMPLIANCE_RE.search(text):
            return Intent.COMPLIANCE
        if _SUPERSESSION_RE.search(text):
            return Intent.LATEST if re.search(r"\b(latest|newest|current)\b", text, re.I) \
                else Intent.SUPERSESSION
        if _EXPLAIN_RE.search(text) and has_designation:
            return Intent.EXPLAIN
        if has_designation and len(out.keywords) <= 4:
            return Intent.LOOKUP
        if _LIST_RE.search(text) or (out.divisions and len(out.keywords) <= 3):
            return Intent.LIST_BY_DOMAIN
        if has_designation:
            return Intent.EXPLAIN
        return Intent.TOPIC_SEARCH

    @staticmethod
    def _current_only(text: str, out: ProcessedQuery) -> bool:
        """Default to current editions, unless the question is about history.

        ``is_current=False`` records must remain reachable: a compliance checker
        that cannot retrieve the superseded edition cannot tell a user their
        product complies with a withdrawn standard -- which is the single most
        valuable thing it does.
        """
        if out.intent in (Intent.SUPERSESSION, Intent.COMPLIANCE):
            return False
        if re.search(r"\b(superseded|obsolete|outdated|withdrawn|old\s+version|history)\b",
                     text, re.I):
            return False
        return True

    def _keywords(self, text: str, out: ProcessedQuery) -> list[str]:
        words = re.findall(r"[a-z0-9][a-z0-9.\-/]*", text.lower())
        keep: list[str] = []
        for word in words:
            if word in _STOPWORDS or word in _GENERIC or len(word) < 3:
                continue
            # Drop the designation tokens themselves; they are handled exactly.
            if re.fullmatch(r"is\d+|\d{4}", word.replace(" ", "")):
                continue
            if word not in keep:
                keep.append(word)
        return keep

    def _expand(self, out: ProcessedQuery) -> None:
        """Add ontology siblings of the query's own keywords.

        Only concepts that map onto at least two standards are in the ontology,
        so this cannot pull in a one-off word. Expansions are capped so a long
        question cannot drown its own signal in synonyms.
        """
        if not self._concepts:
            return
        wanted: list[str] = []
        for keyword in out.keywords:
            if keyword in self._concepts:
                wanted.append(keyword)
        if not wanted:
            return
        # A candidate expansion must be supported by *at least two* of the
        # standards the concept points at. Without that test, one odd member
        # drags its own vocabulary into every query touching the concept: asking
        # about "drinking water quality" pulled in "unplasticized, pipes, tubes"
        # from a single PVC-pipe standard, and that standard then outranked the
        # drinking water standard the user actually asked about.
        for keyword in wanted:
            members = self._concepts.get(keyword, [])
            titles = []
            for canonical in members:
                std = self.data.standards_by_canonical().get(canonical)
                if std and std.title:
                    titles.append(set(re.findall(r"[a-z]{4,}", std.title.lower())))
            if len(titles) < 2:
                continue
            shared = set.intersection(*[t for t in titles[:6]]) if titles else set()
            for word in sorted(shared):
                if (word in _STOPWORDS or word in _GENERIC or word in out.keywords
                        or word in wanted or len(word) < 4):
                    continue
                wanted.append(word)
            if len(wanted) >= self.max_expansions:
                break
        out.expansions = wanted[:self.max_expansions]
        if out.expansions:
            out.notes.append(f"ontology expansion: +{', '.join(out.expansions)}")
