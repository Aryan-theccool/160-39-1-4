"""Resilient HTTP for the BIS pipeline.

Two things make this more than `requests.get`:

1. **Retries with jitter on the codes that actually mean "try later".**
   archive.org returns 429 and 503 under load; BIS's servers are slow. A flat
   `time.sleep(3)` retry loop either hammers the server or gives up too early.

2. **Resumable, checksum-verified downloads.**
   The `gov.in.is.*` corpus is ~22k items and the JP2/PDF derivatives are
   multi-megabyte. A 100 MB scan that fails at 90% should not start over, and a
   truncated file must never be mistaken for a complete one. archive.org
   publishes an md5 for every file in its metadata, so we can verify.

The transport is injected, so the whole module is testable offline.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Optional

import requests

log = logging.getLogger(__name__)

#: Status codes worth retrying. 408/429/5xx are transient; anything else is a
#: real answer and should be surfaced immediately.
RETRY_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 524})

DEFAULT_USER_AGENT = (
    "bis-standards-pipeline/1.0 (+https://github.com/; research use; "
    "contact: set BIS_USER_AGENT)"
)

# archive.org's documented rate guidance is "be nice"; 1 rps is a safe default
# for metadata calls.
DEFAULT_MIN_INTERVAL = 1.0


class HttpError(RuntimeError):
    """A request ultimately failed after all retries."""

    def __init__(self, message: str, *, status: Optional[int] = None, url: str = ""):
        super().__init__(message)
        self.status = status
        self.url = url


class ChecksumMismatch(HttpError):
    """A completed download did not match its published md5."""


@dataclass
class FetchResult:
    """Outcome of a GET, carrying what caching needs to know."""

    url: str
    status: int
    content: bytes
    etag: Optional[str] = None
    from_cache: bool = False

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.text)


@dataclass
class RetryPolicy:
    attempts: int = 5
    backoff_base: float = 1.5
    backoff_cap: float = 60.0
    jitter: float = 0.25

    def delay(self, attempt: int) -> float:
        """Delay before retry number `attempt` (1-based), with jitter."""
        raw = min(self.backoff_cap, self.backoff_base ** attempt)
        spread = raw * self.jitter
        return max(0.0, raw + random.uniform(-spread, spread))


@dataclass
class HttpClient:
    """A polite, retrying, caching HTTP client.

    Parameters
    ----------
    session:
        Anything with a ``.request(...)`` signature compatible with
        ``requests.Session``. Inject a fake in tests.
    sleep:
        Injectable clock so tests do not actually wait.
    cache_dir:
        When set, GET responses with an ETag are cached to disk and
        revalidated with ``If-None-Match``.
    """

    session: object = None
    user_agent: str = DEFAULT_USER_AGENT
    timeout: float = 30.0
    policy: RetryPolicy = field(default_factory=RetryPolicy)
    min_interval: float = DEFAULT_MIN_INTERVAL
    cache_dir: Optional[Path] = None
    sleep: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = requests.Session()
        self._last_request = 0.0
        if self.cache_dir is not None:
            Path(self.cache_dir).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def get(self, url: str, *, params: Optional[dict] = None,
            headers: Optional[dict] = None, use_cache: bool = True) -> FetchResult:
        """GET with retries, polite spacing and optional ETag caching."""
        req_headers = {"User-Agent": self.user_agent, "Accept": "*/*"}
        if headers:
            req_headers.update(headers)

        cache_key = self._cache_key(url, params)
        cached = self._read_cache(cache_key) if (use_cache and cache_key) else None
        if cached and cached.get("etag"):
            req_headers["If-None-Match"] = cached["etag"]

        resp = self._request("GET", url, params=params, headers=req_headers)

        if resp.status_code == 304 and cached:
            log.debug("cache hit (304): %s", url)
            return FetchResult(url=url, status=200, content=cached["body"].encode("utf-8"),
                               etag=cached.get("etag"), from_cache=True)

        if resp.status_code >= 400:
            raise HttpError(f"GET {url} -> {resp.status_code}",
                            status=resp.status_code, url=url)

        etag = resp.headers.get("ETag")
        if etag and cache_key:
            self._write_cache(cache_key, etag, resp.content)

        return FetchResult(url=url, status=resp.status_code, content=resp.content, etag=etag)

    def get_json(self, url: str, *, params: Optional[dict] = None, **kw):
        return self.get(url, params=params, **kw).json()

    def download(self, url: str, dest: Path, *, expected_md5: Optional[str] = None,
                 chunk_size: int = 1 << 16, overwrite: bool = False) -> Path:
        """Download `url` to `dest`, resuming across failures.

        Writes to ``dest.part`` and only renames on a verified complete
        transfer, so `dest` never exists in a half-written state.

        Raises :class:`ChecksumMismatch` if `expected_md5` is given and does not
        match -- the partial file is kept so the next run can retry.
        """
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(dest.suffix + ".part")

        if dest.exists() and not overwrite:
            if expected_md5 and _md5_file(dest) != expected_md5.lower():
                log.warning("cached file failed checksum, redownloading: %s", dest)
                dest.unlink()
            else:
                log.debug("already present: %s", dest)
                return dest

        attempt = 0
        while True:
            attempt += 1
            resume_at = part.stat().st_size if part.exists() else 0
            headers = {"User-Agent": self.user_agent}
            if resume_at:
                headers["Range"] = f"bytes={resume_at}-"

            try:
                resp = self.session.request(  # type: ignore[union-attr]
                    "GET", url, headers=headers, stream=True, timeout=self.timeout
                )
            except requests.RequestException as exc:
                if attempt >= self.policy.attempts:
                    raise HttpError(f"download {url} failed: {exc}", url=url) from exc
                self._backoff(attempt, exc)
                continue

            try:
                if resp.status_code == 416:
                    # Range not satisfiable: our .part is bogus, start clean.
                    part.unlink(missing_ok=True)
                    resume_at = 0
                    continue

                if resp.status_code not in (200, 206):
                    if resp.status_code in RETRY_STATUS and attempt < self.policy.attempts:
                        self._backoff(attempt, f"HTTP {resp.status_code}")
                        continue
                    raise HttpError(f"download {url} -> {resp.status_code}",
                                    status=resp.status_code, url=url)

                # A 200 in reply to a Range request means the server ignored the
                # Range; we must truncate rather than append duplicate bytes.
                mode = "ab" if (resp.status_code == 206 and resume_at) else "wb"
                with open(part, mode) as fh:
                    for chunk in resp.iter_content(chunk_size=chunk_size):
                        if chunk:
                            fh.write(chunk)
            except requests.RequestException as exc:
                if attempt >= self.policy.attempts:
                    raise HttpError(f"download {url} interrupted: {exc}", url=url) from exc
                self._backoff(attempt, exc)
                continue
            finally:
                resp.close()

            if expected_md5:
                actual = _md5_file(part)
                if actual != expected_md5.lower():
                    if attempt >= self.policy.attempts:
                        raise ChecksumMismatch(
                            f"{url}: md5 {actual} != expected {expected_md5}",
                            url=url,
                        )
                    log.warning("checksum mismatch on %s, retrying (%d)", dest.name, attempt)
                    part.unlink(missing_ok=True)
                    self._backoff(attempt, "checksum mismatch")
                    continue

            part.replace(dest)
            self._throttle()
            return dest

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _request(self, method: str, url: str, **kwargs):
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.policy.attempts + 1):
            self._throttle()
            try:
                resp = self.session.request(  # type: ignore[union-attr]
                    method, url, timeout=self.timeout, **kwargs
                )
            except requests.RequestException as exc:
                last_exc = exc
                if attempt >= self.policy.attempts:
                    break
                self._backoff(attempt, exc)
                continue

            if resp.status_code in RETRY_STATUS and attempt < self.policy.attempts:
                retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
                if retry_after is not None:
                    log.info("server asked us to wait %ss", retry_after)
                    self.sleep(retry_after)
                else:
                    self._backoff(attempt, f"HTTP {resp.status_code}")
                continue
            return resp

        raise HttpError(f"{method} {url} failed after {self.policy.attempts} attempts: {last_exc}",
                        url=url)

    def _backoff(self, attempt: int, reason: object) -> None:
        delay = self.policy.delay(attempt)
        log.warning("retrying in %.1fs (attempt %d): %s", delay, attempt, reason)
        self.sleep(delay)

    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval:
            self.sleep(self.min_interval - elapsed)
        self._last_request = time.monotonic()

    def _cache_key(self, url: str, params: Optional[dict]) -> Optional[str]:
        if self.cache_dir is None:
            return None
        basis = url + ("?" + json.dumps(params, sort_keys=True) if params else "")
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return Path(self.cache_dir) / f"{key}.json"  # type: ignore[arg-type]

    def _read_cache(self, key: str) -> Optional[dict]:
        path = self._cache_path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write_cache(self, key: str, etag: str, body: bytes) -> None:
        try:
            self._cache_path(key).write_text(
                json.dumps({"etag": etag, "body": body.decode("utf-8", "replace")}),
                encoding="utf-8",
            )
        except OSError as exc:  # a cache failure must never break a scrape
            log.debug("cache write failed: %s", exc)


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _md5_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_pages(client: HttpClient, url: str, params: dict, *,
               page_size: int, max_items: Optional[int],
               extract: Callable[[dict], Iterator[dict]]) -> Iterator[dict]:
    """Paginate a Solr-style JSON endpoint (`rows` / `start`).

    archive.org's ``advancedsearch.php`` caps `rows` at 200 and paginates by
    offset. This drives that loop and stops at the server-reported
    ``numFound`` so we never spin on empty pages.
    """
    start = 0
    seen = 0
    while True:
        page_params = dict(params, rows=page_size, start=start)
        payload = client.get_json(url, params=page_params)
        response = payload.get("response", {})
        num_found = int(response.get("numFound", 0))
        docs = response.get("docs", []) or []

        if not docs:
            return

        for doc in extract(payload):
            yield doc
            seen += 1
            if max_items is not None and seen >= max_items:
                return

        start += len(docs)
        if start >= num_found:
            return
