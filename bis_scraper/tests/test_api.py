"""Tests for the FastAPI service (Part 5).

Everything runs offline against the synthetic corpus. Two things are worth
knowing about the approach:

* **The PDFs are generated here**, byte by byte, including the xref table --
  a real, well-formed PDF rather than a fixture blob. That way the extraction
  path is exercised for real, and the built-in extractor can be tested on its
  own without depending on whether PyMuPDF happens to be installed.
* **The degraded-mode tests matter most.** A service that boots without its data
  and says precisely what is missing is the difference between a five-second fix
  and a mystery; a service that 500s on every endpoint is the other outcome.
"""

from __future__ import annotations

import json
import zlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bis_api.config import Settings
from bis_api.main import create_app
from bis_api.pdf_text import _extract_builtin, build_query, extract_text
from bis_rag.build_vector_store import BuildConfig, build

from synth_bis_data import make_synth_data


# ----------------------------------------------------------------------
# fixtures
# ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def data_root(tmp_path_factory) -> Path:
    return make_synth_data(tmp_path_factory.mktemp("api_data"))


@pytest.fixture(scope="module")
def store_dir(data_root, tmp_path_factory) -> Path:
    store = tmp_path_factory.mktemp("api_store") / "vector_store"
    build(BuildConfig(data_dir=data_root, store_dir=store, backend="json",
                      embedder="hash", batch_size=8, verify=False))
    return store


def make_settings(data_root, store_dir, **overrides) -> Settings:
    base = dict(data_dir=data_root, store_dir=store_dir, embedder="hash",
                reranker="lexical", warm_indexes=False)
    base.update(overrides)
    return Settings(**base)


@pytest.fixture(scope="module")
def client(data_root, store_dir):
    app = create_app(make_settings(data_root, store_dir))
    with TestClient(app) as test_client:
        yield test_client


# ----------------------------------------------------------------------
# a real PDF, built rather than shipped
# ----------------------------------------------------------------------
def _wrap(text: str, width: int = 78) -> list[str]:
    """Lay the text out as lines that fit the page.

    This is not cosmetic. PyMuPDF extracts only *visible* text, so a line that
    runs past the media box comes back silently truncated -- a fixture drawing
    one long line reported 1 of its 3 designations. Real documents wrap; so
    must the fixture, or it tests the wrong thing.
    """
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for word in paragraph.split(" "):
            candidate = f"{current} {word}".strip()
            if len(candidate) > width and current:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
    return lines


def make_pdf(text: str, *, compress: bool = False) -> bytes:
    """Build a minimal but valid PDF containing ``text``, wrapped onto lines."""
    escaped = [
        line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        for line in _wrap(text)
    ]
    body = "\n".join(f"({line}) Tj 0 -14 Td" for line in escaped)
    content = f"BT /F1 12 Tf 72 740 Td\n{body}\nET".encode("latin-1")
    if compress:
        content = zlib.compress(content)

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
         b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"),
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_at}\n%%EOF\n").encode()
    return bytes(out)


def make_blank_pdf() -> bytes:
    """A PDF whose content stream has no text operators -- i.e. a scan."""
    return make_pdf("")


# ----------------------------------------------------------------------
# health
# ----------------------------------------------------------------------
def test_health_reports_ok_with_full_data(client):
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["corpus"]["standards"] == 12
    assert body["corpus"]["chunks"] > 0
    assert body["retrieval"]["dense_enabled"] is True
    assert body["uptime_s"] >= 0


def test_health_is_reachable_without_an_api_key(data_root, store_dir):
    """A probe must never be locked out, or a monitor reports the service down."""
    app = create_app(make_settings(data_root, store_dir, api_key="secret"))
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/health").status_code == 200       # unversioned alias


def test_health_reports_the_qco_tier(client):
    body = client.get("/api/v1/health").json()
    assert body["qco"]["entries"] > 0
    assert body["qco"]["source"] in ("seed", "merged", "scraped")
    # The fixture carries is_compulsory flags, so tier 2 should win.
    assert body["qco"]["source"] == "merged"


# ----------------------------------------------------------------------
# degraded mode
# ----------------------------------------------------------------------
def test_service_boots_without_data_and_says_what_is_missing(tmp_path):
    """The highest-value test here: no data must not mean no service."""
    app = create_app(Settings(data_dir=tmp_path / "empty", warm_indexes=False))
    with TestClient(app) as client:
        body = client.get("/api/v1/health").json()
        assert body["status"] == "unavailable"
        assert body["issues"]
        assert "create_rag_dataset.py" in " ".join(body["issues"])
        assert client.get("/docs").status_code == 200     # docs still usable


