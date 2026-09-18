"""Retrieval-augmented generation over the standards corpus. Part 2, second half.

Provider-agnostic by design
---------------------------
The plan specifies Groq. Groq is supported (``GROQ_API_KEY`` and it is used
automatically), but hard-coding one vendor means the pipeline does not run at
all for anyone without that key -- including in a review environment, where the
result is an unusable demo. So the generator is chosen from the environment:

===========================  =========================================
Selected when                Provider
===========================  =========================================
``GROQ_API_KEY`` set          Groq (``llama-3.3-70b-versatile`` default)
``OPENAI_API_KEY`` set        OpenAI, or anything via ``LLM_BASE_URL``
``OLLAMA_HOST`` set           local Ollama
nothing set                   :class:`ExtractiveGenerator` -- no LLM
===========================  =========================================

The extractive fallback is not a fake. It does not call a language model, it
does not invent prose, and every result says ``mode="extractive"`` plus a note
explaining that no LLM was configured. What it does is compose an answer out of
the retrieved passages with their citations, which is genuinely useful -- it is
the same information a user needs, minus the fluency.

Two things the generator is not allowed to do
---------------------------------------------
**Cite a standard that was not retrieved.** The naive pipeline asks the model to
cite its sources, prints whatever it writes, and looks confident while citing a
standard that does not exist. :func:`verify_citations` re-parses every IS
designation in the generated answer and checks it against what was actually
retrieved. Unsupported ones are surfaced in ``unsupported_citations`` and in the
warnings, so the failure is visible rather than plausible.

**Recommend a superseded edition.** If retrieval returns IS 456:1978 and the
dataset knows IS 456:2000 replaces it, the replacement is injected into the
prompt as a hard constraint and into the response as a warning. A standards
recommender that quietly returns a withdrawn edition is worse than one that
returns nothing.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, Sequence

from bis_pipeline import iscode

from .data import BisData
from .hybrid import HybridSearch, SearchResponse, SearchResult
from .query_processor import Intent, ProcessedQuery

log = logging.getLogger(__name__)

__all__ = [
    "Citation", "RAGAnswer", "Generator", "OpenAICompatibleGenerator",
    "ScriptedGenerator",
    "OllamaGenerator", "ExtractiveGenerator", "select_generator",
    "RAGPipeline", "verify_citations", "SYSTEM_PROMPT",
]

SYSTEM_PROMPT = """You are a technical assistant for Indian Standards (BIS / IS codes).

Rules, in priority order:
1. Answer only from the numbered context passages. If they do not contain the
   answer, say so plainly and name what is missing. Do not fill gaps from your
   own knowledge of standards -- IS numbers, years and limits are exactly the
   details that are wrong when recalled from memory.
2. Cite every factual claim with the standard's designation, e.g. (IS 1239:2004).
   Never cite a standard that is not in the context.
3. If a passage is marked SUPERSEDED, say so explicitly and name the replacement
   edition before anything else. Never recommend a superseded edition without
   that warning.
4. Quote numeric limits (temperatures, percentages, tolerances) exactly as they
   appear. Do not round, convert or restate them approximately.
5. Be concise: three short paragraphs at most. Lead with the answer, then the
   supporting detail, then the citation list.
