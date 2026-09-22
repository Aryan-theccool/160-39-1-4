# STEP QCO-1: AUDIT AND EXPORT OF THE 44 QCO SEED RECORDS

**Document ID**: `DOC-31-QCO-44-SEED-INVENTORY`  
**Status**: **QCO INVENTORY COMPLETE — READY FOR OFFICIAL VERIFICATION**  
**Date**: September 22, 2026  
**Parent System Validation**: `DOC-30-FINAL-SYSTEM-VALIDATION` (PASS)  
**Corpus Scope**: Curated subset of 500 BIS standards (19,871 chunks)

---

## 1. SOURCE LOCATION & ARCHITECTURAL DISCOVERY

### Exact File & Module
- **Primary Source File**: [`bis_scraper/src/bis_rag/compliance.py`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_scraper/src/bis_rag/compliance.py)
- **Lines of Definition**: Lines 96–159 (`SEED_QCO: dict[str, dict[str, str]]`)
- **Runtime Loader**: [`bis_rag.compliance.QCODatabase`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_scraper/src/bis_rag/compliance.py#L304-L420)
- **Data Models**:
  - `QCOEntry` dataclass (`bis_rag.compliance.QCOEntry`)
  - `QCOEvidenceState` (`bis_rag.compliance.QCOEvidenceState`)

### Loader & Fallback Mechanism
The `QCODatabase` loader executes a 3-tier hierarchy:
1. **Tier 1 (Authoritative Scrape)**: Attempts to load `mandatory/mandatory.json`. If absent or unpopulated (0 valid rows), raises `ValueError` and falls back to Tier 2/3.
2. **Tier 2 (Merged Corpus Flag)**: Attempts to derive compulsory flags from `merged/merged_standards.json` if present.
3. **Tier 3 (Seed Fallback)**: Calls `self._load_seed()`, which iterates over `SEED_QCO` and instantiates 44 `QCOEntry` objects with `verified=False`, `source="seed"`, and `evidence_state="SEED_UNVERIFIED"`.

---

## 2. COMPLETE INVENTORY TABLE OF ALL 44 SEED RECORDS

| # | Record ID | Product | IS Standard | Edition | QCO | Notification | Ministry | Effective Date | Source | Evidence State | Verified |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `QCO-SEED-01` (`is 269`) | 33 grade ordinary Portland cement | IS 269 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 2 | `QCO-SEED-02` (`is 455`) | Portland slag cement | IS 455 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 3 | `QCO-SEED-03` (`is 1489`) | Portland pozzolana cement | IS 1489 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 4 | `QCO-SEED-04` (`is 8041`) | rapid hardening Portland cement | IS 8041 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 5 | `QCO-SEED-05` (`is 8112`) | 43 grade ordinary Portland cement | IS 8112 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 6 | `QCO-SEED-06` (`is 12269`) | 53 grade ordinary Portland cement | IS 12269 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 7 | `QCO-SEED-07` (`is 383`) | coarse and fine aggregates for concrete | IS 383 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 8 | `QCO-SEED-08` (`is 1786`) | high strength deformed steel bars for reinforcement | IS 1786 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 9 | `QCO-SEED-09` (`is 432`) | mild steel bars for concrete reinforcement | IS 432 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 10 | `QCO-SEED-10` (`is 458`) | precast concrete pipes | IS 458 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 11 | `QCO-SEED-11` (`is 1536`) | centrifugally cast iron pressure pipes | IS 1536 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 12 | `QCO-SEED-12` (`is 1077`) | common burnt clay building bricks | IS 1077 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 13 | `QCO-SEED-13` (`is 2185`) | concrete masonry units | IS 2185 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 14 | `QCO-SEED-14` (`is 302`) | safety of household and similar electrical appliances | IS 302 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 15 | `QCO-SEED-15` (`is 694`) | PVC insulated cables for working voltages up to 1100 V | IS 694 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 16 | `QCO-SEED-16` (`is 1554`) | PVC insulated cables | IS 1554 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 17 | `QCO-SEED-17` (`is 7098`) | cross-linked polyethylene insulated cables | IS 7098 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 18 | `QCO-SEED-18` (`is 1293`) | plugs and socket outlets | IS 1293 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 19 | `QCO-SEED-19` (`is 8828`) | miniature circuit breakers | IS 8828 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 20 | `QCO-SEED-20` (`is 616`) | safety of audio, video and similar electronic apparatus | IS 616 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 21 | `QCO-SEED-21` (`is 13252`) | safety of information technology equipment | IS 13252 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 22 | `QCO-SEED-22` (`is 14700`) | electromagnetic compatibility of electrical equipment | IS 14700 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 23 | `QCO-SEED-23` (`is 4985`) | unplasticized PVC pipes for potable water | IS 4985 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 24 | `QCO-SEED-24` (`is 1239`) | steel tubes and tubular fittings | IS 1239 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 25 | `QCO-SEED-25` (`is 1879`) | cast iron fittings for water and gas | IS 1879 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 26 | `QCO-SEED-26` (`is 14543`) | packaged drinking water | IS 14543 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 27 | `QCO-SEED-27` (`is 13488`) | water meters | IS 13488 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 28 | `QCO-SEED-28` (`is 14220`) | submersible pumpsets | IS 14220 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 29 | `QCO-SEED-29` (`is 8472`) | centrifugal pumps | IS 8472 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 30 | `QCO-SEED-30` (`is 5120`) | gas cylinders | IS 5120 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 31 | `QCO-SEED-31` (`is 3196`) | LPG cylinders | IS 3196 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 32 | `QCO-SEED-32` (`is 4151`) | protective helmets for motorcycle riders | IS 4151 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 33 | `QCO-SEED-33` (`is 15298`) | footwear | IS 15298 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 34 | `QCO-SEED-34` (`is 3055`) | clinical thermometers | IS 3055 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 35 | `QCO-SEED-35` (`is 9873`) | safety of toys | IS 9873 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 36 | `QCO-SEED-36` (`is 1165`) | milk powder | IS 1165 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 37 | `QCO-SEED-37` (`is 1479`) | condensed milk | IS 1479 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 38 | `QCO-SEED-38` (`is 14433`) | infant milk substitutes | IS 14433 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 39 | `QCO-SEED-39` (`is 4707`) | food colours | IS 4707 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 40 | `QCO-SEED-40` (`is 7215`) | code of practice for food packaging | IS 7215 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 41 | `QCO-SEED-41` (`is 121`) | medium density fibre boards | IS 121 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 42 | `QCO-SEED-42` (`is 1566`) | hard drawn steel wire for prestressed concrete | IS 1566 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 43 | `QCO-SEED-43` (`is 6003`) | cement concrete flooring tiles | IS 6003 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |
| 44 | `QCO-SEED-44` (`is 2096`) | non-load bearing gypsum partition slabs | IS 2096 | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | NOT PRESENT | seed | SEED_UNVERIFIED | False |

---

## 3. DATA QUALITY AUDIT STATISTICS

| Quality Metric | Count | Percentage |
|---|---|---|
| **Total QCO Records** | **44** | 100.0% |
| **Unique Record IDs** | **44** | 100.0% |
| **Duplicate Records** | **0** | 0.0% |
| **Records with IS Code** | **44** | 100.0% |
| **Records without IS Code** | **0** | 0.0% |
| **Records with QCO Order Name/Title** | **0** | 0.0% |
| **Records without QCO Order Name/Title** | **44** | 100.0% |
| **Records with S.O. / Gazette Notification Number** | **0** | 0.0% |
| **Records without Gazette Notification Number** | **44** | 100.0% |
| **Records with Ministry / Department Attribution** | **0** | 0.0% |
| **Records without Ministry / Department Attribution** | **44** | 100.0% |
| **Records with Official Source URL** | **0** | 0.0% |
| **Records without Official Source URL** | **44** | 100.0% |
| **Records with Effective / Enforcement Date** | **0** | 0.0% |
| **Records without Effective / Enforcement Date** | **44** | 100.0% |
| **Records Marked `qco_verified=True`** | **0** | 0.0% |
| **Records Marked `qco_verified=False`** | **44** | 100.0% |
| **Records in `SEED_UNVERIFIED` State** | **44** | 100.0% |
| **Records with Ambiguous / Incomplete Metadata** | **44** | 100.0% |

> **Audit Finding**: Every record in the current seed set contains only an informal product string, an IS code, and a sector tag. None of the 44 records currently possess official gazette notifications, S.O. numbers, ministry citations, enforcement dates, or authenticating source URLs.

---

## 4. DOMAIN & SECTOR GROUPINGS

### Group A: By Product Sector
1. **Construction Materials (`sector = construction`) — 17 records (38.6%)**:
   - IS 269, IS 455, IS 1489, IS 8041, IS 8112, IS 12269 (Cement varieties)
   - IS 383 (Aggregates)
   - IS 1786, IS 432, IS 1566 (Steel reinforcement & wire)
   - IS 458, IS 1536 (Pipes)
   - IS 1077, IS 2185, IS 6003, IS 2096, IS 121 (Bricks, blocks, tiles, slabs, boards)

2. **Electrical & Electronics (`sector = electrical`) — 9 records (20.5%)**:
   - IS 302, IS 616, IS 13252 (Appliances, audio/video, IT equipment safety)
   - IS 694, IS 1554, IS 7098 (Cables & wires)
   - IS 1293 (Plugs and sockets)
   - IS 8828 (Miniature circuit breakers)
   - IS 14700 (Electromagnetic compatibility)

3. **Mechanical, Automotive & Safety (`sector = mechanical`) — 8 records (18.2%)**:
   - IS 14220, IS 8472 (Submersible and centrifugal pumps)
   - IS 5120, IS 3196 (Gas and LPG cylinders)
   - IS 4151 (Motorcycle helmets)
   - IS 15298 (Footwear)
   - IS 3055 (Clinical thermometers)
   - IS 9873 (Toys)

4. **Water Supply & Plumbing (`sector = water_supply`) — 5 records (11.4%)**:
   - IS 4985 (uPVC pipes for drinking water)
   - IS 1239, IS 1879 (Steel tubes & cast iron fittings)
   - IS 14543 (Packaged drinking water)
   - IS 13488 (Water meters)

5. **Food & Dairy Packaging (`sector = food`) — 5 records (11.4%)**:
   - IS 1165, IS 1479, IS 14433 (Milk powder, condensed milk, infant milk)
   - IS 4707 (Food colours)
   - IS 7215 (Food packaging code of practice)

### Group B: By Source Type & Evidence State
- **Source = `seed`**: 44 (100.0%)
- **Source = `scraped`**: 0 (0.0%)
- **Source = `merged`**: 0 (0.0%)
- **Evidence State = `SEED_UNVERIFIED`**: 44 (100.0%)
- **Verified = `False`**: 44 (100.0%)

---

## 5. APPLICATION DATA FLOW & VERDICT SAFETY TRACE

```
+-------------------------------------------------------------------------------+
|                       bis_scraper/src/bis_rag/compliance.py                   |
|                        SEED_QCO = { "is 269": {...}, ... }                    |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
|                    QCODatabase._load() -> _load_seed()                        |
|       Constructs QCOEntry(source='seed', verified=False,                      |
|                           evidence_state='SEED_UNVERIFIED')                   |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
|              ComplianceChecker.check() & assess_tender_compliance()           |
|  - Compares product / tender requirements against QCO entries                 |
|  - Invokes _score_and_grade()                                                 |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
|                    MANDATORY REGULATORY SAFETY GATE                           |
|                                                                               |
|   if grade == "FULLY COMPLIANT" and not self.qco.verified:                    |
|       grade = "MOSTLY COMPLIANT"                                              |
|       report.grade_capped_by = (                                              |
|           "the QCO list is the built-in seed set, which may be incomplete; "  |
|           "a fully-compliant verdict needs the scraped list"                  |
|       )                                                                       |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
|                      FastAPI Endpoints & UI Presentation                      |
|  - /api/v1/compliance & /api/v1/tender return QCOEvidenceState: SEED_UNVERIFIED|
|  - /api/v1/health reports status: degraded (unverified QCO evidence)          |
|  - Frontend displays warning badge: "Unverified Seed QCO Record"              |
|  - Reports (DOCX / PDF) include regulatory disclaimer regarding seed data     |
+-------------------------------------------------------------------------------+
```

### Safety Safeguards Verification
1. **No Authoritative False-PASS**: When evaluating products matching any of the 44 standards (e.g. `IS 8112` 43 Grade Cement or `IS 1180` Distribution Transformers), the grade is hard-capped at `MOSTLY COMPLIANT`.
2. **Deterministic Reason Strings**: `grade_capped_by` explicitly discloses to users and auditors that the verdict is derived from unverified seed data.
3. **Health Check Warning**: The system health endpoint (`/api/v1/health`) flags QCO data as unverified.

---

## 6. AUDIT CONFIRMATION & INTEGRITY CHECK

- **Code Modifications in Step QCO-1**: **NONE** (0 lines altered).
- **Data Modifications in Step QCO-1**: **NONE** (0 records added/modified/deleted).
- **RAG Architecture Modifications**: **NONE** (Chroma collections and hybrid retrieval unchanged).
- **Corpus Integrity**: Maintained at exactly 500 standards and 19,871 chunks.

---

## 7. VERIFICATION TESTS EXECUTED

```bash
python scratch/run_step_e_final_system_validation.py
```
- **Corpus Integrity**: PASS (500 standards, 19,871 chunks)
- **FastAPI Endpoints**: PASS (`/health` reports degraded/seed QCO status)
- **Grounding Gate**: PASS (100% verified, 0 phantom citations)
- **Compliance Cases (A, B, C)**: PASS (All capped at `MOSTLY COMPLIANT`, 0 false `FULLY COMPLIANT`)
- **QCO Database Counts**: PASS (0 verified, 44 seed-unverified)
- **Security & Tender Gates**: PASS

---

## SUMMARY OF THE CURRENT QCO DATASET

```
CURRENT QCO DATASET
-------------------
Total records: 44
Verified: 0
Seed/unverified: 44
```

### FINAL STATUS
```
================================================================================
QCO INVENTORY COMPLETE — READY FOR OFFICIAL VERIFICATION
================================================================================
```
