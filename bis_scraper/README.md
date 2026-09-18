# BIS Standards Pipeline

Builds a searchable dataset of Bureau of Indian Standards (Indian Standards)
from sources that actually work and are legally usable, then indexes it for
retrieval.

**Read [`docs/CORRECTIONS.md`](docs/CORRECTIONS.md) first.** This repo is a
corrected rebuild of an earlier three-scraper plan; that document records, with
live evidence, why three of its four components could not have produced data.
The short version:

- `standards.bis.gov.in/standardlist` returns 404; the real catalogue is a JS
  app whose detail pages use unguessable encrypted IDs.
- The BIS 2005 catalogue book on archive.org is lending-restricted and answers
  `401 Authorization Required`. It cannot be downloaded, so it cannot be OCR'd.
- The archive.org `gov.in.is.*` collection *is* the right source — 22,025
  CC0-licensed BIS standards — and it already ships plain-text OCR, so no PDF
  parsing or Tesseract is needed.

## Layout

```
bis_scraper/
├── src/bis_pipeline/
│   ├── iscode.py           IS designation grammar -> one canonical join key
│   ├── http.py             retrying, caching, resumable + checksum-verified HTTP
│   ├── archive_scraper.py  archive.org gov.in.is.* (metadata + OCR text)
│   ├── mandatory.py        BIS compulsory-certification (QCO) IS numbers
│   ├── coverage.py         which QCO standards the CC0 corpus already holds
│   ├── merger.py           one row per standard; resolves which edition is current
│   ├── index.py            dependency-free TF-IDF index (dense optional)
│   └── cli.py              the commands below
├── src/bis_rag/            RAG engine: vector store, hybrid search, answers
│   ├── schema.py           the bis_data contract; fails loudly when broken
│   ├── data.py             BisData: all of bis_data/ behind one object
│   ├── embeddings.py       hash / sentence-transformers / API, + mixing guard
│   ├── vectorstore.py      ChromaDB, and a dependency-free JSON+NumPy store
│   ├── build_vector_store.py  Part 1: build the store
│   ├── query_processor.py  Part 2a: intent, filters, ontology expansion
│   ├── bm25.py, hybrid.py  Part 3: BM25 + TF-IDF + dense, RRF fusion, reranking
│   ├── rag.py              Part 2b: grounded answers, verified citations
│   ├── compliance.py       Part 4: QCO mandatory list, scoring, HTML gap report
│   └── cli.py              `bis-rag doctor|build|search|ask|compliance|analyze`
├── src/bis_api/            Part 5: the FastAPI service
│   ├── main.py             app factory, exception handlers, lifespan
│   ├── services.py         component loading that degrades instead of crashing
│   ├── pdf_text.py         PDF text extraction, PyMuPDF or built-in
│   ├── config.py           every setting, from the environment
│   ├── models/             request + response schemas (they document /docs)
│   ├── middleware/         request ids, timing, rate limiting
│   └── routers/            search, recommend, compliance, standards, system, demo
├── tests/                  335 tests, all offline, replaying captured payloads
├── docs/CORRECTIONS.md     what changed versus the original plan, with evidence
├── docs/RAG_ENGINE.md      the RAG engine: data contract, design, limits
├── docs/API.md             the HTTP API: endpoints, config, limits
└── requirements.txt
```

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Four packages for the default path: `requests`, `beautifulsoup4`, `lxml`,
`pandas`. Everything else in `requirements.txt` is commented out and annotated
with the reason it is optional.

## Run

```bash
export PYTHONPATH=src

# 1. archive.org: metadata + OCR text. Cap it on a first run.
python -m bis_pipeline archive --max-items 200

# 2. BIS compulsory-certification IS numbers
python -m bis_pipeline mandatory

# 3. which QCO-mandated standards are already free to index?
python -m bis_pipeline coverage

# 4. one dataset
python -m bis_pipeline merge

# 5. index and query
python -m bis_pipeline index
python -m bis_pipeline query "submersible pump" "drinking water quality"
```

Or all of it: `python -m bis_pipeline all --max-items 200 "drinking water"`.

Outputs land in `bis_data/`:

