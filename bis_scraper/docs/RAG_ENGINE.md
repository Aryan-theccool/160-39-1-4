# RAG Engine (`bis_rag`)

Parts 1–3 of the build plan: the vector store, the RAG pipeline + query
processor, and hybrid search with fusion and reranking — implemented against the
**real** field names in `bis_data/`, with the silent-failure modes closed.

```
    python -m bis_rag.build_vector_store     # Part 1  (bis-rag build)
    python -m bis_rag.query_processor        # Part 2a (bis-rag analyze)
    python -m bis_rag.rag                    # Part 2b (bis-rag ask)
    python -m bis_rag.hybrid                 # Part 3  (bis-rag search)
```

---

## 1. Start here: the field names are not what you would guess

The single most expensive bug in this project is a wrong dictionary key, because
it fails **silently**. A build script that reads a key which does not exist gets
`None`, embeds an empty string, indexes 9,043 vectors of boilerplate headers,
and prints *"ChromaDB READY!"*. Search then returns confident nonsense, and
nothing in the output looks wrong.

The original `build_chromadb.py` draft had exactly this bug. Its field names and
the real ones:

| Draft read                       | Real field          | Where it is written        |
| -------------------------------- | ------------------- | -------------------------- |
| `chunk.get("text", …)`           | **`chunk`**         | `create_rag_dataset.py:64` |
| `chunk.get("content")`           | **`chunk`**         | same                       |
| `chunk.get("is_number")`         | **`designation`**   | `create_rag_dataset.py:60` |
| `chunk.get("status")`            | **`is_current`** (bool) | `create_rag_dataset.py:69` |
| `std.get("text")`                | *absent* in `knowledge_base.json`; the text is **`text_snippet`** in `search_corpus.jsonl` | `create_rag_dataset.py:159` |
| `std.get("keywords")`            | `keywords` ✅        | `create_rag_dataset.py:106` |

Consequences of the draft as written: every one of the 9,043 chunk documents
would have ended at `Content:` with nothing after it, and all 197 standards
would have embedded an empty `Summary:`. `bis_rag.schema` fixes this by
declaring the contract once and refusing to build from a dataset that violates
it.

### The full contract

`bis_data/rag/chunked_documents.jsonl` — one JSON object per line:

```json
{"standard_id": "IS|302|2|15|2009|None", "designation": "IS 302 (Part 2 / Section 15):2009",
 "chunk_id": "IS|302|2|15|2009|None__chunk_3", "chunk_index": 3, "total_chunks": 12,
 "chunk": "<the passage text>", "title": "…", "division": "Electrical", "committee": "ETD 32",
 "year": 2009, "is_current": true, "archive_url": "https://archive.org/details/…"}
```

| File | Shape | Used for |
| ---- | ----- | -------- |
| `rag/chunked_documents.jsonl` | 9,043 objects, schema above | `bis_chunks` collection, BM25 |
| `rag/knowledge_base.json` | 197 objects: `id`, `designation`, `title`, `year`, `division`, `committee`, `part`, `section`, `keywords[]`, `is_current`, `superseded_by`, `has_full_text`, `archive_url`, `license` | `bis_standards` collection |
| `rag/search_corpus.jsonl` | 197 objects incl. `text_snippet` (first 5,000 chars) | summary text, BM25 |
| `merged/merged_standards.json` | 24-field records incl. `is_compulsory`, `text_path`, `status` | QCO flag, supersession |
| `semantic/*.json` | `category_hierarchy`, `cross_references`, `domain_ontology`, `temporal_index`, `search_facets` | routing, expansion, filters |
| `index/search_index.json` | the pre-built TF-IDF index (4.86 MB) | sparse retrieval, reused verbatim |

`canonical` (`IS|302|2|15|2009|None`) is the join key across all of them.

Two traps beyond the key names:

- **`superseded_by` is a designation string, not an id.** `merger.resolve_editions`
  sets `superseded_by = newest.designation`, i.e. `"IS 456:2000"`, and
  `cross_references.supersession_chains` stores that string as a *value*. Joining
  on it as if it were a canonical id silently misses every time.
  `BisData.supersession()` re-parses it with `iscode.parse_designation` and
  resolves it to the canonical, and reports `in_dataset=False` when the
  replacement is not in the 197-standard subset.
