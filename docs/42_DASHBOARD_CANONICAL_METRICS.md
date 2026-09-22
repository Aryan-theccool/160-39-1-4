# docs/42_DASHBOARD_CANONICAL_METRICS.md
# Dashboard Canonical Metrics — Authoritative Reference
# SIH-108 — BIS Standards AI

**Created:** 2026-09-22  
**Status:** AUTHORITATIVE — do not modify without re-running `scratch/reconcile_populations.py`  
**Source audit:** `docs/41_DATA_POPULATION_RECONCILIATION_AUDIT.md`

---

## Purpose

This document defines the canonical, presentation-safe numbers used by the
Dashboard UI and explains why they differ from the raw internal backend counts.
It is intended for SIH judges, evaluators, and engineers who may notice the
discrepancy between what the dashboard shows and what the backend health
endpoint reports in its internal diagnostics.

---

## Canonical Values (User-Facing Dashboard)

| Metric | Canonical Value | Dashboard Card Label |
|--------|-----------------|----------------------|
| Unique curated BIS standards | **500** | "Standards in RAG Corpus" |
| Active retrieval chunks | **19,853** | "Active Retrieval Chunks" |
| Clean normalized BIS divisions | **15** | "BIS Divisions" |
| Gazette-verified QCO mappings | **33** | "Verified QCO Mappings" |
| QCO total candidates | **44** | (shown in card subtext) |

---

## Internal Backend Values (Diagnostic Only)

These values are visible in the collapsible "Internal diagnostics" section of
the dashboard and in the `/api/v1/health` JSON response. They are **not**
presented as primary metrics.

| Internal Count | Value | Why It Differs |
|---------------|-------|----------------|
| In-memory standard records | **953** | `BisData.standards()` performs a 3-way merge of `knowledge_base`, `search_corpus`, and `merged_standards`. Entries without canonical IDs prevent 1-to-1 matching, yielding duplicate representations. |
| Raw division strings | **70** | Raw scraped strings include HTML tags, entity codes, `<br>` noise, and archive description artifacts. Before `cleanDivisionName()` is applied, 70 distinct strings exist. After cleaning, 15 unique divisions remain. |
| Raw stored chunk lines | **19,871** | Chunk JSONL file contains 19,871 lines. `load_chunks()` applies `MIN_CHUNK_CHARS=40` to strip OCR artifacts and page furniture. 18 chunks are filtered out, yielding 19,853 active retrieval chunks. |
| Chroma chunk vectors | **19,871** | Vector index stores all 19,871 raw chunks without applying the `MIN_CHUNK_CHARS` filter. The retrieval pipeline applies the filter at query time. |
| `is_compulsory` flags | **0** | Count of `is_compulsory=True` across the 953 in-memory records. This is a per-record flag, not the QCO catalog count. It shows 0 because the corpus flags have not been back-propagated from the QCO layer into the standard records. |
| QCO catalog candidates | **44** | Total entries in the QCO database (seed + verified). |
| Gazette-verified QCO entries | **33** | Entries with `evidence_state == "VERIFIED"` (cross-referenced with official BIS Gazette notifications). |

---

## Data Source Traceability

### Standards: 500 vs 953

**Canonical (500):** Derived from `GET /api/v1/standards?current_only=false&limit=500`.
The API caps limit at 500 matching the physical unique standards corpus. This is
the number a user would see browsing the Standards Catalog.

**Internal (953):** Derived from `BisData.standards()` in
`bis_scraper/src/bis_rag/data.py`. This method merges three data sources:

```python
# Approximate deduplication logic in BisData.standards()
from_kb = self._load("knowledge_base")       # source A
from_sc = self._load("search_corpus")        # source B
from_ms = self._load("merged_standards")     # source C
all_standards = dedupe_standards(from_kb + from_sc + from_ms)
```

`dedupe_standards()` in `bis_scraper/src/bis_rag/schema.py` deduplicates by
canonical ID, but `knowledge_base.json` entries lack a `canonical` field,
preventing 1-to-1 matching. This leaves 953 records in memory instead of 500.

### Divisions: 15 vs 70

**Canonical (15):** Derived from `byDivision.length` on the dashboard, where
`byDivision` is computed by:

```typescript
// bis_web/src/app/dashboard/page.tsx
const byDivision = countBy(rows, (row) => cleanDivisionName(row.division))
  .filter(entry => entry.label && entry.label.toLowerCase() !== "unclassified");
```

`cleanDivisionName()` in `bis_web/src/lib/format.ts` strips HTML tags,
decodes entities, and normalizes whitespace. After normalization, 15 unique
BIS engineering divisions remain.

**Internal (70):** Derived from `BisData.divisions()` in `data.py`:

```python
def divisions(self) -> list[str]:
    return sorted({s.division for s in self.standards() if s.division})
```

