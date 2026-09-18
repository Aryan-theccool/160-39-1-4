# BIS Standards API (`bis_api`)

Part 5 of the build: a FastAPI service in front of the RAG engine. It exposes the
retrieval pipeline, the grounded-answer generator and the compliance checker over
HTTP, for the frontend to call.

```bash
cd bis_scraper
export PYTHONPATH=src
uvicorn bis_api.main:app --reload --port 8000
```

Then: <http://localhost:8000/docs> for Swagger UI, <http://localhost:8000/> for a
small built-in console that exercises every endpoint by hand.

---

## 1. The design decision that matters most

**The service boots without its data instead of refusing to start.**

`bis_data/` is gitignored, and the vector store lives outside the repo. Every
other project in this situation crash-loops on `import`, and the operator sees
`FileNotFoundError` from somewhere inside a dependency with no indication of
what to do about it. Here:

- startup records a per-component status and continues (`services.py`);
- `/health` reports `status: "degraded"` or `"unavailable"` **and the exact
  command to fix it**;
- data-backed endpoints return `503` with that same instruction, not a stack
  trace;
- `/docs`, `/` and `/api/v1/health` keep working, so you can see the API even
  when the corpus is missing.

The failure this prevents is not hypothetical: it is the first thing that
happens when anyone else clones this repository.

```
$ curl localhost:8000/api/v1/search?q=cement
{"error":"service_unavailable",
 "detail":"bis_data/ is not loaded, so there is nothing to search. ... regenerate
           with: python create_rag_dataset.py, or set BIS_DATA_DIR. present files: none",
 "request_id":"...","status_code":503}
```

**Degraded is reported separately from unavailable.** A missing vector store is
not fatal — BM25 and TF-IDF still work — so the service answers, but `/health`
says `degraded` and lists `dense retrieval inactive (no vector store)`. A service
that silently answers from a weaker retriever and reports `ok` is lying.

---

## 2. Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | status, index counts, latency, QCO tier |
| `GET` | `/health` | alias, unversioned, for probes |
| `GET` | `/api/v1/search` | hybrid retrieval, no LLM |
| `POST` | `/api/v1/recommend` | grounded answer + citations |
| `POST` | `/api/v1/recommend/pdf` | same, from an uploaded PDF |
| `POST` | `/api/v1/compliance/check` | compliance verdict |
| `GET` | `/api/v1/compliance/report` | the same verdict as printable HTML |
| `GET` | `/api/v1/standards` | list + facet counts |
| `GET` | `/api/v1/standards/{is_number}` | one standard + supersession |
| `POST` | `/api/v1/feedback` | append a judgement to `feedback.jsonl` |
| `GET` | `/` | demo console (not part of the API contract) |

### `GET /api/v1/search`

Fast path: BM25 + TF-IDF + dense vectors, reciprocal-rank fusion and re-ranking.
No LLM, nothing generated.

```
$ curl -s "localhost:8000/api/v1/search?q=drinking%20water%20quality&limit=3"

intent: topic_search | took 12.2 ms
  IS 10500:2012 | Drinking water - Specification | {'bm25:chunks': 3, 'dense:chunks': 2}
```

Query parameters: `q` (required), `limit` (1–50, default 5), `domain`,
`is_number`, `year`, `include_superseded` (default false), `include_passages`,
`reranker` (`auto`|`lexical`|`cross`).

**Measured latency** on the fixture corpus is 12–40 ms server-side with warm
indexes, and the value is returned in `took_ms` and in the `X-Response-Time-Ms`
header rather than being claimed here. Two things make it fast: the indexes are
warmed at startup (`BIS_WARM_INDEXES`, default on) because building them on the
first request would blow the budget on the one request a reviewer is most likely
to try, and the reranker defaults to the lexical one — the cross-encoder changes
the answer, not the speed, and needs `sentence-transformers`.

The original brief said "BM25 only, <500 ms". This is retrieval-only in the same
sense — no generation — but it uses the full hybrid path, because the brief's
actual goal was a fast endpoint and the hybrid retriever is what the RAG engine
is *for*. Set `BIS_RERANKER=none` to drop re-ranking.

### `POST /api/v1/recommend`

```json
{"query": "What standard covers drinking water quality?", "top_k": 3}
```

Returns the RAG answer: `answer`, `citations[]`, `chunks[]`, `intent`,
`confidence`, `grounded`, `warnings[]`, `compliance`, `mode`, `took_ms`, and a
`retrieval` envelope.