- **`category_hierarchy.json` "categories" are not divisions.** They are
  hardcoded number ranges (`"Chemical (500-1000)"`, `"Textiles (100-500)"`) in
  `create_semantic_index.py` that do not correspond to BIS's real classification.
  `bis_rag` uses `divisions` and `committees` (which are real) and ignores
  `categories` entirely.

---

## 2. Running it

```bash
cd bis_scraper
export PYTHONPATH=src

# what do I have?
python -m bis_rag.cli doctor

# Part 1 — embed into a vector store
python -m bis_rag.cli build                      # uses bis_data/vector_store
python -m bis_rag.cli build --backend json       # no chromadb required

# Part 3 — hybrid search, with provenance
python -m bis_rag.cli search "water pipe for potable supplies"
python -m bis_rag.cli analyze "Is cement mandatory?"     # how the query was parsed

# Part 2 — grounded answer with citations
python -m bis_rag.cli ask "Has IS 456:1978 been superseded?"

# Part 4 — compliance check + printable gap report
python -m bis_rag.cli compliance "33 grade ordinary Portland cement" IS 269:1989 \
    --html gap_report.html
```

### On a machine with the real data (your Windows checkout)

```bat
cd bis_scraper
set PYTHONPATH=src
python -m bis_rag.cli doctor
python -m bis_rag.cli build --embedder hash --backend chroma
```

`bis_data/` is gitignored, so it is never in a fresh clone. Point at it
explicitly with `BIS_DATA_DIR` / `--data-dir` if it lives elsewhere.

Real semantic embeddings need either a local model or an API key:

```bash
# ~1.3 GB download, needs torch
pip install 'sentence-transformers>=2.7'
python -m bis_rag.cli build --embedder st:BAAI/bge-large-en-v1.5

# or an OpenAI-compatible embeddings endpoint
export EMBEDDING_API_KEY=...
python -m bis_rag.cli build --embedder api:text-embedding-3-small
```

### The honest note about the default embedder

If `sentence-transformers` is not installed, the default is a hashing embedder
that is **lexical, not semantic**. `bis-rag doctor` prints this, `build` prints
this, and every response carries the embedder name. "water pipe" will not match
"conduit for aqueous transport" — because it cannot. On a machine with the
model, `--embedder st:BAAI/bge-large-en-v1.5` is a drop-in change; the store
records a fingerprint of the embedder that built it and refuses to serve a query
from a different one (mixing model A's queries with model B's vectors returns
meaningless results that *look* plausible).

---

## 3. Architecture

```
bis_rag/
├── schema.py               the data contract; fails loudly on a broken dataset
├── data.py                 BisData: one object for all of bis_data/, lazy + cached
├── embeddings.py           hash / sentence-transformers / OpenAI-compatible + guard
├── vectorstore.py          ChromaDB and a portable JSON+NumPy backend
├── build_vector_store.py   Part 1: embed chunks + standards
├── query_processor.py      Part 2a: intent, designations, filters, expansion
├── bm25.py                 Part 3: Okapi BM25 + adapter for the prebuilt TF-IDF
├── hybrid.py               Part 3: RRF fusion, diversity, reranking, provenance
├── rag.py                  Part 2b: prompt, providers, citation verification
├── compliance.py           Part 4: QCO database, scoring, grades, HTML report
└── cli.py                  doctor / build / search / ask / compliance / analyze
```

### Retrieval

```
query ──> QueryProcessor ──> intent + filters + expansions
           │
           ├── BM25 over chunks (unexpanded query)
           ├── prebuilt TF-IDF over standards (unexpanded query)     ──> RRF ──> rerank ──> diversity ──> top-k
           └── dense over the vector store (expansions added)
```

**Why RRF.** The three retrievers produce incomparable scores (BM25 unbounded,
cosine in `[0,1]`, a cross-encoder a logit). Reciprocal rank fusion combines
*ranks*: `score = Σ weight_r / (60 + rank_r)`. A document found by all three
beats one that is rank 1 in a single retriever — agreement is evidence.

**Why two sparse retrievers.** BM25 (`b=0.75`) normalises for length and rewards
rare terms; the hashed TF-IDF cosine is length-blind and bigram-aware, so it
catches phrases BM25 splits. They fail differently, and fusion wants that. Both
use `bis_pipeline.index.tokenize`, so `IS-14220` and `IS/IEC 61730-1` survive
tokenisation.

