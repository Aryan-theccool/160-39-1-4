"""Shared test doubles.

The pipeline takes its transport as a parameter, so these fakes exercise the
real ``HttpClient`` / scraper code paths without any network access.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

import requests

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str) -> dict:
    return json.loads(fixture(name))


class FakeResponse:
    """Minimal stand-in for ``requests.Response``."""

    def __init__(self, status_code: int = 200, content: bytes = b"",
                 headers: Optional[dict] = None, chunks: Optional[list[bytes]] = None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self._chunks = chunks if chunks is not None else [content]
        self.closed = False

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def iter_content(self, chunk_size: int = 8192):
        for chunk in self._chunks:
            yield chunk

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)

    def close(self):
        self.closed = True


class FakeSession:
    """Routes requests by URL. `routes` maps a URL substring to a responder.

    A responder is either a ``FakeResponse`` or a callable
    ``(method, url, kwargs) -> FakeResponse``.
    """

    def __init__(self, routes: Optional[dict] = None, default: Optional[FakeResponse] = None):
        self.routes: dict[str, object] = routes or {}
        self.default = default or FakeResponse(404, b"not found")
        self.calls: list[dict] = []

    def add(self, url_fragment: str, responder):
        self.routes[url_fragment] = responder
        return self

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, "kwargs": kwargs})
        for fragment, responder in self.routes.items():
            if fragment in url:
                return responder(method, url, kwargs) if callable(responder) else responder
        return self.default

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    # -- assertions ---------------------------------------------------
    def urls(self) -> list[str]:
        return [c["url"] for c in self.calls]

    def count(self, url_fragment: str) -> int:
        return sum(1 for c in self.calls if url_fragment in c["url"])


class NoSleep:
    """Records sleeps instead of performing them, so retries are instant."""

    def __init__(self):
        self.total = 0.0
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.total += seconds
        self.calls.append(seconds)