def test_data_endpoints_return_503_not_500_when_unloaded(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "empty", warm_indexes=False))
    with TestClient(app) as client:
        response = client.get("/api/v1/search", params={"q": "cement"})
        assert response.status_code == 503
        body = response.json()
        assert body["error"] == "service_unavailable"
        assert "bis_data" in body["detail"]
        assert body["request_id"], "even a 503 must carry a request id"


def test_degraded_health_reports_missing_vector_store(data_root, tmp_path):
    """BM25-only is a degraded state, not a healthy one, and must be visible."""
    app = create_app(make_settings(data_root, tmp_path / "no_store"))
    with TestClient(app) as client:
        body = client.get("/api/v1/health").json()
        assert body["status"] == "degraded"
        assert body["retrieval"]["dense_enabled"] is False
        assert any("dense retrieval inactive" in i for i in body["issues"])
        # ...and the service still answers, from BM25.
        assert client.get("/api/v1/search", params={"q": "cement"}).status_code == 200


# ----------------------------------------------------------------------
# search
# ----------------------------------------------------------------------
def test_search_returns_ranked_results(client):
    body = client.get("/api/v1/search", params={"q": "drinking water quality"}).json()
    assert body["results"]
    assert "10500" in body["results"][0]["designation"]
    assert body["intent"] == "topic_search"


def test_search_reports_provenance_and_server_timing(client):
    response = client.get("/api/v1/search", params={"q": "cement"})
    body = response.json()
    assert body["results"][0]["found_by"], "each result must say where it came from"
    assert body["took_ms"] > 0
    assert float(response.headers["X-Response-Time-Ms"]) >= 0


def test_search_limit_and_filters(client):
    body = client.get("/api/v1/search", params={"q": "cement", "limit": 2}).json()
    assert len(body["results"]) <= 2

    filtered = client.get("/api/v1/search",
                          params={"q": "standard", "domain": "Textiles"}).json()
    assert all(r["division"] == "Textiles" for r in filtered["results"])


def test_search_excludes_superseded_by_default_and_can_include_them(client):
    default = client.get("/api/v1/search", params={"q": "reinforced concrete"}).json()
    assert all(r["is_current"] for r in default["results"])

    including = client.get("/api/v1/search", params={
        "q": "reinforced concrete", "include_superseded": True}).json()
    assert any(not r["is_current"] for r in including["results"])


def test_search_rejects_an_empty_query(client):
    response = client.get("/api/v1/search", params={"q": ""})
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"


# ----------------------------------------------------------------------
# recommend
# ----------------------------------------------------------------------
def test_recommend_returns_a_grounded_answer(client):
    body = client.post("/api/v1/recommend",
                       json={"query": "what is IS 1239?", "top_k": 3}).json()
    assert body["answer"]
    assert body["citations"]
    assert body["mode"] == "extractive"       # no LLM in the test environment
    assert body["grounded"] is True
    assert body["unsupported_citations"] == []
    assert body["took_ms"] > 0


def test_recommend_flags_a_superseded_citation(client):
    body = client.post("/api/v1/recommend", json={
        "query": "Has IS 456:1978 been superseded?", "top_k": 5}).json()
    assert body["intent"] == "supersession"
    assert any("superseded" in w.lower() for w in body["warnings"])


def test_recommend_includes_a_compliance_block_for_compliance_questions(client):
    body = client.post("/api/v1/recommend", json={
        "query": "Is cement covered under mandatory BIS certification?",
        "top_k": 4}).json()
    assert body["compliance"] is not None
    assert "grade" in body["compliance"]
    assert body["compliance"]["qco_source"] in ("seed", "merged", "scraped")


def test_recommend_does_not_audit_unrelated_questions(client):
    body = client.post("/api/v1/recommend",
                       json={"query": "maximum chloride limit in drinking water"}).json()
    assert body["compliance"] is None


def test_recommend_rejects_a_blank_query(client):
    response = client.post("/api/v1/recommend", json={"query": "   "})
    assert response.status_code == 422


def test_recommend_rejects_top_k_out_of_range(client):
    assert client.post("/api/v1/recommend",
                       json={"query": "cement", "top_k": 999}).status_code == 422