This returns raw uncleaned strings. Among the 70 raw strings, many are
different representations of the same division (e.g., `"Civil Engineering"`,
`"Civil Engineering<br/> (CED)"`, `"Civil Engineering Section Name: ..."`).
After `cleanDivisionName()`, these collapse to a single `"Civil Engineering"`.

### Chunks: 19,853 vs 19,871

**Canonical (19,853):** Active retrieval chunks returned by `load_chunks()` in
`bis_scraper/src/bis_rag/schema.py` after applying `MIN_CHUNK_CHARS=40`.

**Internal (19,871):** Total raw chunk lines in the chunks JSONL file (also
the number of vectors in the Chroma index). The 18-chunk difference represents
OCR artifacts and page furniture shorter than 40 characters that are filtered
at retrieval time.

### QCO: 33 vs 0

**Canonical (33):** `service.qco.verified_count` — entries where
`evidence_state == "VERIFIED"`, cross-referenced with official BIS Gazette
notifications. These are the 33 Gazette-confirmed mandatory standard mappings.

**Internal (0):** `service.corpus.compulsory` — count of `is_compulsory=True`
flags on the 953 in-memory standard records. This flag has not been
back-propagated from the QCO catalog into the corpus records, so it reads 0
even though 33 verified QCO mappings exist. This is a known data pipeline gap
(see `docs/41_DATA_POPULATION_RECONCILIATION_AUDIT.md`, §7).

---

## Dashboard Implementation Notes

### Card 1 — Standards in RAG Corpus

```tsx
// Source: standardsState.data?.total ?? 0
// API: GET /api/v1/standards?current_only=false&limit=500
// Returns: StandardsPage.total = 500
value={formatNumber(standardsState.data?.total ?? 0)}
```

### Card 2 — BIS Divisions

```tsx
// Source: byDivision.length (computed client-side)
// byDivision = countBy(rows, row => cleanDivisionName(row.division))
//              .filter(entry => entry.label && ...)
// Result: 15 clean divisions
value={formatNumber(byDivision.length)}
```

### Card 3 — Verified QCO Mappings

```tsx
// Source: service.qco.verified_count (added to Health interface)
// Falls back to service.qco.entries if backend does not send verified_count
value={formatNumber(service.qco.verified_count ?? service.qco.entries)}
```

### Card 4 — Active Retrieval Chunks (wide card)

```tsx
// Source: service.corpus.chunks
// Already filtered by MIN_CHUNK_CHARS=40 at the backend
value={formatNumber(service.corpus.chunks)}  // 19,853
```

### Division Chart Consistency

The division chart uses `byDivision` (the same cleaned dataset as the card):

```
Dashboard card:     "BIS DIVISIONS — 15"
Chart badge:        "Top 8 of 15 divisions"
Top 12 button:      (shows 12 of 15 when >12 divisions)
View all button:    "View all (15)"
```

This is internally consistent. The raw 70-string count never appears in the
division chart. `cleanDivisionName()` is the sole normalization function applied.

---

## Verification Checklist

After any dashboard change, verify:

```
[ ] Standards card = 500
[ ] Active Retrieval Chunks card = 19,853
[ ] BIS Divisions card = 15
[ ] QCO card label = "Verified QCO Mappings"
[ ] QCO card value = 33 (or matches qco.verified_count from /health)
[ ] Division chart badge says "Top 8 of 15 divisions"
[ ] Top 12 filter works
[ ] View all shows 15 divisions
[ ] No HTML strings appear in division labels
[ ] No malformed division labels (containing <, >, &, "Section Name:", etc.)
[ ] Diagnostics card (collapsed) shows: 953 / 70 / 19,871
[ ] Diagnostics card clearly labeled "Internal diagnostics — backend counts for engineering use only"
[ ] TypeScript: npx tsc --noEmit passes
[ ] Frontend: npm test passes
[ ] Backend: pytest passes
```

---

## Why Not Fix the Backend Instead?

The reconciliation audit (`docs/41_DATA_POPULATION_RECONCILIATION_AUDIT.md`)
identified two backend cleanup opportunities:

1. **Normalize `knowledge_base.json` IDs** so `BisData.standards()` returns
   500 instead of 953. Risk: may affect compliance scoring weight calculation
   if `is_compulsory` flag mapping changes.

2. **Normalize division strings before `summary()`** so backend reports 15
   instead of 70. Risk: affects the `/health` diagnostic endpoint expected by
   monitoring tools.

These are **architectural cleanup tasks** deferred to avoid RAG regression
risk. The frontend semantics fix is sufficient for the SIH presentation.

---

*Document generated from reconciliation audit conducted 2026-09-22.*  
*Canonical numbers validated by `scratch/reconcile_populations.py`.*
