# Retrieval evaluation

The project has two question sets. Only one of them measures retrieval.

| | `qa_pairs.jsonl` (985 pairs) | `eval/retrieval_cases.jsonl` (56 cases) |
|---|---|---|
| Origin | generated from templates over the dataset | written by hand |
| Example | `Q: "What is IS 269:2015?"` `A: "Ordinary Portland Cement"` | `Q: "I need to procure cement for a highway construction project"` |
| Answerable without retrieval | **every one** — the designation is in the question | none |
| Measures | that designation lookup works | whether natural language finds the right standard |

The 985 pairs are still worth keeping as a smoke test. They prove the loader, the
designation parser and the ontology join work end to end, and they do it in
seconds. They cannot fail in a way that tells you anything about search quality,
because a lookup table passes them.

```bash
cd bis_scraper && export PYTHONPATH=src

python -m bis_rag eval                                    # the shipped 56 cases
python -m bis_rag eval --baseline                         # + BM25-only comparison
python -m bis_rag eval --repeats 20                       # enough samples for a P99
python -m bis_rag eval --min-hit-rate-5 0.8 --json        # CI gate
```

Exit code is 1 when a threshold fails, so this drops straight into CI. The
superseded-violation threshold defaults to **0** and is not meant to be raised:
pointing a user at a withdrawn edition of a standard is the worst answer this
system can give, and it is never a good trade for a higher hit rate.

---

## How the 56 cases were written

Each one is a query in the language a person actually uses, plus the standard(s)
that answer it. They were written against known BIS standards, not sampled from
the dataset — sampling from the corpus is how you end up testing the corpus
against itself.

- **22 easy** — near-exact product names (`"ordinary portland cement 33 grade"`).
  These should be near-perfect; if they are not, something is badly broken.
- **26 medium** — procurement phrasing (`"I need to procure cement for a highway
  construction project"`), trade names that do not appear in the titles (`"TMT
  bars"` → IS 1786, "hume pipes" → IS 458, "paver blocks" → IS 15658), and
  near-miss distractors (heavy-duty PVC cable is IS 1554, not IS 694).
- **8 hard** — no domain keywords at all. `"my borewell water tastes salty and
  nobody knows what is safe to drink"` → IS 10500. `"we keep getting electric
  shocks from bathroom fittings"` → IS 12640. These are the cases that separate
  semantic retrieval from a keyword index, and the report breaks the metrics out
  by difficulty so the difference is visible rather than averaged away.

`expected` is a list, and any listed standard counts as a hit. For a few products
more than one standard is a defensible answer — which OPC grade applies to a
highway is a mix-design decision, not a standards one — and forcing a single
answer would score correct retrievals as misses.

A test in `tests/test_rag_evaluate.py` asserts that no case names the standard it
is looking for, so the set cannot drift back into the trap the old pairs fell
into.

---

## What each metric means

**Coverage, reported first.** A case whose expected standard is not in the corpus
is excluded from every rate and listed as a gap. A retriever cannot return an
answer the corpus does not contain, and counting those as misses measures the
dataset while looking like it measures the search. On a QCO-only corpus this
number is genuinely informative: it tells you which sectors you can and cannot
answer questions about.

**Hit Rate @k** — of the answerable cases, how many put a correct standard in the
top k. `@1` is what a user who reads only the first result experiences; `@5` is
what someone scanning the page gets.

**MRR @k** — mean reciprocal rank of the first correct hit. This is the metric
that distinguishes "usually right" from "right, but ranked third", which hit rate
at k hides entirely.

**Hallucination rate** — citations that do not resolve to a standard in the
corpus. Note the asymmetry, which the report prints rather than hiding: on the
search path this is structurally zero, because search returns corpus rows by
definition, and in `extractive` answer mode it is zero by construction too, since
the answer quotes retrieved text. **A zero here is only evidence about the model
when an LLM is configured** (`BIS_RAG_LLM`). The report says which mode ran.

**Superseded violation rate** — a withdrawn edition outranking the current
edition of the same standard. See below.