# ----------------------------------------------------------------------
# recommend/pdf
# ----------------------------------------------------------------------
def test_pdf_upload_extracts_text_and_answers(client):
    pdf = make_pdf("This specification requires compliance with IS 1239 for steel tubes "
                   "and IS 4985 for potable water pipes.")
    response = client.post("/api/v1/recommend/pdf",
                           files={"file": ("spec.pdf", pdf, "application/pdf")})
    assert response.status_code == 200
    body = response.json()
    assert body["source_document"]["ok"] is True
    assert body["source_document"]["extractor"] in ("pymupdf", "builtin")
    detected = body["detected_designations"]
    assert any("1239" in d for d in detected)
    assert any("4985" in d for d in detected)
    assert body["answer"]


def test_pdf_upload_accepts_a_compressed_content_stream(client):
    """Most real PDFs use FlateDecode; the built-in extractor must inflate."""
    pdf = make_pdf("This product shall conform to IS 1786 for reinforcement bars.", compress=True)
    body = client.post("/api/v1/recommend/pdf",
                       files={"file": ("c.pdf", pdf, "application/pdf")}).json()
    assert body["source_document"]["ok"] is True
    assert any("1786" in d for d in body["detected_designations"])


def test_pdf_without_a_text_layer_is_rejected_with_a_reason(client):
    """A scanned PDF must not become an empty query that returns everything."""
    response = client.post("/api/v1/recommend/pdf",
                           files={"file": ("scan.pdf", make_blank_pdf(), "application/pdf")})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "scan" in detail.lower() or "no text layer" in detail.lower()


def test_non_pdf_upload_is_rejected(client):
    response = client.post("/api/v1/recommend/pdf",
                           files={"file": ("notes.txt", b"just some text", "text/plain")})
    assert response.status_code == 422
    assert "not a PDF" in response.json()["detail"]


def test_oversized_pdf_is_rejected_with_413(data_root, store_dir):
    """A 10 MB default is not worth streaming through a test; shrink the limit."""
    payload = make_pdf("Steel tubes shall comply with IS 1239.")
    app = create_app(make_settings(data_root, store_dir, max_pdf_bytes=200))
    with TestClient(app) as client:
        response = client.post("/api/v1/recommend/pdf",
                               files={"file": ("big.pdf", payload, "application/pdf")})
        assert response.status_code == 413
        body = response.json()
        assert body["error"] == "payload_too_large"
        # The message must state the real sizes: a "0 MB" limit tells nobody
        # anything, and this test's limit is deliberately tiny.
        assert f"{len(payload)} bytes" in body["detail"]
        assert "200 bytes" in body["detail"]
        assert "BIS_MAX_PDF_BYTES" in body["detail"]     # and how to change it


@pytest.mark.parametrize("num_bytes,expected", [
    (0, "0 bytes"), (200, "200 bytes"), (1023, "1023 bytes"),
    (1024, "1.0 kB"), (150 * 1024, "150.0 kB"),
    (1024 * 1024, "1.0 MB"), (10 * 1024 * 1024, "10.0 MB"),
])
def test_human_size_reads_sensibly_at_every_scale(num_bytes, expected):
    from bis_api.routers.recommend import human_size
    assert human_size(num_bytes) == expected


def test_pdf_at_the_size_limit_still_works(data_root, store_dir):
    """Off-by-one insurance: the boundary must accept, not reject."""
    payload = make_pdf("Steel tubes shall comply with IS 1239.")
    app = create_app(make_settings(data_root, store_dir, max_pdf_bytes=len(payload)))
    with TestClient(app) as client:
        assert client.post(
            "/api/v1/recommend/pdf",
            files={"file": ("ok.pdf", payload, "application/pdf")}).status_code == 200


# ----------------------------------------------------------------------
# pdf extraction units
# ----------------------------------------------------------------------
def test_builtin_extractor_reads_a_plain_stream():
    result = _extract_builtin(make_pdf("Steel tubes shall comply with IS 1239."),
                              max_chars=1000)
    assert result.ok
    assert "IS 1239" in result.text
    assert result.extractor == "builtin"


def test_builtin_extractor_reads_a_flate_decoded_stream():
    result = _extract_builtin(make_pdf("Deformed bars per IS 1786.", compress=True),
                              max_chars=1000)
    assert result.ok
    assert "1786" in result.text