`mode` is `extractive` when no LLM is configured and `llm` when one is. The
extractive path quotes retrieved clauses and never invents prose, so an
unconfigured deployment degrades in quality, not in honesty.

The `retrieval` block is what lets a client explain itself rather than only
answer:

```json
{"retrieval": {"mode": "recommend",
               "query_coverage": 0.62,
               "superseded": [{"designation": "IS 269:1989",
                               "superseded_by": "IS 269:2015", "is_current": false}],
               "timings_ms": {"query_processing": 0.1, "sparse": 0.3, "dense": 12.4,
                              "fusion": 0.1, "rerank": 1.0, "total": 13.9}}}
```

`retrieval.mode` is `recommend`, `search` or `history`; the endpoint forces
`recommend`, so a withdrawn edition is never among the recommendations and
`superseded` names the ones that were held back, each with the standard that
replaced it. `timings_ms` is per stage, so "the dense leg is the slow one" is an
observation rather than a guess.

Every result row carries `is_current` and `superseded_by`, so a client can label
a withdrawal wherever one appears instead of leaving the user holding a dead
edition. `superseded_by` is empty for a current standard.

### `POST /api/v1/recommend/pdf`

`multipart/form-data`, field `file`. Max 10 MB (`BIS_MAX_PDF_BYTES`).

Extracts the text, pulls out every IS designation it can find, and leads the
query with those. Returns `source_document` (which extractor ran, how many
pages, how many characters) and `detected_designations`.

- **413** when the file exceeds the limit, with both sizes in human units and
  the name of the variable that changes it.
- **422** when the PDF has no usable text layer — a scan — with a reason. The
  alternative, searching on an empty string, returns the entire corpus ranked by
  nothing, which looks like an answer.
- **422** when the upload is not a PDF at all.

PyMuPDF is used when installed; otherwise a built-in `zlib`-based extractor runs
and says so in `source_document.extractor`. `pdf_text.py` falls back rather than
500ing, because `requirements.txt` deliberately lists PyMuPDF as optional.

### `POST /api/v1/compliance/check`

```json
{"product_description": "33 grade ordinary Portland cement",
 "standards": ["IS 269:1989", "IS 456:1978", "IS 456:2000"]}
```

```json
{"compliance_status": "PARTIAL", "grade": "MOSTLY COMPLIANT",
 "compliance_score": 0.7667, "mandatory_present": [...], "mandatory_missing": [],
 "mandatory_candidates": [...], "sector_candidates": [...],
 "superseded_used": [{"used": "IS 269:1989", "replace_with": "IS 269:2015"}, ...],
 "conflicts": [...], "action_items": [...], "limitations": [...],
 "qco_source": "merged", "qco_verified": true, "grade_capped_by": null}
```

`standards` is optional: omit it and the checker first runs the retriever to
propose which standards apply, and says so. See `docs/RAG_ENGINE.md` §5 for the
scoring rules, the grade caps, and why the mandatory list has three tiers.

### `GET /api/v1/standards/{is_number}`

Accepts any spelling the grammar handles — `IS 456`, `is 456:1978`,
`IS 456 : 1978`. Returns the full record plus a `supersession` object with the
replacement's canonical key, and `404` naming the corpus size when absent.

---

## 3. Cross-cutting behaviour

**Error shape.** Every error — validation, 404, 413, 422, 429, 500, 503 — is the
same object, so the frontend needs one handler:

```json
{"error": "not_found", "detail": "...", "request_id": "a1b2...", "status_code": 404}
```

An unhandled exception logs the traceback server-side and returns only the
request id. A traceback in a response body is an information leak.

**Request ids.** Every response carries `X-Request-ID`, echoed from the request
when it matches `[A-Za-z0-9._:-]{1,64}` and replaced with a fresh id otherwise.
A client-supplied header echoed verbatim into logs is log injection; one with a
newline in it would forge log lines.

**Timing.** `X-Response-Time-Ms` on every response, plus `Access-Control-Expose-Headers`
so browser JavaScript can actually read it.

**Rate limiting.** Sliding window, 100 requests / 60 s per client
(`BIS_RATE_LIMIT_REQUESTS`, `BIS_RATE_LIMIT_WINDOW`). Responses carry
`X-RateLimit-Limit` and `X-RateLimit-Remaining`; a rejection is `429` with
`Retry-After`. `/api/v1/health`, `/health`, `/` and `/docs` are exempt, because
a rate-limited health check reads as an outage.

> **Known limitation.** The limiter is in-process. With `uvicorn --workers N`
> the effective limit is `N × BIS_RATE_LIMIT_REQUESTS`. A real deployment puts a
> shared limiter in front; this is adequate for a single-process service.

