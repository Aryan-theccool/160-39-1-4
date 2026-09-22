"""Tests for the HTTP layer: retries, caching and resumable downloads."""

import hashlib
from pathlib import Path

import pytest
import requests

from bis_pipeline.http import ChecksumMismatch, HttpClient, HttpError, RetryPolicy, iter_pages

from conftest import FakeResponse, FakeSession, NoSleep


def make_client(session, **kw) -> HttpClient:
    sleep = NoSleep()
    client = HttpClient(
        session=session, sleep=sleep, min_interval=0.0,
        policy=RetryPolicy(attempts=4, backoff_base=1.1, jitter=0.0), **kw,
    )
    return client


class TestRetries:
    def test_retries_503_then_succeeds(self):
        state = {"n": 0}

        def responder(method, url, kwargs):
            state["n"] += 1
            if state["n"] < 3:
                return FakeResponse(503, b"busy")
            return FakeResponse(200, b'{"ok": true}')

        session = FakeSession({"api": responder})
        client = make_client(session)

        result = client.get("https://example.test/api")
        assert result.status == 200
        assert result.json() == {"ok": True}
        assert session.count("api") == 3

    def test_honours_retry_after_header(self):
        state = {"n": 0}

        def responder(method, url, kwargs):
            state["n"] += 1
            if state["n"] == 1:
                return FakeResponse(429, b"slow down", {"Retry-After": "7"})
            return FakeResponse(200, b"ok")

        session = FakeSession({"api": responder})
        client = make_client(session)
        client.get("https://example.test/api")

        sleep = client.sleep
        assert 7 in sleep.calls, "must wait the server-specified interval"

    def test_gives_up_after_max_attempts(self):
        session = FakeSession({"api": FakeResponse(503, b"busy")})
        client = make_client(session)
        with pytest.raises(HttpError) as exc:
            client.get("https://example.test/api")
        assert exc.value.status == 503
        assert session.count("api") == 4

    def test_4xx_is_not_retried(self):
        session = FakeSession({"api": FakeResponse(404, b"nope")})
        client = make_client(session)
        with pytest.raises(HttpError) as exc:
            client.get("https://example.test/api")
        assert exc.value.status == 404
        assert session.count("api") == 1, "a 404 is an answer, not a transient fault"

    def test_connection_errors_are_retried(self):
        state = {"n": 0}

        def responder(method, url, kwargs):
            state["n"] += 1
            if state["n"] < 3:
                raise requests.ConnectionError("reset")
            return FakeResponse(200, b"ok")

        session = FakeSession({"api": responder})
        client = make_client(session)
        assert client.get("https://example.test/api").content == b"ok"
        assert session.count("api") == 3


class TestEtagCache:
    def test_304_returns_cached_body(self, tmp_path):
        state = {"n": 0}

        def responder(method, url, kwargs):
            state["n"] += 1
            if kwargs.get("headers", {}).get("If-None-Match") == '"abc"':
                return FakeResponse(304, b"")
            return FakeResponse(200, b'{"v": 1}', {"ETag": '"abc"'})

        session = FakeSession({"api": responder})
        client = make_client(session, cache_dir=tmp_path)

        first = client.get("https://example.test/api")
        second = client.get("https://example.test/api")

        assert first.from_cache is False
        assert second.from_cache is True
        assert second.json() == {"v": 1}
        assert session.count("api") == 2