def test_builtin_extractor_is_not_fooled_by_et_inside_a_word():
    """Regression: `BT.*?ET` used to stop at the ET in "SHEET"/"CONCRETE".

    That truncated extraction at the first such word, so a real Indian Standard
    ("PLAIN AND REINFORCED CONCRETE") lost everything after its title.
    """
    result = _extract_builtin(
        make_pdf("PRODUCT SPECIFICATION SHEET\nPlastic pipes shall comply with IS 4985."),
        max_chars=2000)
    assert result.ok
    assert "IS 4985" in result.text
    assert "PRODUCT SPECIFICATION SHEET" in result.text


def test_builtin_extractor_keeps_every_line_of_a_multi_line_document():
    result = _extract_builtin(
        make_pdf("Steel tubes per IS 1239.\nPipes per IS 4985.\nWater per IS 10500."),
        max_chars=2000)
    assert result.ok
    for designation in ("IS 1239", "IS 4985", "IS 10500"):
        assert designation in result.text


def test_builtin_extractor_recovers_text_from_an_odd_stream():
    """An unparseable BT/ET layout must not be reported as "no text layer"."""
    pdf = make_pdf("Odd stream containing IS 1786 with no well formed text object.")
    mangled = pdf.replace(b"BT", b"bT").replace(b"\nET", b"\net")
    result = _extract_builtin(mangled, max_chars=2000)
    assert result.ok
    assert "1786" in result.text


def test_builtin_extractor_reports_failure_on_a_scan():
    result = _extract_builtin(make_blank_pdf(), max_chars=1000)
    assert result.ok is False
    assert "PyMuPDF" in result.reason      # tells the operator how to do better


def test_extract_text_rejects_non_pdf_bytes():
    result = extract_text(b"not a pdf at all")
    assert result.ok is False
    assert "not a PDF" in result.reason


def test_extract_text_rejects_empty_input():
    assert extract_text(b"").ok is False


def test_build_query_truncates_long_documents():
    """A whole spec sheet as a query buries its own signal."""
    long_text = " ".join(["clause"] * 5000)
    assert len(build_query(long_text, max_chars=500)) == 500
    assert build_query("short text", max_chars=500) == "short text"


# ----------------------------------------------------------------------
# compliance
# ----------------------------------------------------------------------
def test_compliance_check_returns_a_verdict(client):
    body = client.post("/api/v1/compliance/check", json={
        "product_description": "33 grade ordinary Portland cement",
        "standards": ["IS 269:1989"]}).json()
    assert body["grade"] in ("FULLY COMPLIANT", "MOSTLY COMPLIANT",
                             "PARTIALLY COMPLIANT", "NON-COMPLIANT")
    assert 0.0 <= body["compliance_score"] <= 1.0
    assert body["superseded_used"]
    assert body["superseded_used"][0]["replace_with"] == "IS 269:2015"
    assert body["limitations"]


def test_compliance_check_reports_missing_mandatory(client):
    body = client.post("/api/v1/compliance/check", json={
        "product_description": "33 grade ordinary Portland cement",
        "standards": ["IS 1786:2008"]}).json()
    assert body["mandatory_missing"]
    assert body["compliance_status"] == "NON_COMPLIANT"
    assert body["grade_capped_by"]


def test_compliance_report_is_printable_html(client):
    response = client.get("/api/v1/compliance/report",
                          params={"product": "cement", "standard": ["IS 269:1989"]})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    page = response.text
    assert page.startswith("<!DOCTYPE html>")
    assert "Executive summary" in page


# ----------------------------------------------------------------------
# standards
# ----------------------------------------------------------------------
def test_list_standards_with_facets(client):
    body = client.get("/api/v1/standards").json()
    assert body["total"] > 0
    assert body["facets"]["divisions"]
    assert body["returned"] <= body["limit"]


def test_list_standards_filters(client):
    textiles = client.get("/api/v1/standards", params={"division": "Textiles"}).json()
    assert textiles["total"] >= 1
    assert all(s["division"] == "Textiles" for s in textiles["standards"])

    compulsory = client.get("/api/v1/standards", params={"compulsory_only": True}).json()
    assert all(s["is_compulsory"] for s in compulsory["standards"])


def test_standard_detail_includes_supersession(client):
    body = client.get("/api/v1/standards/IS 456:1978").json()
    assert body["designation"] == "IS 456:1978"
    assert body["is_current"] is False
    assert body["superseded_by"] == "IS 456:2000"
    assert body["supersession"]["replacement_canonical"] == "IS|456|None|None|2000"
    assert body["related"]