**Expansions go to the dense leg only.** They come from
`domain_ontology.json` concepts, and a candidate term must appear in the titles
of **at least two** standards the concept points at. Without that test, asking
about *drinking water quality* pulled `unplasticized, pipes, tubes` in from a
single PVC-pipe standard, which then outranked the drinking water standard. That
regression is now a test (`test_expansion_requires_two_supporting_standards`).

### Ranking rules that encode domain knowledge

- **Exact designation wins.** If the query names `IS 1239:2004`, that standard is
  rank 1 — a vector index must not be allowed to argue with an exact code.
- **Superseded editions are filtered by default, but never for compliance or
  supersession questions.** A compliance checker that cannot retrieve the
  withdrawn edition cannot tell you that your product complies with a standard
  nobody uses any more.
- **For compliance, current editions rank above superseded ones** (both stay in
  the results). Otherwise a heavily-worded 1989 edition outranks its 2015
  replacement and the answer leads with the wrong edition.
- **Diversity cap** (`max_per_standard=3`): without it, four chunks of IS 10500
  fill the context window and the generator never sees the other standards.
- **A nonsense query returns nothing.** Because RRF fuses ranks, it has no way
  to notice that all candidates were equally irrelevant; a floor on dense
  similarity plus a lexical-support check for non-semantic embedders turns
  "least unrelated standard" into "no match", with an explanation.

---

## 4. Answers you can check

`bis-rag ask` returns `mode`, `generator`, citations, and any warning.

- **`mode="llm"`** — a model generated the prose. The provider is chosen from
  the environment: `GROQ_API_KEY` → Groq (`llama-3.3-70b-versatile` by default),
  `OPENAI_API_KEY` → OpenAI (or anything via `LLM_BASE_URL`), `OLLAMA_HOST` →
  local Ollama.
- **`mode="extractive"`** — no LLM configured. The answer is assembled from the
  retrieved passages, quotes them verbatim, and says so in `notes`. It is not a
  degraded imitation of an LLM; it is a different, verifiable thing.

**Citation verification.** Every generated answer is re-parsed with
`iscode.find_all` and each cited designation is checked against what was
actually retrieved. An answer citing `IS 9103:1999` when the context held
`IS 456:2000` comes back with `grounded: false` and
`unsupported_citations: ["IS 9103:1999"]`. Citing `IS 456` where the context
holds `IS 456:2000` is accepted (same standard, year omitted); citing
`IS 456:1978` against `IS 456:2000` is flagged as a wrong edition.

**Supersession.** If retrieval returns a superseded edition, the replacement is
injected into the prompt as a hard constraint *and* surfaced as a warning in the
response. A recommender that quietly returns a withdrawn standard is worse than
one that returns nothing.

---

## 5. Compliance checking (Part 4)

```bash
bis-rag compliance "submersible pumpset" IS 14220:2000 IS 302:2009 --html report.html
bis-rag compliance "ordinary portland cement"            # uses recommended standards
```

`compliance` scores the standards you are working to against the QCO
(compulsory-certification) list, and writes a printable HTML gap report.

### Where the mandatory list comes from

QCO status is created by government notification. A wrong or stale entry makes
the checker confidently wrong about a legal requirement, so the list is resolved
in tiers and the tier is reported on every result (`qco_source`, `qco_verified`):

| Tier | Source | Verified |
| ---- | ------ | -------- |
| 1 | `bis_data/mandatory/mandatory.json` — output of `python -m bis_pipeline mandatory`, scraped from BIS with per-entry `source_url` | yes |
| 2 | `is_compulsory` in `merged_standards.json` — the same scrape after a merge | yes |
| 3 | `SEED_QCO` in `compliance.py` — ~44 well-known product standards, hardcoded | **no** |

On tier 3 the report carries a banner and **cannot return a fully-compliant
grade**, because an incomplete list of mandatory standards cannot prove
completeness. It can still say "this standard is superseded" and "this known
mandatory standard is missing from your set", which is most of the value. Run
`python -m bis_pipeline mandatory` to replace the seed list with the real one.

Seed entries carry no notification years. A wrong year is worse than a missing
one, and the authoritative years live in the scrape, which records where they
came from.

### What the score means, and what it does not

```
score = 0.7 * (mandatory present / mandatory identified)
      + 0.2 * (current editions / supplied standards)
      + 0.1 * (no conflicts)
```

Two deliberate deviations from that formula:

- **Missing a mandatory standard caps the grade** at PARTIALLY COMPLIANT. A
  product needing IS 269 and IS 1786 that has only IS 1786 is not "50%
  compliant" in any sense a regulator would accept; compliance is a conjunction,
  not an average. The score is kept as a summary of remaining work, not as a
  verdict.
- **If no mandatory standard is identified**, the 0.7 term is removed and the
  weights are redistributed, with `weights_redistributed: true`. Scoring that
  case as 0/0 → 0.0 would grade an unclassified product NON-COMPLIANT, which
  claims something we cannot support: it means "no QCO row matches this", not
  "you fail".

### Guessing is a finding, so the checker refuses to guess

Three rules exist because each one caught a false "missing mandatory" claim
during development:

- **A sector list is not a product-specific requirement.** Treating every
  construction QCO as expected claimed a cement product was failing 15
  standards, including bricks (IS 1077) and flooring tiles (IS 6003). Sector
  entries are now `sector_candidates` — suggestions, never `mandatory_missing`.
- **An ambiguous description asserts nothing.** "ordinary portland cement" is
  IS 269 (33 grade), IS 8112 (43 grade) and IS 12269 (53 grade); the checker
  reports them as `mandatory_candidates` and asks you to disambiguate. Grade
  numbers survive tokenisation precisely so "53 grade" *does* resolve.
- **One shared word is not identification.** "electrical cable" shares exactly
  one token with "safety of household and similar electrical appliances", so
  IS 302 is offered rather than asserted (`MIN_PRODUCT_MATCH = 2`).

### Limits, stated in the report itself