```
bis_data/archive/items.jsonl        one normalised item per line (resumable)
bis_data/archive/text/<id>.txt      OCR text per standard
bis_data/coverage/qco_held.csv          QCO standards already free to index
bis_data/coverage/qco_missing.csv       QCO standards to obtain from BIS
bis_data/merged/merged_standards.{json,jsonl,csv}
bis_data/index/search_index.json
```

### The full collection

`archive` with no `--max-items` walks all ~22k items. At the default 1 request/
second that is roughly 12 hours for metadata alone, because each item needs its
own `/metadata/` call for the file list. Budget accordingly, and note:

- `items.jsonl` is append-only and re-read on start, so a killed run resumes
  where it stopped.
- GET responses with an ETag are cached under `bis_data/http_cache/`.
- Downloads resume via HTTP `Range` and are verified against archive.org's
  published md5; a file only appears at its final path once complete and
  checksum-correct.
- Access-restricted items are detected and skipped, not retried.

Use `--no-text` for a metadata-only pass, `--pdfs` if you genuinely need PDFs.

## What the merged dataset looks like

One row per IS designation. `IS 302-2-15:2009`, `IS 302 (Part 2 / Section 15):2009`
and archive.org's `gov.in.is.302.2.15.2009` all collapse onto one key.

Fields worth knowing:

| field | meaning |
|---|---|
| `canonical` | join key, e.g. `IS\|302\|2\|15\|2009\|None` |
| `is_current` | false when a newer edition is present |
| `superseded_by` | that newer edition |
| `is_compulsory` | named in a BIS Quality Control Order |
| `has_full_text` | freely licensed OCR text was retrieved |
| `division`, `section_name`, `committee` | from archive.org's `description` |
| `sources` | which inputs contributed, e.g. `["ARCHIVE_ORG","BIS_QCO"]` |

Edition resolution matters for a recommender: without it, a query for
"submersible pump" can surface IS 14220:1994 alongside the 2002 revision with
nothing to say the older one is superseded. `search()` filters on `is_current`
by default; pass `--include-superseded` to see everything.

## The search index

Default backend is a dependency-free TF-IDF cosine index over the standard
library. It is a lexical baseline, not semantic search: "drinking water
quality" matches because those words appear, not because the meaning is close.

For dense retrieval pass an embedding function — no vector DB required:

```python
from sentence_transformers import SentenceTransformer
from bis_pipeline.index import SearchIndex

model = SentenceTransformer("BAAI/bge-small-en-v1.5")
index = SearchIndex().build(records, embed_fn=lambda t: model.encode(t).tolist())
```

or `python -m bis_pipeline index --embed-model BAAI/bge-small-en-v1.5`
(a ~130 MB download; `bge-large` is ~1.3 GB). `export_for_chroma(index)`
renders the shape `collection.add(**...)` expects if you do want ChromaDB.

## RAG engine (`bis_rag`)

Everything above gets you a dataset and a lexical index. `bis_rag` turns it into
a retrieval system: a persistent vector store, hybrid search, and grounded
answers with citations.

```bash
export PYTHONPATH=src

python -m bis_rag doctor                            # what data/deps are present
python -m bis_rag build                             # Part 1: embed into a vector store
python -m bis_rag search "water pipe for potable supplies"
python -m bis_rag analyze "Is cement mandatory?"    # how the query was understood
python -m bis_rag ask "Has IS 456:1978 been superseded?"
python -m bis_rag compliance "ordinary portland cement" --html gap.html   # Part 4
python -m bis_rag eval --baseline                   # Part 7: retrieval metrics
```

It reads `bis_data/` directly and **reuses the existing TF-IDF index** rather
than rebuilding it. ChromaDB is used when installed and a dependency-free
JSON+NumPy store otherwise, so `build` runs anywhere.

Two things it refuses to do, because both are silent failures otherwise:

- **It will not embed empty text.** The field-name traps in `bis_data` are a
  documented contract (`bis_rag/schema.py`) and a dataset that violates it
  raises with the file, the field, the keys it looked for, and the coverage
  report — instead of indexing 9,043 blank documents and reporting success.
