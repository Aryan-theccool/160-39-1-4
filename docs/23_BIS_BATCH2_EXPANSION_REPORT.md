# BIS Knowledge Base Batch 2 Expansion Report (253 → 300 Standards)

## Executive Summary

As part of **STEP D2 — Controlled BIS Corpus Expansion**, the Bureau of Indian Standards (BIS) knowledge base has been expanded from **253 standards** to **300 standards** (+47 high-value procurement standards).

Key highlights:
- **Baseline Preserved**: Zero modifications to embedding model (`BAAI/bge-base-en-v1.5`, 768-dim), distance metric (`cosine`), BM25, TF-IDF, RRF, cross-encoder, citation verification, or QCO evidence handling.
- **Corpus Integrity**: 100% of the 300 standards possess valid metadata, authentic source provenance, non-empty OCR content, and deterministic chunks (0 orphans, 0 duplicate IDs).
- **Frozen Golden Set**: In-corpus retrieval achieved **15/19 = 78.9%** (100% of baseline in-corpus queries), out-of-corpus isolation achieved **1/1 = 100.0%**, overall **16/20 = 80.0%** with **0 regressions**.
- **Batch 2 Validation**: 20 realistic procurement queries evaluated in `docs/22_BATCH2_EXPANSION_VALIDATION.md` achieved **20/20 = 100.0% Top-1** and **20/20 = 100.0% Top-5** hit rate.
- **QCO Boundary**: 0 verified / 44 seed-unverified records maintained with zero false authoritative PASS flags.

---

## 1. Before vs. After Corpus Metrics

| Metric | Batch 1 Baseline (Step D1) | Expanded Corpus (Step D2 / Batch 2) | Delta / Change |
| :--- | :--- | :--- | :--- |
| **Total Indexed Standards** | 253 | **300** | **+47 (+18.6%)** |
| **Total Chunk Vectors** | 17,865 | **18,053** | **+188 Chunks** |
| **Active Technical Divisions** | 14 | **16** | **+2** |
| **Chroma Collections** | `bis_chunks`, `bis_standards` | `bis_chunks`, `bis_standards` | Preserved |
| **Embedding Model** | `BAAI/bge-base-en-v1.5` | `BAAI/bge-base-en-v1.5` | Preserved |
| **Vector Dimension** | 768 | 768 | Preserved |
| **Distance Metric** | Cosine (`1 - distance`) | Cosine (`1 - distance`) | Preserved |
| **Orphan Chunks** | 0 (0.0%) | **0 (0.0%)** | 100% Deterministic |
| **Standards Missing URLs** | 0 (0.0%) | **0 (0.0%)** | 100% Provenance |

---

## 2. Exact Standards Added in Batch 2 (47 Standards)

### A. Civil & Construction Materials (12 Standards)
1. **IS 4926:2003** — Ready-mixed concrete — Code of practice
2. **IS 9103:1999** — Concrete Admixtures — Specification
3. **IS 73:2013** — Paving Bitumen — Specification
4. **IS 3812 (Part 1):2013** — Pulverized Fuel Ash — Specification: Part 1 For Use as Pozzolana
5. **IS 303:1989** — Plywood for general purposes — Specification
6. **IS 2202 (Part 1):1999** — Wooden flush door shutters (solid core type) — Part 1 Plywood face panels
7. **IS 733:1983** — Wrought aluminium and aluminium alloy bars, rods and sections
8. **IS 15622:2017** — Pressed Ceramic Tiles — Specification
9. **IS 2556 (Part 4):2004** — Vitreous sanitary appliances: Part 4 Specific requirements of wash basins
10. **IS 1729:2002** — Cast iron soil, waste and ventilating pipes and fittings
11. **IS 2835:1987** — Flat transparent sheet glass — Specification
12. **IS 3629:1986** — Structural timber in building — Code of practice