**CORS.** `*` by default, because the frontend runs on a different port. Restrict
it with `BIS_CORS_ORIGINS=https://a.example,https://b.example` — a comma-separated
list, validated at startup.

**API keys.** Off by default. Set `BIS_API_KEY` and every route except the health
and docs routes requires a matching `X-API-Key`. Off by default is deliberate: a
service that ships "secure" with a key in the repo is worse than one that is
honestly open, and an unauthenticated localhost demo is the intended use.
Comparison uses `secrets.compare_digest`.

---

## 4. Configuration

| Variable | Default | Meaning |
|---|---|---|
| `BIS_DATA_DIR` | `bis_data` | the corpus |
| `BIS_STORE_DIR` | `<data_dir>/vector_store` | the vector store |
| `BIS_FEEDBACK_PATH` | `<data>/feedback.jsonl` | where feedback is appended |
| `BIS_RAG_EMBEDDER` | `hash` | `hash` \| `sentence-transformers` \| `openai` |
| `BIS_BACKEND` | `auto` | `auto` \| `chroma` \| `json` |
| `BIS_RERANKER` | `auto` | `auto` \| `lexical` \| `cross` |
| `BIS_WARM_INDEXES` | `1` | build BM25 indexes at startup |
| `BIS_RAG_LLM` | unset | `groq` \| `openai` \| `ollama` \| OpenAI-compatible base URL |
| `BIS_API_KEY` | unset | enables `X-API-Key` enforcement |
| `BIS_CORS_ORIGINS` | `*` | comma-separated allow-list |
| `BIS_RATE_LIMIT_REQUESTS` / `_WINDOW` | `100` / `60` | per client |
| `BIS_MAX_PDF_BYTES` | `10485760` | upload limit |
| `BIS_TRUST_PROXY_HEADERS` | `0` | trust `X-Forwarded-*` |
| `BIS_DOCS` | `1` | serve `/docs` and `/openapi.json` |

> **Point both at the same place.** Serving and building must agree on
> `BIS_STORE_DIR`, or the service reports `degraded` and answers from BM25 while
> the vectors you built sit unused. If `bis-rag build` wrote to a custom
> directory — the plan for this project puts it outside the repo, at
> `d:\Dprojects\sih108\chroma_bis_db` — then `bis_api` needs the same value:
>
> ```bash
> export BIS_STORE_DIR=/path/to/chroma_bis_db      # or %BIS_STORE_DIR% on Windows
> ```
>
> `/health` is where this shows up: `retrieval.dense_enabled: false` and
> `vectors: 0` with the rest of the service answering normally.

`hash` is the default embedder because it needs no download and no API key. It
is **lexical, not semantic** — it will not connect "cracked wall" to "structural
defect". Install `sentence-transformers` for real embeddings; the store records
which embedder built it and refuses to mix.

---

## 5. Tests

```bash
python -m pytest tests/test_api.py -q     # 65 tests
```

All offline, against the synthetic corpus. The PDFs are **generated byte by
byte in the test file**, xref table included, rather than checked in as binary
fixtures — so the extraction path is genuinely exercised and the tests document
what a PDF is.

Three tests earn their keep:

- `test_service_boots_without_data_and_says_what_is_missing` — the degraded
  path, which is the one that decides whether a new clone is debuggable.
- `test_builtin_extractor_is_not_fooled_by_et_inside_a_word` — see below.
- `test_unhandled_exception_is_a_clean_json_error_without_a_traceback`.

### The bugs these tests found

**`BT.*?ET` truncated extraction at the first "ET" inside a word.** The
built-in extractor scans text objects with a non-greedy regex, so any document
containing `SHEET`, `CONCRETE` or `COMPLETE` stopped being read at that word —
which is to say, on the first page of nearly every Indian Standard. Now anchored
on token boundaries, with a fallback that scans the raw stream if the text-object
parse yields nothing.

**The fixture drew one long line that ran off the page.** PyMuPDF extracts only
*visible* text, so a 3-designation spec sheet reported 1. The generator is at
fault, not the reader — but it is a genuine reminder that a fixture which does
not look like real input tests the wrong thing.

A third was found by writing the test rather than by running it: `AppServices`
originally assigned `self.data` *before* validating it, so a failed load left a
half-built object and `/health` — the endpoint you call to find out what is
broken — was the one that 500'd. The accessors rely on "not `None` means usable",
so assignment now happens only after every check passes, and `health()` is
additionally wrapped so it cannot raise whatever state the components are in.