**Latency P50/P95/P99**, with the sample count printed next to it. A P99 from 56
samples is approximately the second-worst observation; use `--repeats` before
quoting a tail figure. The first search of a run is excluded as a warm-up,
because it builds the BM25 indexes and would otherwise put a startup cost into
the tail of a per-query distribution.

---

## Two things this measurement got wrong before it got them right

Both are worth recording, because both produced a confident number that was
false, and a benchmark that lies is worse than no benchmark.

**The supersession check flagged correct behaviour.** The first version counted
any withdrawn edition appearing in the top results. On the first run it reported
a **50% violation rate** — on a run where the current edition was ranked *first*
in every single case. A withdrawn edition at rank 4, under its own current
edition at rank 1, is correctly ranked; nobody reading the top result is misled.

The definition is now about ordering: a violation is a withdrawn edition
*outranking* its current edition, or appearing with the current edition absent
from the window. Measuring the ordering rather than the filter is deliberate —
the API filters withdrawn editions out before a user sees them, so measuring with
that filter on would score the filter.

The corrected check then found a **real** defect, which is the point:

> For `"coarse and fine aggregate grading requirements for concrete"`,
> `IS 456:1978` came back at rank 5 and its current edition `IS 456:2000` at
> rank 7. The ranking has no notion of which edition is in force, and the
> existing soft "prefer current" multiplier (1.15x) was not enough to close a
> relevance gap that large. Fixed in `HybridSearch._current_edition_first`.

The first fix for that was also wrong: it swapped *adjacent* pairs, on the
assumption that two editions of one standard come back next to each other. They
did not — an unrelated standard sat between them — so the fix silently did
nothing and the test caught it.

**A hit rate on its own proves nothing.** On the 12-standard development fixture,
the full pipeline and a BM25-only baseline both score 100%, because with twelve
standards a keyword search finds everything. `--baseline` runs the degraded
retriever over the same cases and reports the delta, and prints a warning when
the full pipeline is not ahead. That warning is the honest answer to "is 100%
good?" — on that fixture, it means nothing at all.

---

## Where RAGAS fits, and where it does not

The preferred harness for this was:

```python
# pip install ragas datasets
from ragas import evaluate
from ragas.metrics import (
    context_precision, context_recall, faithfulness, answer_relevancy,
)
evaluate(dataset, metrics=[context_precision, context_recall, faithfulness, answer_relevancy])
```

That is the RAGAS **v0.1** API. Three things have to be true for it to run, and
only one of them is about this repository.

**It needs a judge LLM.** Every metric above is LLM-as-judge — faithfulness
decomposes the answer into atomic claims and checks each against the context;
context precision and recall ask the judge whether retrieved chunks are relevant
and sufficient; the "context precision" of a chunk is never computed from the
ranking itself. The `evaluate` signature accepts an `llm` and an `embeddings`;
passing neither means RAGAS constructs its own, which defaults to OpenAI. There
is no key-free mode in the package. `answer_relevancy` additionally needs an
**embeddings** model on top of the judge.

**It needs columns this pipeline does not produce on the search path.** RAGAS
is built for a full RAG *answer*, not for retrieval. In v0.2+ each metric
declares required fields: `faithfulness` wants `user_input`, `response`,
`retrieved_contexts`; `context_precision` and `context_recall` want those plus
`reference`; `answer_relevancy` wants `user_input` and `response`. The
evaluation above measures the ranking the search endpoint returns, and a search
result has no `response` — so a RAGAS dataset would have to be built by calling
`RAGPipeline.answer` too. That is available and tested, but it is a different
measurement of a different object.

**The v0.1 metric names no longer exist as written.** In 0.2+ they are classes
instantiated with their model — `Faithfulness()`,
`ResponseRelevancy(llm=..., embeddings=...)`,
`LLMContextPrecisionWithReference()`, `LLMContextRecall()` — and in 0.4
`evaluate()` itself is deprecated in favour of the `@experiment()` decorator.

### What is deliberately not built here

`bis_rag.evaluate` computes the metrics that have a ground truth or a
definition, and no metrics that need a judge:

| RAGAS metric | Here | Why |
|---|---|---|
| `context_recall` | **Hit Rate @k, MRR** | "did retrieval find the needed document" is answerable exactly, because the ground truth is a standard, not an answer string |
| `context_precision` | **superseded violation rate** | ranking quality with a domain-specific definition of "bad result" that a general judge would not know: a withdrawn edition outranking its current edition |
| `faithfulness` | **hallucination rate** | deterministic under `extractive`; a judge is needed only when `BIS_RAG_LLM` is set |
| `answer_relevancy` | — | genuinely not measurable without a judge or an embeddings model, and not measured here |

That is the honest split. The four RAGAS metrics on 56 questions with a small
judge model would be noisy, cost real tokens, and — for a system whose current
answer mode is extractive — measure the template more than the retrieval. The
deterministic metrics run in three seconds, in CI, with no key and no network,
and they caught two real bugs (above), which is more than a judge metric would
have done at this stage.

### Running RAGAS anyway

On a machine with a key, the cases in `eval/retrieval_cases.jsonl` are exactly
the dataset RAGAS wants — they just need a `response` and `retrieved_contexts`
per row, which the pipeline produces:

```python
# The dataset construction below was executed against the fixture and populates
# all four RAGAS columns. The evaluate() call was NOT: it needs an LLM key and
# the ragas/langchain stack, neither of which exists in this environment. Treat
# the metric names and arguments as a starting point, not as verified.
from ragas import EvaluationDataset, SingleTurnSample, evaluate
from ragas.metrics import Faithfulness, ResponseRelevancy, LLMContextRecall
from ragas.llms import LangchainLLMWrapper
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from bis_rag.data import BisData
from bis_rag.hybrid import HybridSearch
from bis_rag.rag import RAGPipeline
from bis_rag.evaluate import load_cases

data = BisData("bis_data")
search = HybridSearch(data, store_dir="chroma_bis_db", reranker="lexical")
pipe = RAGPipeline(data, search)

samples = []
for case in load_cases("eval/retrieval_cases.jsonl"):
    answer = pipe.answer(case.query, top_k=5)
    samples.append(SingleTurnSample(
        user_input=case.query,
        response=answer.answer,
        # RAGAnswer carries the search it was built from, so the contexts and
        # the answer come from one retrieval rather than two runs.
        retrieved_contexts=[r.text for r in answer.search.results],
        reference="; ".join(case.expected),   # v0.4 name; ground_truths in v0.3
    ))

judge = LangchainLLMWrapper(ChatOpenAI(model="gpt-4o-mini", temperature=0))
embeddings = LangchainEmbeddingsWrapper(OpenAIEmbeddings())

result = evaluate(
    dataset=EvaluationDataset(samples=samples),
    metrics=[
        Faithfulness(llm=judge),
        ResponseRelevancy(llm=judge, embeddings=embeddings),
        LLMContextRecall(llm=judge),
    ],
)
print(result)
```

Two caveats worth carrying into that run. Use the **same 56 cases**, so the
judge numbers and the deterministic numbers in this directory describe one
system rather than two. And read `faithfulness` as a property of the *prompt and
context assembly*, not of the corpus — under `extractive` it is 0 by
construction, so a low score there is telling you the template leaked text
outside its citations, not that the model invented a standard.

---

---

## Production validation

Two commands answer "is this real?" and "where does the time go?".

```bash
python -m bis_rag doctor                     # what data is this, exactly?
python -m bis_rag eval --production --ablation
```

### Refusing to certify a fixture

`doctor` prints a `PROVENANCE` line and the evaluator refuses to be quoted as
production accuracy when the corpus is not real:

```
  PROVENANCE : SYNTHETIC FIXTURE  <- NOT PRODUCTION DATA
  fixture marker: .../bis_data/.synthetic_fixture.json
  generated by  : tests/synth_bis_data.py
```

`doctor` itself exits **2** when there is no corpus at all, because "no fixture
found" must not read as "real data found" -- it printed the same provenance line
either way, and a CI step chained with `&&` sailed past a missing directory.