class TestDownload:
    def test_writes_file_and_verifies_md5(self, tmp_path):
        payload = b"x" * 10_000
        session = FakeSession({"file": FakeResponse(200, payload, chunks=[payload[:4000], payload[4000:]])})
        client = make_client(session)
        dest = tmp_path / "sub" / "a.bin"

        out = client.download("https://example.test/file", dest,
                              expected_md5=hashlib.md5(payload).hexdigest())

        assert out == dest and dest.read_bytes() == payload
        assert not dest.with_suffix(".bin.part").exists(), "no partial file left behind"

    def test_checksum_mismatch_raises_and_keeps_partial(self, tmp_path):
        session = FakeSession({"file": FakeResponse(200, b"corrupt")})
        client = make_client(session)
        dest = tmp_path / "a.bin"

        with pytest.raises(ChecksumMismatch):
            client.download("https://example.test/file", dest,
                            expected_md5="0" * 32)

        assert not dest.exists(), "a bad file must never appear at the final path"

    def test_skips_existing_verified_file(self, tmp_path):
        payload = b"already here"
        dest = tmp_path / "a.bin"
        dest.write_bytes(payload)
        session = FakeSession({"file": FakeResponse(200, b"ignored")})
        client = make_client(session)

        client.download("https://example.test/file", dest,
                        expected_md5=hashlib.md5(payload).hexdigest())

        assert session.count("file") == 0, "must not redownload a verified file"

    def test_resumes_with_range_and_appends(self, tmp_path):
        whole = b"0123456789"
        part = tmp_path / "a.bin.part"
        part.write_bytes(whole[:4])

        def responder(method, url, kwargs):
            rng = kwargs.get("headers", {}).get("Range")
            assert rng == "bytes=4-", f"expected a resume request, got {rng}"
            return FakeResponse(206, whole[4:], chunks=[whole[4:]])

        session = FakeSession({"file": responder})
        client = make_client(session)
        dest = client.download("https://example.test/file", tmp_path / "a.bin",
                               expected_md5=hashlib.md5(whole).hexdigest())

        assert dest.read_bytes() == whole, "resumed bytes must be appended, not duplicated"

    def test_server_ignoring_range_does_not_duplicate_bytes(self, tmp_path):
        whole = b"0123456789"
        (tmp_path / "a.bin.part").write_bytes(whole[:4])

        # Server answers 200 with the full body despite the Range header.
        session = FakeSession({"file": FakeResponse(200, whole, chunks=[whole])})
        client = make_client(session)
        dest = client.download("https://example.test/file", tmp_path / "a.bin",
                               expected_md5=hashlib.md5(whole).hexdigest())

        assert dest.read_bytes() == whole


class TestIterPages:
    def test_stops_at_num_found(self):
        pages = {
            0: {"response": {"numFound": 3, "docs": [{"i": 1}, {"i": 2}]}},
            2: {"response": {"numFound": 3, "docs": [{"i": 3}]}},
        }

        def responder(method, url, kwargs):
            import json
            start = kwargs["params"]["start"]
            return FakeResponse(200, json.dumps(pages[start]).encode())

        session = FakeSession({"search": responder})
        client = make_client(session)

        got = list(iter_pages(client, "https://example.test/search", {"q": "x"},
                              page_size=2, max_items=None,
                              extract=lambda p: iter(p["response"]["docs"])))

        assert [d["i"] for d in got] == [1, 2, 3]
        assert session.count("search") == 2, "must not request a page past numFound"

    def test_respects_max_items(self):
        import json

        def responder(method, url, kwargs):
            body = {"response": {"numFound": 100, "docs": [{"i": n} for n in range(10)]}}
            return FakeResponse(200, json.dumps(body).encode())

        session = FakeSession({"search": responder})
        client = make_client(session)

        got = list(iter_pages(client, "https://example.test/search", {},
                              page_size=10, max_items=4,
                              extract=lambda p: iter(p["response"]["docs"])))
        assert len(got) == 4

    def test_empty_page_terminates(self):
        import json
        session = FakeSession({"search": FakeResponse(
            200, json.dumps({"response": {"numFound": 999, "docs": []}}).encode())})
        client = make_client(session)

        got = list(iter_pages(client, "https://example.test/search", {},
                              page_size=10, max_items=None,
                              extract=lambda p: iter(p["response"]["docs"])))
        assert got == []
        assert session.count("search") == 1
