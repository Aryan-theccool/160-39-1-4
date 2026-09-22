# Retrieval evaluation

> **SYNTHETIC FIXTURE -- NOT PRODUCTION ACCURACY.**
>
> corpus: `/home/user/demo_data/bis_data` (12 standards).
> These figures describe this corpus. They say nothing about the
> 197-standard dataset, and must not be quoted as its accuracy.

- generated: 2026-09-17 21:03 UTC
- cases: `/home/user/landing-page/bis_scraper/eval/retrieval_cases.jsonl`
- retriever: `bm25+tfidf+dense -> lexical (coverage + designation)`
- retrieval samples: 68
- end-to-end RAG samples: 56

## Report

```
Retrieval evaluation
  corpus provenance     SYNTHETIC FIXTURE
  cases                 68   (scored 56, out-of-scope 12)
  corpus                12 standards, 47 chunks
  reranker              bm25+tfidf+dense -> lexical (coverage + designation)
  top_k                 10   (repeats 1)

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  FIXTURE DATA -- these numbers describe the test corpus, not the
  197-standard dataset. They are not production accuracy.
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

Coverage
  scored cases          56
  covered (answerable)  10/56  (17.9%)
  out-of-scope cases    12   (reported separately below)
  standards not held    45 distinct  (affecting 46 case(s))
                        a retriever cannot return a standard the corpus lacks,
                        so every rate below is given twice: covered-only,
                        and end-to-end (which counts these as misses)

Ranking
                       covered     end-to-end
  Hit Rate @1           100.0%      17.9%
  Hit Rate @3           100.0%      17.9%
  Hit Rate @5           100.0%      17.9%
  Hit Rate @10          100.0%      17.9%
  MRR @5               1.0000      0.1786
  MRR @10              1.0000      0.1786
  exact edition         100.0%      (current edition, not just the right number)

Correctness of what was emitted
  Invalid citation rate  0.0%   (0 of 116 citations, mode: extractive)
                        (invalid citation rate in extractive mode)
                        NOTE: extractive mode quotes retrieved text, so this
                        is 0 by construction here. It only measures the model
                        when an LLM is configured (BIS_RAG_LLM).
  Superseded-first       0.0%   (0 of 10 cases; target 0%)
                        a withdrawn edition ranking ABOVE its own current
                        edition, or appearing with the current one absent
                        from the window. Measured with the current-only
                        filter disabled, so this scores the ranking rather
                        than the filter the API applies before a user sees it
  Superseded exposure    0.0%   (0 of 10 cases in recommend mode; target 0%)
                        a withdrawn edition reaching the ranked
                        recommendations. Separate from the ordering metric
                        above: that one asks how it was ranked, this one
                        asks whether it was offered at all.
                        informational: withdrawn editions were retrieved
                        in 3 case(s) but ranked below their
                        current edition -- IS 10500:1991, IS 269:1989, IS 456:1978

Out-of-scope queries  (expected = [])
  cases                 12
  declined (correct)    9/12   (75.0%)
  best raw score        0.0339   (strongest an unrelated query scored)
  weakest real hit      0.0185   (weakest top score among covered cases)
                        the two sets overlap, so no score floor can
                        separate them: relevance on this corpus is a
                        ranking signal, not a confidence one
    not declined: neg-company-registration -> IS 1:1968, IS 1:1968
    not declined: neg-cricket          -> IS 269:2015
    not declined: neg-cover-letter     -> IS 1:1968, IS 383:2016

Latency (per query, ms)
                        samples  P50     P95     P99
  retrieval             68       14.7    17.1    19.2
  end-to-end RAG        56       13.2    15.7    16.8
                        a P99 from 68 samples is ~the second-worst observation;
                        use --repeats for a tail figure worth quoting

Retrieval stages (ms)
                        where the time inside `retrieval` above goes
  stage               P50      P95      P99
  query_processing    0.100    0.175    0.216
  sparse              0.279    0.449    0.597
  dense               12.377   15.327   16.071
  fusion              0.053    0.111    0.146
  rerank              1.032    2.432    2.937
  total               14.668   17.109   19.164
                        measured where each stage runs, not derived
                        from the total

End-to-end RAG latency (ms) -- retrieval plus generation
  samples 56   P50 13.21   P95 15.65   P99 16.77

By difficulty  (does it work when the question has no keywords in it?)
  easy     n=5    Hit@1 100.0%   Hit@5 100.0%   MRR@5 1.000
  medium   n=4    Hit@1 100.0%   Hit@5 100.0%   MRR@5 1.000
  hard     n=1    Hit@1 100.0%   Hit@5 100.0%   MRR@5 1.000

By sector
  Electrical & Electronics n=14   covered 0    Hit@5 0.0%     MRR@5 0.000
  Cement & Concrete      n=13   covered 4    Hit@5 30.8%    MRR@5 0.308
  Structural Steel       n=13   covered 3    Hit@5 23.1%    MRR@5 0.231
  Water & Sanitation     n=10   covered 3    Hit@5 30.0%    MRR@5 0.300
  Masonry                n=3    covered 0    Hit@5 0.0%     MRR@5 0.000  (n<10: one case moves this)
  Plumbing & Sanitation  n=3    covered 0    Hit@5 0.0%     MRR@5 0.000  (n<10: one case moves this)

Standards the corpus does not hold (45)  -- what to scrape next
  IS 458         costs 2 case(s): proc-precast-pipes, proc-rcc-hume-pipe
  IS 10262       costs 1 case(s): proc-mix-design
  IS 10322       costs 1 case(s): proc-luminaire
  IS 1077        costs 1 case(s): proc-bricks
  IS 12269       costs 1 case(s): proc-cement-53
  ... and 40 more; see missing_corpus_standards.json

note: first search excluded from latency as a warm-up
note: cases file: /home/user/landing-page/bis_scraper/eval/retrieval_cases.jsonl
note: optional input absent: mandatory (mandatory.json) -- this does not affect retrieval, but it does affect features that use it
```

## Ablation

| config | Hit@1 | Hit@5 | MRR@5 | exact edition | hard Hit@5 | P50 ms | P95 ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `tfidf_only` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.2 | 0.38 |
| `bm25_only` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.5 | 1.11 |
| `dense_only` | 0.9000 | 0.9000 | 0.9000 | 0.9000 | 0.0000 | 12.53 | 16.03 |
| `bm25_dense` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 13.31 | 18.66 |
| `bm25_dense_rrf` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 13.77 | 19.0 |
| `bm25_dense_rrf_rerank` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 15.81 | 20.05 |

End-to-end hit rates (`hit@*_end_to_end` in `ablation.csv`) count cases whose standard the corpus does not hold as misses; the columns above are covered-only.

## Targets versus measurements

| metric | target | measured | status |
| --- | --- | --- | --- |
| superseded-first violation rate | 0 | 0.0000 | met |
| superseded exposure in recommend mode | 0 | 0.0000 | met |
| out-of-scope rejection accuracy | 1 | 0.7500 | MISSED |
| invalid citation rate (extractive) | 0 | 0.0000 | met |

A target is a commitment; a measurement is an observation about one corpus. The two supersession targets are hard zero and are gated in CI. The hit rates are not targets -- there is no agreed number for a corpus this size, and picking one would invent an expectation.