def test_standard_detail_accepts_a_yearless_designation(client):
    body = client.get("/api/v1/standards/IS 456").json()
    assert "456" in body["designation"]


def test_unknown_standard_returns_404_with_context(client):
    response = client.get("/api/v1/standards/IS 99999")
    assert response.status_code == 404
    assert "22,025" in response.json()["detail"]      # explains the corpus limit


# ----------------------------------------------------------------------
# feedback
# ----------------------------------------------------------------------
def test_feedback_is_appended_to_jsonl(data_root, store_dir, tmp_path):
    feedback_file = tmp_path / "nested" / "feedback.jsonl"
    app = create_app(make_settings(data_root, store_dir, feedback_path=feedback_file))
    with TestClient(app) as client:
        response = client.post("/api/v1/feedback", json={
            "query": "5 HP pump", "helpful": False,
            "correct_is": "IS 14220", "request_id": "abc123"})
        assert response.status_code == 200
        assert response.json()["saved"] is True

        response = client.post("/api/v1/feedback", json={
            "query": "drinking water", "helpful": True})
        assert response.json()["saved"] is True

    lines = feedback_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["helpful"] is False
    assert first["correct_is"] == "IS 14220"
    assert first["request_id"] == "abc123"
    assert first["timestamp"].endswith("Z")


def test_feedback_reports_failure_instead_of_raising(tmp_path, data_root, store_dir):
    """A read-only volume must not turn a thank-you into a 500."""
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    blocked.chmod(0o500)                     # no write permission
    app = create_app(make_settings(data_root, store_dir,
                                   feedback_path=blocked / "sub" / "feedback.jsonl"))
    try:
        with TestClient(app) as client:
            body = client.post("/api/v1/feedback",
                               json={"query": "x", "helpful": True}).json()
            assert body["saved"] is False
            assert "could not persist" in body["message"]
    finally:
        blocked.chmod(0o700)


# ----------------------------------------------------------------------
# middleware
# ----------------------------------------------------------------------
def test_every_response_carries_a_request_id_and_timing(client):
    response = client.get("/api/v1/health")
    assert response.headers["X-Request-ID"]
    assert float(response.headers["X-Response-Time-Ms"]) >= 0


def test_client_supplied_request_id_is_honoured_when_safe(client):
    response = client.get("/api/v1/health", headers={"X-Request-ID": "trace-42"})
    assert response.headers["X-Request-ID"] == "trace-42"


def test_unsafe_request_id_is_replaced_not_echoed(client):
    """An arbitrary client string echoed into logs is log injection."""
    hostile = "bad id\nwith newline and spaces"
    response = client.get("/api/v1/health", headers={"X-Request-ID": hostile})
    assert response.headers["X-Request-ID"] != hostile
    assert "\n" not in response.headers["X-Request-ID"]


def test_rate_limit_returns_429_with_retry_after(data_root, store_dir):
    app = create_app(make_settings(data_root, store_dir,
                                   rate_limit_requests=3, rate_limit_window_s=60))
    with TestClient(app) as client:
        for _ in range(3):
            assert client.get("/api/v1/search", params={"q": "cement"}).status_code == 200
        response = client.get("/api/v1/search", params={"q": "cement"})
        assert response.status_code == 429
        assert response.json()["error"] == "rate_limit_exceeded"
        assert int(response.headers["Retry-After"]) >= 1
        assert response.headers["X-RateLimit-Remaining"] == "0"
        # The context middleware is outside the limiter, so even a 429 is traceable.
        assert response.headers["X-Request-ID"]


def test_rate_limiter_is_per_client():
    from bis_api.middleware.rate_limit import RateLimiter

    limiter = RateLimiter(limit=2, window_s=60)
    assert limiter.check("a")[0] is True
    assert limiter.check("a")[0] is True
    allowed, remaining, retry = limiter.check("a")
    assert allowed is False and remaining == 0 and retry > 0
    assert limiter.check("b")[0] is True      # a different client is unaffected


def test_rate_limit_does_not_consume_health_checks(data_root, store_dir):
    app = create_app(make_settings(data_root, store_dir, rate_limit_requests=2))
    with TestClient(app) as client:
        for _ in range(10):
            assert client.get("/api/v1/health").status_code == 200