- **It will not mix embedders.** A store records a fingerprint of the embedder
  that built it; querying with a different one raises rather than returning
  plausible-looking, meaningless neighbours.

It also checks compliance against the QCO mandatory list and writes a printable
gap report. The mandatory list is resolved in tiers — the real scrape from
`bis_data/mandatory/mandatory.json` when present, a clearly-labelled **unverified**
built-in seed list otherwise — and the tier is reported on every result. On the
seed tier a "fully compliant" verdict is impossible, because an incomplete list
of mandatory standards cannot prove compliance.

Read [`docs/RAG_ENGINE.md`](docs/RAG_ENGINE.md) for the data contract, the
fusion/ranking rules, the compliance scoring rules, and what is still unbuilt
(Part 6 and the RAGAS evaluation).

## Evaluation (`bis_rag.evaluate`)

`qa_pairs.jsonl` is a smoke test, not an evaluation set: its 985 questions are
generated from templates like `"What is {designation}?"`, so a designation lookup
answers all of them and they measure nothing about retrieval. Part 7 replaces
them with 56 hand-written cases in `eval/retrieval_cases.jsonl` — real questions
with no designation in them, including eight with no domain keywords at all.

```bash
python -m bis_rag eval --baseline           # Hit Rate @1/3/5/10, MRR@5, latency, gates
```

It reports Hit Rate, MRR, hallucination rate, superseded-violation rate and
latency P50/P95/P99, broken out by difficulty; `--baseline` re-runs the same
cases against BM25-only so a hit rate cannot be quoted without knowing whether
the hybrid pipeline earned it. Exit code 1 on a threshold breach, so it works in
CI. The superseded-violation threshold is hard zero.

This measurement earned its keep before it was finished: the first version of the
supersession check reported a **50% violation rate on a run where the current
edition was ranked first in every case** — a false alarm that would have taught
anyone reading it to ignore the number. Corrected, it found a real defect: for an
aggregates query `IS 456:1978` (withdrawn) ranked 5th and `IS 456:2000` (current)
7th, so the first edition a user saw was the one that had been replaced. Fixed.

### Production validation

```bash
python -m bis_rag doctor                      # what data is this, exactly?
python -m bis_rag eval --production --ablation
```

`doctor` prints the resolved data path, store path, corpus size, chunk count,
embedder, backend and per-collection vector counts, plus a `PROVENANCE` line. It
exits `2` when there is no corpus at all, so `bis-rag doctor && ...` cannot walk
past a missing data directory.
A synthetic fixture writes a marker into its own tree, and `--production` turns
"this corpus is a fixture, or too small to be the real one" into exit code 2
rather than a number someone might quote. Refusing to certify fixture data is
not ceremony: a hit rate over a corpus chosen to contain the answers looks
exactly like a hit rate over a real one.

Every ranking metric is reported **covered-only** (is the ranking working?) and
**end-to-end** (what does a user experience?), because the gap between them is
the coverage gap and only one of the two is a statement about the retriever.
`missing_corpus_standards.json` names the standards the corpus lacks and the
case ids each one costs.

Both supersession metrics are measured and both target zero: a withdrawn edition
must not outrank its own current edition, and must not reach the ranked
recommendations at all. Search, history and recommendation modes are distinct
policies, not one filter, and the recommendation path is measured by rerunning
every case in recommendation mode rather than assuming the filter did its job.

`eval/results/` holds the artifacts — `latest.json`, `latest.md`,
`failures.jsonl`, `missing_corpus_standards.json`, `ablation.csv` — on every run.

See [`eval/README.md`](eval/README.md).

## HTTP API (`bis_api`)

Part 5 wraps the engine in a FastAPI service for the frontend to call:

```bash
export PYTHONPATH=src
uvicorn bis_api.main:app --reload --port 8000
```