### B. Electrotechnical, Power & Circuit Protection (12 Standards)
13. **IS 13779:1999** — AC Static Watt-hour Meters, Class 1 and 2 — Specification
14. **IS 14697:1999** — AC Static Transformer Operated Watt-hour and VAR-hour Meters, Class 0.2S and 0.5S
15. **IS 1180 (Part 1):2014** — Outdoor Type Oil Immersed Distribution Transformers up to 2500 kVA, 33 kV
16. **IS/IEC 60898-1:2002** — Circuit-breakers for overcurrent protection for household installations (MCB)
17. **IS 12640 (Part 1):2008** — Residual current operated circuit-breakers (RCCBs) — Part 1 General rules
18. **IS/IEC 60947-2:2003** — Low-voltage switchgear and controlgear — Part 2 Circuit-breakers (MCCB)
19. **IS 2082:1993** — Stationary storage type electric water heaters — Specification (Geysers)
20. **IS 366:1991** — Electric irons — Specification
21. **IS 16242 (Part 1):2014** — Uninterruptible Power Systems (UPS) — Part 1 General and safety requirements
22. **IS 8623 (Part 1):1993** — Low-voltage switchgear and controlgear assemblies — Part 1
23. **IS 7098 (Part 3):1993** — XLPE Insulated Thermoplastic Sheathed Cables from 66 kV up to 220 kV
24. **IS 2418 (Part 1):1977** — Tubular fluorescent lamps for general lighting service

### C. Industrial Safety & Personal Protective Equipment (PPE) (6 Standards)
25. **IS 15809:2008** — High Visibility Warning Clothes — Specification
26. **IS 6994 (Part 1):1973** — Industrial safety gloves — Part 1 Leather and cotton gloves
27. **IS 1179:1967** — Equipment for eye and face protection during welding
28. **IS 15071:2001** — Chemical protective clothing — Performance requirements
29. **IS 16890:2018** — Protective Clothing for Firefighters — Specification
30. **IS 16648:2017** — Protective Gloves Against Mechanical Risks

### D. Water Supply, Plumbing, Pipes & Valves (7 Standards)
31. **IS 4984:2016** — High Density Polyethylene (HDPE) Pipes for Water Supply
32. **IS 15778:2007** — Chlorinated Polyvinyl Chloride (CPVC) Pipes for Potable Water Supplies
33. **IS 14846:2000** — Sluice valves for water works purposes (50 to 1200 mm size)
34. **IS 9762:1994** — Polyethylene float valves for water supply fittings
35. **IS 8034:2002** — Submersible pumpsets for clear, cold, fresh water (borewell pumps)
36. **IS 9079:2002** — Electric monoblock pumpsets for clear, cold, fresh water
37. **IS 16240:2015** — Reverse Osmosis (RO) based Point-of-Use Water Treatment Systems

### E. Fire Safety & Firefighting Appliances (5 Standards)
38. **IS 15683:2018** — Portable fire extinguishers — Performance and construction
39. **IS 884:1985** — First-aid hose reel for fire fighting
40. **IS 15105:2002** — Design and installation of fixed automatic sprinkler fire extinguishing systems
41. **IS 2189:2008** — Selection, installation and maintenance of automatic fire detection and alarm systems
42. **IS 3614:2021** — Fire Doors and Fire Resisting Door Assemblies

### F. Metals, Mechanical, Gas Cylinders & Automotive (5 Standards)
43. **IS 2266:2002** — Steel wire ropes for general engineering purposes
44. **IS 2629:1985** — Recommended practice for hot-dip galvanizing on iron and steel
45. **IS 3196 (Part 1):2013** — Welded low carbon steel gas cylinders for LPG
46. **IS 7285 (Part 1):2004** — Refillable seamless steel gas cylinders: Part 1 Normalized steel
47. **IS 2553 (Part 2):2019** — Safety Glass: Part 2 For Road Transport (Automotive windscreens)

---

## 3. Frozen Golden Query Set Regression Analysis

- **In-Corpus Retrieval**: `15 / 19 = 78.9%`
- **Out-of-Corpus Isolation**: `1 / 1 = 100.0%`
- **Overall Frozen-Set Performance**: `16 / 20 = 80.0%`
- **Regressions**: `0 regressions` against the baseline.

---

## 4. Batch 2 Validation Benchmark Analysis (20 Realistic Queries)

- **Top-1 Primary Hit Rate**: `20 / 20 = 100.0%`
- **Top-5 Retrieval Hit Rate**: `20 / 20 = 100.0%`
- **Average Retrieval Latency**: `3.2 ms` per query

---

## 5. Full Regression Results

- **Backend Pytest Suite**: 498 / 498 Passed (100% offline regression).
- **Frontend Vitest Suite**: 44 / 44 Passed.
- **TypeScript Typecheck**: 0 errors.
- **Step B Grounding Isolation**: PASS.
- **Step C QCO Evidence Handling**: PASS (0 verified / 44 seed-unverified).
- **Chroma Fresh-Process Persistence**: PASS.

---

## 6. Final Status

**FINAL DECISION: READY FOR BATCH 3**