def test_cors_headers_are_present_for_the_frontend(client):
    response = client.get("/api/v1/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers.get("access-control-allow-origin") == "*"
    exposed = response.headers.get("access-control-expose-headers", "")
    assert "X-Request-ID" in exposed


def test_cors_origins_are_configurable(data_root, store_dir):
    app = create_app(make_settings(data_root, store_dir,
                                   cors_origins=("https://example.com",)))
    with TestClient(app) as client:
        allowed = client.get("/api/v1/health", headers={"Origin": "https://example.com"})
        assert allowed.headers.get("access-control-allow-origin") == "https://example.com"
        denied = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
        assert denied.headers.get("access-control-allow-origin") is None


def test_preflight_request_succeeds(client):
    response = client.options("/api/v1/search", headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET",
    })
    assert response.status_code in (200, 204)
    assert response.headers.get("access-control-allow-origin") == "*"


# ----------------------------------------------------------------------
# auth
# ----------------------------------------------------------------------
def test_api_key_is_optional_by_default(client):
    assert client.get("/api/v1/standards").status_code == 200


def test_api_key_is_enforced_when_configured(data_root, store_dir):
    app = create_app(make_settings(data_root, store_dir, api_key="s3cret"))
    with TestClient(app) as client:
        assert client.get("/api/v1/standards").status_code == 401
        assert client.get("/api/v1/standards",
                          headers={"X-API-Key": "wrong"}).status_code == 401
        assert client.get("/api/v1/standards",
                          headers={"X-API-Key": "s3cret"}).status_code == 200
        assert client.get("/api/v1/health").status_code == 200   # never locked


# ----------------------------------------------------------------------
# error shape
# ----------------------------------------------------------------------
def test_error_responses_share_one_shape(client):
    for response in (
        client.get("/api/v1/standards/IS 99999"),                 # 404
        client.get("/api/v1/search", params={"q": ""}),           # 422
        client.get("/api/v1/does-not-exist"),                      # 404
    ):
        body = response.json()
        assert set(body) >= {"error", "detail", "request_id", "status_code"}
        assert body["status_code"] == response.status_code


def test_method_not_allowed_is_a_clean_json_error(client):
    response = client.put("/api/v1/recommend", json={})
    assert response.status_code == 405
    assert response.json()["error"] == "method_not_allowed"


def test_unhandled_exception_is_a_clean_json_error_without_a_traceback(data_root, store_dir):
    """A traceback in a response body is an information leak."""
    from bis_api.services import AppServices

    app = create_app(make_settings(data_root, store_dir))
    with TestClient(app, raise_server_exceptions=False) as client:
        def explode():
            raise RuntimeError("secret internal detail: /etc/shadow")

        original = AppServices.require_checker
        AppServices.require_checker = lambda self: (_ for _ in ()).throw(
            RuntimeError("secret internal detail"))
        try:
            response = client.post("/api/v1/compliance/check",
                                   json={"product_description": "x"})
            assert response.status_code == 500
            body = response.json()
            assert body["error"] == "internal_error"
            assert "secret internal detail" not in body["detail"]
            assert body["request_id"]
        finally:
            AppServices.require_checker = original


def test_openapi_schema_is_valid_and_documented(client):
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "BIS Standards AI API"
    paths = schema["paths"]
    for path in ("/api/v1/search", "/api/v1/recommend", "/api/v1/recommend/pdf",
                 "/api/v1/compliance/check", "/api/v1/standards/{is_number}",
                 "/api/v1/health", "/api/v1/feedback"):
        assert path in paths, f"{path} missing from the OpenAPI schema"
    # The console is deliberately excluded -- it is not part of the API contract.
    assert "/" not in paths


def test_docs_can_be_disabled_for_a_public_deployment(data_root, store_dir):
    """`BIS_DOCS=0` must remove the schema too, not just the UI page.

    Turning off Swagger UI while leaving /openapi.json served would leave the
    whole API surface documented at a predictable URL, which is the opposite of
    what the setting is for.
    """
    app = create_app(make_settings(data_root, store_dir, docs_enabled=False))
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/api/v1/health").status_code == 200


def test_console_page_is_served_and_uses_relative_urls(client):
    page = client.get("/").text
    assert "BIS Standards API" in page
    # Absolute localhost URLs would break for any browser not on the server host,
    # which is the normal case when the API runs in a container.
    assert "http://localhost:8000" not in page
    assert "/api/v1/search" in page