Swagger UI at `/docs`, a hand-testable console at `/`, and:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/search` | hybrid retrieval, no LLM |
| `POST` | `/api/v1/recommend` | grounded answer + citations |
| `POST` | `/api/v1/recommend/pdf` | the same, from an uploaded PDF |
| `POST` | `/api/v1/compliance/check` | compliance verdict |
| `GET` | `/api/v1/standards/{is_number}` | one standard + supersession |
| `GET` | `/api/v1/health` | status, index counts, latency |
| `POST` | `/api/v1/feedback` | append a judgement to `feedback.jsonl` |

It **starts without `bis_data/`** rather than crash-looping: `/health` reports
`unavailable` with the command that fixes it, data endpoints return 503, and
`/docs` still renders. A missing vector store is `degraded`, not fatal — BM25
still answers, and the service says which retriever is doing the work.

Every response carries `X-Request-ID` and `X-Response-Time-Ms`; every error is
the same `{error, detail, request_id, status_code}` object; CORS is open by
default (hackathon), constrainable with `BIS_CORS_ORIGINS`. Set `BIS_API_KEY` to
require `X-API-Key` on the data endpoints.

Read [`docs/API.md`](docs/API.md) for the endpoint reference, the environment
variables, and the two bugs the API tests found.

## Web frontend (`bis_web`)

Part 6 lives in [`../bis_web`](../bis_web): a Next.js 14 frontend — six pages
(search, results, tender PDF analysis, compliance, standards browser, dashboard)
in an Indian tricolour theme, talking to this API. Run the API first, then:

```bash
cd ../bis_web && npm install && npm run dev
```

It calls `/api/v1/*` on its own origin and lets Next.js proxy to this service,
so it works whether or not the browser is on the same machine as the API. See
[`../bis_web/README.md`](../bis_web/README.md).

## Tests

```bash
python -m pytest
```

425 tests, no network. The HTTP transport is injected, so the real client,
scraper and pagination code run against captured real API payloads and a real
(CC0) OCR text file. The 168 `bis_rag` and `bis_api` tests run against a
miniature `bis_data/` whose field names are copied from the real generators;
the API tests build their own PDFs byte by byte, xref table included, so the
extraction path is genuinely exercised.

Two are worth pointing out because they caught real bugs:

- `TestCrossProcessPersistence` builds an index in one process and queries it
  in another. Feature hashing originally used Python's `hash()`, which is
  salted per process — a saved index silently returned zero results. In-process
  tests could never see this.
- `test_does_not_invent_codes_from_corrupted_ocr` asserts that the string
  `IS 1 113C7 - 1905` — real OCR output for IS 11367:1985 — yields no codes at
  all, rather than a bogus `IS 1`.
- `test_empty_text_field_is_a_hard_error` builds a chunks file whose text field
  is empty under the key names the original `build_chromadb.py` used, and
  asserts the loader refuses it. Embedding empty strings "succeeds" and returns
  confident nonsense, so this is the one failure that must never be silent.

## Getting the standards you don't already have

`coverage` splits BIS's QCO-mandated standards into two groups:

```
  QCO-mandated standards : 612
  already free (CC0)     : 481  (78.6%)
  need registration      : 131
    qco_held     bis_data/coverage/qco_held.csv
    qco_missing  bis_data/coverage/qco_missing.csv
```

`qco_held.csv` lists what the pipeline can index today, with archive.org URLs.
`qco_missing.csv` lists what it cannot.

For the remainder, BIS's own FAQ says to register at
`https://standardsbis.bsbedge.com/` and download Indian Standards **free**
(only ISO/IEC-adopted standards cost money). Registration needs an email
address; the PDFs carry FileOpen DRM.

That is a per-account entitlement, so this repo deliberately stops at telling
you *which* standards to fetch rather than fetching them. Bulk-mirroring that
portal or stripping its DRM is not something the pipeline does.

Note that the "cannot be downloaded, printed or stored" wording you may find
quoted belongs to BIS's **2019 view-only viewer** at
`bsbedge.com/mandatory-indian-standards`, which now returns 404. It does not
apply to the current portal.

## Etiquette

- archive.org's `gov.in.is.*` items are CC0 and were published under India's
  Right to Information Act 2005. Indexing them is fine.
- Default rate limit is 1 request/second per host, and retries honour
  `Retry-After`. Raise `--min-interval` if you are being throttled; do not
  lower it.
- Lending-restricted archive.org items are detected and skipped rather than
  circumvented.