Every report carries its `limitations`: this compares the standards you supplied
against the QCO list *this dataset* holds, it does not determine whether your
product needs certification, and a standard missing from the results may simply
not be indexed here (the corpus holds 197 of ~22,025 CC0 standards, and 481 of
BIS's 612 QCO-mandated standards). Absence of a warning is not legal advice.

The HTML report escapes all interpolated text — the product description is
caller-supplied and attacker-controlled in a web context.

## 6. Tests

```bash
cd bis_scraper && PYTHONPATH=src python -m pytest
```

168 new tests in `tests/test_rag_schema.py`, `tests/test_rag_retrieval.py`,
`tests/test_rag_compliance.py` and `tests/test_api.py`, all offline, running
against
`tests/synth_bis_data.py` — a miniature `bis_data/`
whose field names are copied from the real generators (a fixture using `text`
where the real file says `chunk` would make the tests pass while the real
pipeline fails).

The ones worth knowing about, because each encodes a bug that actually happened
during development:

| Test | Bug it prevents |
| ---- | --------------- |
| `test_empty_text_field_is_a_hard_error` | the silent empty-embedding build |
| `test_alias_is_accepted_but_reported` | a rename upstream going unnoticed |
| `test_chunk_metadata_keeps_native_types` | `{"year": {"$gte": 2010}}` matching nothing because years were stringified |
| `test_querying_with_a_different_embedder_raises` | scoring BGE queries against hash vectors |
| `test_expansion_requires_two_supporting_standards` | one odd standard hijacking the query |
| `test_fusion_rewards_agreement` | RRF silently regressing to single-retriever ranking |
| `test_verify_citations_rejects_an_invented_standard` | hallucinated IS numbers presented as sourced |
| `test_diversity_cap_limits_repeats_of_one_standard` | five chunks of the same standard filling the results |
| `test_empty_result_set_says_so_rather_than_guessing` | a nonsense query returning a confident answer |
| `test_missing_mandatory_caps_the_grade` | a "67% compliant" verdict for a product missing a mandatory standard |
| `test_seed_data_cannot_claim_full_compliance` | an unverified QCO list proving compliance |
| `test_sector_entries_are_suggestions_not_missing_mandatory` | 15 false failures from a sector list |
| `test_ambiguous_product_description_asserts_nothing` | guessing one cement grade out of three |
| `test_dedupe_keeps_distinct_editions_so_conflicts_still_surface` | deduping away the very conflict it must find |
| `test_service_boots_without_data_and_says_what_is_missing` | a missing `bis_data/` turning into an undebuggable crash loop |
| `test_builtin_extractor_is_not_fooled_by_et_inside_a_word` | `BT.*?ET` stopping at the "ET" in "SHEET"/"CONCRETE" |

---

## 7. What is not built yet

Parts 4 and 5 are done; 6 and the evaluation remain, and nothing here pretends
otherwise:

- **Part 4 — compliance checker.** Built (section 5). The remaining gap is data,
  not code: the QCO list is incomplete by construction until
  `python -m bis_pipeline mandatory` is run, and 131 of BIS's 612 QCO-mandated
  standards require registration at bis.gov.in to obtain (see
  `docs/CORRECTIONS.md` and `coverage`).
- **Part 5 — FastAPI backend.** Built (`bis_api`, see `docs/API.md`). Two
  deliberate deviations, both reported: the service **boots degraded instead of
  crash-looping** when `bis_data/` is missing, and `/search` uses the full hybrid
  retriever rather than literally BM25-only — the brief's constraint was "no LLM,
  under 500 ms", and the measured time is 12–40 ms.
- **Part 6 — Next.js frontend.** Not started.
- **RAGAS evaluation.** Not started, and it should not start with
  `qa_pairs.jsonl`. Those 985 pairs are generated from templates like
  `"What is {designation}?"` with the title as the answer, so every one is
  answerable by a designation lookup — a lookup table passes all of them, and
  they measure nothing about retrieval. They remain useful as a smoke test of
  the loader and parser.

  What replaced them is `bis_rag.evaluate` (section 8): 56 hand-written cases in
  `eval/retrieval_cases.jsonl`, and the metrics that follow from them. RAGAS
  would add answer-faithfulness scoring on top, but it needs an LLM key and a
  question set with real ground truth, which is what `eval/` now provides.

---

## 8. Evaluating retrieval (Part 7)

```bash
python -m bis_rag eval --baseline
```

56 hand-written cases, each a query in the language a person actually uses plus
the standard that answers it. Metrics: Hit Rate @1/@3/@5/@10, MRR @5 and @10,
hallucination rate, superseded-violation rate, and latency P50/P95/P99, broken
out by difficulty so the keyword-free questions cannot be averaged away.
`--baseline` re-runs the same cases against BM25-only, because a hit rate on its
own does not say whether the semantic and reranking machinery is doing anything.

Exit code 1 on a threshold breach, so it works as a CI gate. The superseded rate
is hard zero by default.

Full methodology, including the two ways this measurement was wrong before it was
right, in [`eval/README.md`](../eval/README.md). The short version: the first
supersession check reported a 50% violation rate on a run where the current
edition was ranked first in every case, and a hit rate on a 12-standard corpus
proves nothing — which `--baseline` says out loud.

### Supersession policy (three modes, not one filter)

`HybridSearch.search(..., mode=...)` decides what may be *recommended*, which is
a different question from what may be retrieved:

| mode | withdrawn editions |
|---|---|
| `recommend` | withheld from the ranked results entirely, returned separately in `response.superseded` with `superseded_by` named |
| `search` | may appear, never above their own current edition, never without a named replacement |
| `history` | the user asked for the old edition; nothing is demoted |

The mode defaults from the intent (`SUPERSESSION` → history, `COMPLIANCE` /
`LATEST` / `LIST_BY_DOMAIN` → recommend, everything else → search) and the
recommend and compliance endpoints pass it explicitly. A query that names a
designation is exempt from the recommend policy: someone who typed "IS 269:1989"
asked for that edition, and silently substituting the current one would be a
worse failure than the one the policy prevents.

### Years, and why a sentinel is worse than a missing value

The TF-IDF leg used to write `"year": -1` for every candidate because the index
did not carry years. That failed `$gte` filters — silently removing a whole
retriever from every "standards since 2000" query — and *passed* `$lte` ones,
offering a 2015 standard as a 1980s edition. `year` is now the real year from
the index (`bis_pipeline.index` records it) with a fallback to `bis_data` for
indexes built before the change, and *unknown* is `None`, which fails both
directions. Year filters are exercised independently for the TF-IDF, BM25 and
dense legs.

### Query coverage is reported, not gated

`HybridSearch._query_coverage` measures the IDF-weighted share of a query's
keywords found in the best candidate, and `min_query_coverage` can decline
anything below it. The default is **0.0 (off)**, and that is a measurement
rather than caution: a floor of 0.15 separates all twelve out-of-scope queries
from nine of ten answerable ones on the fixture, and then declines "Is cement
covered under mandatory BIS certification?" — a legitimate compliance question
that shares one word with the right standard and four with the vocabulary of
compliance. A threshold that cannot tell those apart is measuring how many of a
query's words appear in one short document. It is exposed, reported, and off.
