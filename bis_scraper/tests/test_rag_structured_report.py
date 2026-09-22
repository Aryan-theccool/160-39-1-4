"""Step 3 tests: LLM-powered structured report generation & verification.

Tests:
1. No LLM configured -> mode='extractive', structured report generated.
2. LLM configured -> mode='llm', structured report parsed with grounding.
3. Hallucinated citation -> verifier flags fake IS number, grounding=False.
4. Superseded standard -> authoritative status cannot be overridden by LLM.
5. API response integration -> recommend payload includes structured report.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from bis_rag.data import BisData
from bis_rag.hybrid import HybridSearch, RetrievalConfig, SearchResult
from bis_rag.rag import (
    ApplicableStandard,
    ExtractiveGenerator,
    ProductUnderstanding,
    RAGPipeline,
    RelatedStandard,
    ScriptedGenerator,
    StructuredReport,
    parse_structured_report,
    verify_citations,
)


@pytest.fixture(scope="module")
def data(tmp_path_factory) -> BisData:
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from synth_bis_data import make_synth_data

    root = tmp_path_factory.mktemp("structured_data")
    make_synth_data(root / "bis_data")
    return BisData(root / "bis_data")


@pytest.fixture(scope="module")
def search(data, tmp_path_factory) -> HybridSearch:
    from bis_rag.build_vector_store import BuildConfig, build

    store = tmp_path_factory.mktemp("structured_store") / "store"
    build(BuildConfig(data_dir=data.root, store_dir=store, backend="json",
                      embedder="hash", batch_size=8, verify=False))
    return HybridSearch(data, store_dir=store, embedder="hash",
                        config=RetrievalConfig(top_k=6), reranker="lexical")


@pytest.fixture
def pipeline(data, search):
    return lambda gen: RAGPipeline(data, search=search, generator=gen)


def test_1_no_llm_extractive_fallback_structured_report(pipeline):
    """Test 1: Extractive fallback produces structured report and mode='extractive'."""
    pipe = pipeline(ExtractiveGenerator())
    answer = pipe.answer("ordinary portland cement 33 grade", top_k=4)

    assert answer.mode == "extractive"
    assert "extractive" in answer.generator.lower()
    assert answer.report is not None
    assert isinstance(answer.report, dict)
    assert "summary" in answer.report
    assert "product_understanding" in answer.report
    assert "applicable_standards" in answer.report
    assert len(answer.report["applicable_standards"]) > 0
    assert "warnings" in answer.report
    assert "evidence" in answer.report
    assert answer.grounded is True
    assert "### Summary" in answer.answer
    assert "### Applicable Indian Standards" in answer.answer


def test_2_llm_configured_structured_report_with_citations(pipeline, search):
    """Test 2: LLM produces structured output and citations are verified."""
    context = search.search("ordinary portland cement 33 grade", top_k=4)
    primary = context.results[0].designation

    sample_llm_response = f"""### Summary
Ordinary Portland Cement (33 Grade) is governed by {primary}.

### Product & Specification Understanding
- Product: Ordinary Portland Cement 33 Grade
- Application: General civil engineering construction

### Applicable Indian Standards
- {primary} — Specification for 33 grade ordinary portland cement [Status: current]
  - Rationale: Defines physical and chemical requirements.

### Related / Allied Standards
- {primary} — Specification

### Compliance & Quality Notes
- Subject to mandatory BIS certification.

### Warnings & Supersessions
- None.
"""
    pipe = pipeline(ScriptedGenerator([sample_llm_response]))
    answer = pipe.answer("ordinary portland cement 33 grade", top_k=4)

    assert answer.mode == "llm"
    assert answer.report is not None
    assert answer.report["product_understanding"]["product"] != ""
    assert len(answer.report["applicable_standards"]) > 0
    assert answer.grounded is True
    assert answer.unsupported_citations == []


def test_3_hallucinated_citation_is_flagged_in_report_and_warnings(pipeline):
    """Test 3: LLM hallucinates a fake standard number -> flagged and unverified."""
    fake_response = """### Summary
Cement requirements are specified in IS 269:2015.
Street lighting luminaires must also comply with IS 99999:2025.
"""
    pipe = pipeline(ScriptedGenerator([fake_response]))
    answer = pipe.answer("ordinary portland cement", top_k=4)

    assert answer.mode == "llm"
    assert "IS 99999:2025" in answer.unsupported_citations
    assert answer.grounded is False
    assert any("IS 99999:2025" in w for w in answer.warnings)
    assert any("unverified" in w.lower() or "not present in the retrieved context" in w.lower() for w in answer.warnings)


def test_4_superseded_standard_authority_preservation():
    """Test 4: LLM cannot mark a superseded standard as current."""
    fake_json_response = json.dumps({
        "summary": "Report on old standard",
        "product_understanding": {"product": "Cement"},
        "applicable_standards": [
            {
                "designation": "IS 456:1978",
                "title": "Code of practice for plain and reinforced concrete",
                "relevance": "Direct specification",
                "reason": "Structural concrete",
                "status": "current"  # LLM mistakenly claiming it is current
            }
        ],
        "related_standards": [],
        "compliance_notes": [],
        "warnings": [],
        "evidence": []
    })

    superseded_result = SearchResult(
        id="IS_456_1978",
        text="Concrete specification",
        metadata={
            "designation": "IS 456:1978",
            "title": "Code of practice for plain and reinforced concrete",
            "is_current": False,
            "superseded_by": "IS 456:2000"
        },
        score=1.0,
    )

    _, report = parse_structured_report(
        fake_json_response,
        results=[superseded_result],
        citations=[],
        warnings=["IS 456:1978 is superseded by IS 456:2000"],
        query="concrete"
    )

    # Status MUST be superseded due to deterministic metadata override
    assert report.applicable_standards[0].status == "superseded"
    assert any("IS 456:1978 is superseded" in w for w in report.warnings)


def test_5_api_recommend_response_schema_compatibility(pipeline):
    """Test 5: answer payload serializes to RecommendResponseOut compatible dict."""
    pipe = pipeline(ExtractiveGenerator())
    answer = pipe.answer("drinking water", top_k=3)
    d = answer.as_dict()

    assert "question" in d
    assert "answer" in d
    assert "report" in d
    assert "mode" in d
    assert "generator" in d
    assert "grounded" in d
    assert "citations" in d
    assert "warnings" in d
    assert "notes" in d
    assert isinstance(d["report"], dict)