"""


# ----------------------------------------------------------------------
# generators
# ----------------------------------------------------------------------
class Generator(Protocol):
    name: str
    is_llm: bool

    def complete(self, *, system: str, user: str, max_tokens: int = 900) -> str: ...


@dataclass
class OpenAICompatibleGenerator:
    """Groq, OpenAI, Together, vLLM, LM Studio -- anything with /chat/completions."""

    model: str
    base_url: str
    api_key: str = ""
    name: str = "openai-compatible"
    is_llm: bool = True
    timeout: float = 120.0
    temperature: float = 0.1   # low: this is a retrieval-grounded factual task

    def complete(self, *, system: str, user: str, max_tokens: int = 900) -> str:
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": self.temperature,
            "max_tokens": max_tokens,
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(f"{self.base_url.rstrip('/')}/chat/completions",
                                         data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"{self.name} returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"{self.name} request failed: {exc}") from exc
        try:
            return payload["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"unexpected response shape from {self.name}: "
                               f"{json.dumps(payload)[:300]}") from exc


@dataclass
class OllamaGenerator:
    """Local Ollama. ``/api/chat``, no key, fully offline."""

    model: str = "llama3.1"
    host: str = "http://localhost:11434"
    name: str = "ollama"
    is_llm: bool = True
    timeout: float = 300.0

    def complete(self, *, system: str, user: str, max_tokens: int = 900) -> str:
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": max_tokens},
        }).encode("utf-8")
        request = urllib.request.Request(f"{self.host.rstrip('/')}/api/chat", data=body,
                                         headers={"Content-Type": "application/json"},
                                         method="POST")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return str(payload.get("message", {}).get("content", "")).strip()


@dataclass
class ExtractiveGenerator:
    """No-LLM fallback: assembles an answer from the retrieved passages.

    Deliberately produces something a reader can verify line by line. It never
    paraphrases, so it cannot hallucinate a limit -- and it says up front that
    no model was involved, so nobody mistakes its output for generated prose.
    """

    name: str = "extractive (no LLM configured)"
    is_llm: bool = False

    def complete(self, *, system: str, user: str, max_tokens: int = 900) -> str:
        return ""


@dataclass
class ScriptedGenerator:
    """A generator that returns prepared text, for testing the citation path.

    The citation checks are the only defence between a model and a user who will
    act on what it says, and they were untested because testing them needed an
    API key. This makes them testable without one: give it the text a model
    *would* have produced, including the wrong citations, and assert on what the
    pipeline does with it.

    Not a mock. It implements the same protocol as the real generators, so the
    pipeline exercises the same code path -- `mode` becomes "llm", the answer is
    verified, unsupported citations are flagged -- and a test that passes here is
    evidence about `RAGPipeline`, not about this class.

    Deterministic by construction: it replays `responses` in order and returns
    the last one forever after. There is no randomness to seed and no network
    call to stub.
    """

    responses: list[str] = field(default_factory=list)
    name: str = "scripted (test double)"
    is_llm: bool = True
    calls: int = 0
    #: The `user` prompt of every call, so a test can assert what the model was
    #: actually shown.
    prompts: list[str] = field(default_factory=list)

    def complete(self, *, system: str, user: str, max_tokens: int = 900) -> str:
        self.prompts.append(user)
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        if not self.responses:
            return ""
        return self.responses[index]


def select_generator(spec: Optional[str] = None) -> Generator:
    """Pick a generator from ``spec`` or the environment.

    ``spec`` forms: ``groq``, ``openai``, ``ollama``, ``extractive``, or an
    explicit ``base_url|model`` pair for anything else OpenAI-compatible.
    """
    spec = (spec or os.environ.get("BIS_RAG_LLM") or "auto").strip().lower()

    groq_key = os.environ.get("GROQ_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    custom_base = os.environ.get("LLM_BASE_URL")
    ollama_host = os.environ.get("OLLAMA_HOST")

    if spec == "extractive":
        return ExtractiveGenerator()
    if spec == "groq" or (spec == "auto" and groq_key):
        return OpenAICompatibleGenerator(
            model=os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile"),
            base_url=os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1"),
            api_key=groq_key or "",
            name="groq",
        )
    if spec == "ollama" or (spec == "auto" and ollama_host and not openai_key and not groq_key):
        return OllamaGenerator(model=os.environ.get("LLM_MODEL", "llama3.1"),
                               host=ollama_host or "http://localhost:11434")
    if spec == "openai" or (spec == "auto" and openai_key):
        return OpenAICompatibleGenerator(
            model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
            base_url=custom_base or "https://api.openai.com/v1",
            api_key=openai_key or "",
            name="openai",
        )
    if "|" in spec:
        base_url, model = spec.split("|", 1)
        return OpenAICompatibleGenerator(model=model, base_url=base_url,
                                         api_key=os.environ.get("LLM_API_KEY", ""),
                                         name="custom")
    if custom_base:
        return OpenAICompatibleGenerator(model=os.environ.get("LLM_MODEL", "default"),
                                         base_url=custom_base,
                                         api_key=os.environ.get("LLM_API_KEY", ""),
                                         name="custom")
    return ExtractiveGenerator()


# ----------------------------------------------------------------------
# response shapes
# ----------------------------------------------------------------------
@dataclass
class Citation:
    designation: str
    title: str = ""
    canonical: str = ""
    is_current: bool = True
    superseded_by: str = ""
    chunk_id: str = ""
    archive_url: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "designation": self.designation,
            "title": self.title,
            "canonical": self.canonical,
            "is_current": self.is_current,
            "superseded_by": self.superseded_by,
            "chunk_id": self.chunk_id,
            "archive_url": self.archive_url,
        }

    def display(self) -> str:
        suffix = "" if self.is_current else f" [SUPERSEDED by {self.superseded_by}]"
        return f"{self.designation} -- {self.title}{suffix}"


@dataclass
class RAGAnswer:
    question: str
    answer: str
    citations: list[Citation] = field(default_factory=list)
    #: ``"llm"`` when a model generated the prose, ``"extractive"`` when not.
    mode: str = "extractive"
    generator: str = ""
    intent: str = ""
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: Designations the answer cited which were never retrieved.
    unsupported_citations: list[str] = field(default_factory=list)
    search: Optional[SearchResponse] = None
    #: Present when a compliance check ran (see `compliance_only`). Carries the
    #: QCO status, superseded-edition warnings and gap actions for the standards
    #: behind this answer.
    compliance: Optional[dict[str, Any]] = None

    @property
    def grounded(self) -> bool:
        return not self.unsupported_citations

    def as_dict(self, *, include_passages: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "question": self.question,
            "answer": self.answer,
            "mode": self.mode,
            "generator": self.generator,
            "intent": self.intent,
            "grounded": self.grounded,
            "citations": [c.as_dict() for c in self.citations],
            "unsupported_citations": self.unsupported_citations,
            "warnings": self.warnings,
            "notes": self.notes,
        }
        if self.compliance is not None:
            payload["compliance"] = self.compliance
        if include_passages and self.search is not None:
            payload["passages"] = [r.as_dict() for r in self.search.results]
        if self.search is not None:
            # The retrieval envelope, not just its results. An API client that
            # cannot see `superseded_alternatives` cannot tell a user "your
            # standard was replaced by this one", which is the entire point of
            # holding the withdrawn edition back instead of returning it.
            #
            # `timings_ms` carries per-stage latency, so a caller can answer
            # "why was this slow" -- the dense leg -- without a profiler.
            payload["retrieval"] = {
                "mode": self.search.mode,
                "timings_ms": self.search.timings,
                "query_coverage": (round(self.search.query_coverage, 4)
                                   if self.search.query_coverage >= 0 else None),
                "superseded": [r.as_dict() for r in self.search.superseded],
            }
        return payload


# ----------------------------------------------------------------------
# citation verification
# ----------------------------------------------------------------------
def verify_citations(answer: str, results: Sequence[SearchResult],
                     *, extra_known: Optional[set[str]] = None) -> list[str]:
    """Return designations cited in ``answer`` that were never retrieved.

    Matching is by *current* designation, not exact string: an answer that says
    "IS 456" is supported by a passage for "IS 456:2000", because that is the
    same standard and refusing the citation would be pedantry. An answer citing
    "IS 9103:1999" when the context held "IS 9103:1999" is supported; one citing
    "IS 9103:1985" is not, and that difference is the entire point.
    """
    cited = {d.format(): d for d in iscode.find_all(answer)}
    if not cited:
        return []

    # Three support levels, because they mean different things:
    #   exact/canonical match -> the citation is literally in the context
    #   designation-without-year match -> the model shortened a real citation
    #   same standard number, different year -> the model invented an edition
    supported_exact: set[str] = set()
    supported_without_year: set[str] = set()
    for result in results:
        supported_exact.add(result.designation.upper())
        supported_exact.add(result.canonical.upper())
        parsed = iscode.parse_designation(result.designation)
        if parsed:
            supported_without_year.add(parsed.key_without_year.upper())
            # Also let the bare number match: "IS 456" and "IS 456 (Part 1)" are
            # different standards, so only the exact prefix+number form is added.
            supported_without_year.add(
                parsed._key(include_year=False).upper())
    for key in extra_known or ():
        supported_exact.add(key.upper())

    unsupported: list[str] = []
    for text, parsed in cited.items():
        if text.upper() in supported_exact or parsed.canonical.upper() in supported_exact:
            continue
        if parsed.year is None:
            # A yearless citation of a standard we hold is fine -- the model just
            # wrote "IS 456" instead of "IS 456:2000".
            if parsed.key_without_year.upper() in supported_without_year:
                continue
            unsupported.append(text)
            continue
        # The cited edition is not in the context. If the same standard *is*
        # there in another edition, say so specifically -- "wrong year" is a far
        # more actionable complaint than "unknown standard".
        if parsed.key_without_year.upper() in supported_without_year:
            unsupported.append(f"{text} (edition not in the retrieved context)")
        else:
            unsupported.append(text)
    return unsupported


# ----------------------------------------------------------------------
# pipeline
# ----------------------------------------------------------------------
class RAGPipeline:
    """Retrieval + generation + verification."""

    def __init__(self, data: BisData, search: Optional[HybridSearch] = None,
                 generator: Optional[Generator | str] = None,
                 *, max_context_chars: int = 9000, compliance: bool = True):
        self.data = data
        # Imported lazily: `compliance` pulls in nothing heavy, but keeping it
        # optional means `rag.py` stays usable if that module is dropped.
        self._compliance_enabled = compliance
        self._checker = None
        self.search = search or HybridSearch(data)
        if generator is None or isinstance(generator, str):
            self.generator: Generator = select_generator(generator)
        else:
            self.generator = generator
        self.max_context_chars = max_context_chars

    # ------------------------------------------------------------------
    def build_context(self, results: Sequence[SearchResult]) -> tuple[str, list[Citation]]:
        """Numbered passages plus the citation list that backs them."""
        citations: list[Citation] = []
        blocks: list[str] = []
        seen: set[str] = set()
        used = 0

        for index, result in enumerate(results, start=1):
            info = self.data.supersession(result.canonical) if result.canonical else None
            replacement = info.replacement_designation if info else ""

            header = [f"[{index}] {result.designation or result.id}"]
            if result.title:
                header.append(f"    Title: {result.title}")
            if result.division:
                header.append(f"    Division: {result.division}")
            if result.year:
                header.append(f"    Year: {result.year}")
            if result.is_current:
                header.append("    Status: current")
            else:
                header.append(f"    Status: SUPERSEDED by {replacement or 'a newer edition'}"
                              " -- do not recommend without this warning")
            body = " ".join(result.text.split())[:1500]
            block = "\n".join(header) + f"\n    Passage: {body}"

            if used + len(block) > self.max_context_chars:
                break
            used += len(block)
            blocks.append(block)

            key = result.canonical or result.designation
            if key and key not in seen:
                seen.add(key)
                citations.append(Citation(
                    designation=result.designation or result.id,
                    title=result.title,
                    canonical=result.canonical,
                    is_current=result.is_current,
                    superseded_by=replacement,
                    chunk_id=str(result.metadata.get("chunk_id", "")),
                    archive_url=str(result.metadata.get("archive_url", "")),
                ))
        return "\n\n".join(blocks), citations

    # ------------------------------------------------------------------
    def build_user_prompt(self, processed: ProcessedQuery, context: str,
                          warnings: Sequence[str]) -> str:
        parts = [f"Question: {processed.raw}", "", "Context passages:", context or "(none)"]
        if warnings:
            parts += ["", "Supersession constraints (must be reflected in the answer):"]
            parts += [f"- {w}" for w in warnings]
        if processed.intent == Intent.COMPLIANCE:
            parts += ["", "This is a compliance question. State whether the standard is "
                          "compulsory under a Quality Control Order if the context says so, "
                          "and if it does not, say that the dataset does not record QCO "
                          "status for it."]
        if not context:
            parts += ["", "No passages were retrieved. Say so and do not answer from memory."]
        parts += ["", "Answer:"]
        return "\n".join(parts)

    # ------------------------------------------------------------------
    def answer(self, question: str, *, top_k: int = 6,
               include_passages: bool = False,
               mode: Optional[str] = None) -> RAGAnswer:
        # `mode` is the supersession policy: the recommend and compliance
        # endpoints pass "recommend" so a withdrawn edition is never the answer
        # to "what should I use", while `/search` keeps the browsing policy.
        response = self.search.search(question, top_k=top_k, mode=mode)
        processed = response.query
        context, citations = self.build_context(response.results)

        warnings = [w["message"] for w in response.supersession_warnings]
        notes = list(response.notes)

        if not response.results:
            return RAGAnswer(
                question=question,
                answer=("No matching standards were found in the dataset. The corpus holds "
                        "197 of archive.org's ~22,025 CC0 Indian Standards, so the standard "
                        "you need may simply not be indexed here."),
                citations=[], mode="extractive", generator=self.generator.name,
                intent=str(processed.intent), notes=notes, warnings=warnings,
                search=response,
            )

        if self.generator.is_llm:
            prompt = self.build_user_prompt(processed, context, warnings)
            try:
                text = self.generator.complete(system=SYSTEM_PROMPT, user=prompt)
                mode = "llm"
            except Exception as exc:
                log.warning("generator %s failed: %s", self.generator.name, exc)
                notes.append(f"generator {self.generator.name} failed ({exc}); "
                             f"returned an extractive answer instead")
                text = self._extractive(processed, response, citations)
                mode = "extractive"
        else:
            text = self._extractive(processed, response, citations)
            mode = "extractive"
            notes.append(
                "No LLM is configured, so this answer was assembled from the retrieved "
                "passages without generation. Set GROQ_API_KEY (or OPENAI_API_KEY, or "
                "OLLAMA_HOST) for prose answers."
            )

        unsupported = verify_citations(text, response.results) if mode == "llm" else []
        if unsupported:
            warnings.append(
                "The generated answer cites "
                + ", ".join(unsupported)
                + " -- not present in the retrieved context. Treat those citations as "
                  "unverified."
            )

        # A compliance question is exactly where a superseded-edition slip is
        # most expensive, so the check runs automatically for that intent -- and
        # only for that intent, because scoring every topic query would add
        # noise to answers nobody asked to have audited.
        compliance_payload = None
        if self._compliance_enabled and processed.intent == Intent.COMPLIANCE:
            compliance_payload = self._run_compliance(question, response, warnings, notes)

        return RAGAnswer(
            question=question,
            answer=text,
            citations=citations,
            mode=mode,
            generator=self.generator.name if mode == "llm" else "extractive",
            intent=str(processed.intent),
            notes=notes,
            warnings=warnings,
            unsupported_citations=unsupported,
            search=response,
            compliance=compliance_payload,
        )

    # ------------------------------------------------------------------
    def _run_compliance(self, question: str, response: SearchResponse,
                        warnings: list[str], notes: list[str]) -> Optional[dict[str, Any]]:
        """Score the retrieved standards against the QCO list.

        The retrieved standards stand in for "what this product is being built
        to", which is the best available signal when the user has not supplied a
        standard list explicitly. Returns ``None`` (and records why) rather than
        raising, because a missing QCO file must not take down `ask`.
        """
        try:
            from .compliance import ComplianceChecker

            if self._checker is None:
                self._checker = ComplianceChecker(self.data)
            # One entry per standard, not per passage: several chunks of the
            # same standard are the normal case in a result set.
            designations: list[str] = []
            for result in response.results:
                if result.designation and result.designation not in designations:
                    designations.append(result.designation)
            report = self._checker.analyze(
                product_description=question,
                standards=designations,
            )
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("compliance check failed: %s", exc)
            notes.append(f"compliance check unavailable ({exc})")
            return None

        if report.mandatory_missing:
            warnings.append(
                "Mandatory standards missing from the retrieved set: "
                + ", ".join(report.mandatory_missing)
                + ". See the compliance section for details."
            )
        for item in report.superseded_used:
            warnings.append(
                f"{item['used']} is superseded by {item['replace_with']}."
            )
        for conflict in report.conflicts:
            warnings.append(f"conflict: {conflict['detail']}")
        notes.append(f"compliance: {report.qco_basis}")
        # Order-preserving dedupe: retrieval-level and compliance-level warnings
        # can describe the same condition (a superseded edition appears once in
        # each), and a warning printed twice reads as two separate problems.
        deduped: list[str] = []
        for warning in warnings:
            if warning not in deduped:
                deduped.append(warning)
        warnings[:] = deduped
        return report.as_dict()

    # ------------------------------------------------------------------
    def _extractive(self, processed: ProcessedQuery, response: SearchResponse,
                    citations: Sequence[Citation]) -> str:
        """Compose an answer without a language model. Quotes, never paraphrases."""
        lines: list[str] = []
        if processed.intent == Intent.COMPLIANCE and response.results:
            flagged = [r for r in response.results if r.metadata.get("is_compulsory")]
            if flagged:
                lines.append("Compulsory certification (QCO) status: recorded as compulsory for "
                             + ", ".join(r.designation for r in flagged) + ".")
            else:
                lines.append("None of the retrieved standards is flagged as compulsory (QCO) "
                             "in this dataset.")
            lines.append("")

        top = response.results[0]
        lines.append(f"Closest match: {top.designation} -- {top.title}"
                     + (f" ({top.year})" if top.year else ""))
        summary = " ".join(top.text.split())
        if summary:
            lines.append(f'"{summary[:700]}"')
        lines.append("")

        if len(response.results) > 1:
            lines.append("Other relevant standards:")
            listed: set[str] = {top.canonical or top.designation}
            for result in response.results[1:8]:
                key = result.canonical or result.designation
                # One line per standard: several chunks of the same standard are
                # expected in the result set, and repeating it looks like a bug.
                if key in listed:
                    continue
                listed.add(key)
                state = "" if result.is_current else "  [SUPERSEDED]"
                lines.append(f"  - {result.designation} -- {result.title}{state}")
                if len(listed) >= 5:
                    break

        if citations:
            lines += ["", "Sources:"]
            for citation in citations[:8]:
                lines.append(f"  - {citation.display()}"
                             + (f"  {citation.archive_url}" if citation.archive_url else ""))
        return "\n".join(lines)