`make_synth_data` writes `.synthetic_fixture.json` into the tree it generates, so
a fixture identifies itself rather than relying on someone remembering. Two
conditions make a corpus certifiable — no marker, **and** at least
`MIN_PRODUCTION_STANDARDS` (50) standards — because an old fixture with no marker
is still twelve hand-picked standards, and a partial scrape is not the corpus
either. `--production` turns either finding into exit code 2 instead of a number
someone might quote.

This matters more than it sounds. A hit rate over a corpus chosen to contain the
answers is not evidence about the retriever, and it looks exactly like one.

### Covered-only and end-to-end

Every ranking metric is reported twice:

| | denominator | what it answers |
|---|---|---|
| covered-only | cases whose expected standard **is** in the corpus | is the ranking working? |
| end-to-end | every scored case, missing standards counted as misses | what does a user experience? |

The gap between them *is* the coverage gap. On the fixture that is `100.0%`
against `17.9%`, which is a statement about a twelve-standard corpus, not about
search. `missing_corpus_standards.json` names each absent standard and the case
ids that wanted it, so the next scrape can be aimed.

### Ablation

Six configurations, one component apart, so a delta is attributable:

```bash
python -m bis_rag eval --ablation          # prints the table, writes ablation.csv
```

`dense_only` on a `hash` embedder loses every keyword-free case. That is the
embedder rather than the vectors — a lexical hashing embedder matches words, not
meaning — and the table says so instead of leaving a zero to be misread.

### Latency, per stage

`retrieval` and `end-to-end RAG` are reported separately, and retrieval is split
into `query_processing`, `sparse`, `dense`, `fusion`, `rerank`. The stages are
timed where they run rather than reconstructed from the total, so "the dense leg
is the slow one" is an observation. A `P99` from 50 samples is roughly the
second-worst observation and the report says so every time.

### Out-of-scope queries

Twelve cases whose `expected` is `[]` — company registration, a flight price, a
cricket result. They are excluded from every ranking denominator (there is no
rank to be right about) and scored separately as *rejection accuracy*.

Measured, this is the least comfortable number in the report, and it is here on
purpose. On the fixture the retriever declines 9 of 12. The three it answers are
answered **confidently**: "how do I register a private limited company in india"
returns the National Flag standard, because BM25 has no score floor and "india"
appears in it, scoring 7.9 — higher than genuine matches score. The report prints
the term that matched, the best raw score an unrelated query achieved, and the
weakest score a covered case achieved, so the overlap is visible rather than
implied. On the fixture those ranges overlap (0.034 against 0.019), which is the
honest way of saying: **relevance here is a ranking signal, not a confidence
one.**

### Artifacts

`eval/results/`, written by every run unless `--no-artifacts`:

| file | contents |
|---|---|
| `latest.json` | the full report: metrics, per-case detail, provenance, ablation |
| `latest.md` | the same for a reader, fixture warning at the top |
| `failures.jsonl` | every case that fell short, with *why* — `standard_not_in_corpus` is a coverage gap, not a ranking miss |
| `missing_corpus_standards.json` | absent standards and the case ids each one costs |
| `ablation.csv` | one row per retriever configuration |

`latest.md` carries a targets-versus-measurements table, because a target is a
commitment and a measurement is an observation about one corpus, and the two
should not be read off the same list.

The directory is committed so the artifact contract is visible without running
anything. The committed copy is a **fixture** run and says so at the top; it is
there to show the shape of the output, not as a result. Point `--data-dir` at the
real corpus and re-run to replace it.

---

## Reading the report honestly

The numbers in this repository's own runs come from a **12-standard synthetic
fixture**, not the 197-standard corpus. On that fixture coverage is ~18%, so most
cases are unanswerable and the headline rates rest on ten cases. They validate
that the harness works. They are not a measurement of retrieval quality, and the
report says so:

```
Coverage
  answerable            10/56  (17.9%)
  absent from corpus    IS 10262, IS 10322, IS 1077, ...
```

Run it against the real `bis_data/` before quoting any of these figures. That is
the number that matters, and it is the one number this repository cannot produce
on its own, because the corpus is not in it.
