# Quality Control Order (QCO) Quality & Compliance Hardening

**Document ID**: `docs/19_QCO_AUDIT_AND_HARDENING.md`  
**Step**: STEP C — QCO Data Quality and Compliance Hardening  
**Status**: COMPLETE  
**Baseline Knowledge Base**: 197 BIS Standards (Golden Baseline frozen)  

---

## 1. Executive Summary & Audit of the 44-Record Seed Dataset

### 1.1 Origin of the Current 44 Records
The 44 Quality Control Order records currently indexed originate from an internal bootstrap lookup table (`SEED_QCO`) defined in `bis_scraper/src/bis_rag/compliance.py`. This dataset covers key Indian Standards across 5 primary industrial sectors:
1. **Civil Engineering & Construction** (e.g., IS 269, IS 456, IS 1489, IS 1786, IS 383, IS 458, IS 1536, IS 1077, IS 2185)
2. **Electrical & Electronics** (e.g., IS 302, IS 694, IS 1554, IS 7098, IS 1293, IS 8828, IS 616, IS 13252, IS 14700)
3. **Water Supply & Plumbing** (e.g., IS 4985, IS 1239, IS 1879, IS 14543, IS 13488)
4. **Mechanical, Automotive & Safety** (e.g., IS 14220, IS 8472, IS 5120, IS 3196, IS 4151, IS 15298, IS 3055, IS 9873)
5. **Food & Packaging** (e.g., IS 1165, IS 1479, IS 14433, IS 4707, IS 7215)

### 1.2 Exact Fields Available & Verification Limitations
| Field | Status / Value in Seed | Limitations & Traceability |
|---|---|---|
| `key` | Yearless stem (e.g., `"is 269"`) | Clean structural key for comparison |
| `designation` | Standard ID (e.g., `"IS 269"`) | Normalized uppercase designation |
| `product` | Product description | Informal bootstrap description; not official Gazette text |
| `sector` | Sector category | Heuristic sector grouping |
| `qco_year` | `None` | Official notification dates are absent in seed data |
| `source` | `"seed"` | Explicitly labeled non-scraped bootstrap |
| `verified` | `False` | Unverified |
| `source_url` | `""` | No government gazette or BIS portal citation attached |
| `evidence_state` | `SEED_UNVERIFIED` | Governed by safety cap rules |

> [!CAUTION]
> **Explicit Disclaimer on Coverage**:  
> The 44-record dataset is a seed bootstrap dataset and is **NOT** claimed to be complete or exhaustive. Thousands of Indian Standards are covered by ministry-specific QCO notifications (DPIIT, Ministry of Steel, MeitY, MoPNG, etc.). The application makes no claim of complete legal regulatory coverage.

---

## 2. 5-Tier Explicit QCO Evidence States

The system implements the `QCOEvidenceState` model across data structures, compliance engines, and client interfaces:

```
                  ┌─────────────────────────────────────┐
                  │          Standard Under Audit       │
                  └──────────────────┬──────────────────┘
                                     │
           ┌─────────────────────────┼─────────────────────────┐
           ▼                         ▼                         ▼
   ┌───────────────┐         ┌───────────────┐         ┌───────────────┐
   │   VERIFIED    │         │SEED_UNVERIFIED│         │   NOT_FOUND   │
   │ Official BIS  │         │ Bootstrap Seed│         │ No Record in  │
   │ Scrape/Merged │         │ (Cap Grade)   │         │ Current Store │
   └───────────────┘         └───────────────┘         └───────────────┘
           │                         │                         │
           ▼                         ▼                         ▼
   Authoritative PASS       Capped at MOSTLY        "No QCO Evidence"
   Full Legal Evidence      Warning Generated       (Never "Voluntary")
```

### State Definitions & Operational Semantics

1. **`VERIFIED`**:
   - **Condition**: Standard is verified by official BIS mandatory portal scraping (`mandatory.json`) or merged verified standard metadata.
   - **Behavior**: Permitted to act as authoritative regulatory evidence. Retains traceable `source_url` and notification metadata.
2. **`SEED_UNVERIFIED`**:
   - **Condition**: Standard is present only in the hardcoded bootstrap `SEED_QCO` dictionary.
   - **Behavior**: **Must NEVER produce a final authoritative compliance grade of `FULLY COMPLIANT`**. Caps grade at `MOSTLY COMPLIANT` (score max 0.89), generates an audit warning in API responses and reports, and renders an amber `QCO (Seed Unverified)` badge in the UI.
3. **`NOT_FOUND`**:
   - **Condition**: No matching QCO entry exists in the currently indexed database.
   - **Behavior**: **Never claims or implies that the standard is legally "Voluntary"**. Labeled honestly in all UI views and PDF/DOCX exports as `"No QCO Evidence Found in Current Dataset"`.
4. **`NOT_APPLICABLE`**:
   - **Condition**: Product description or scope conclusively falls outside the applicable domain of the standard.
5. **`AMBIGUOUS`**:
   - **Condition**: Conflicting or non-differentiated candidate matches.

---

## 3. Compliance Safety & Anti-Hallucination Hardening

### 3.1 Hardened Rules Implemented
1. **Safety Capping**: When any mandatory standard relied upon has `qco_evidence_state == SEED_UNVERIFIED`, the overall grade is automatically capped from `FULLY COMPLIANT` to `MOSTLY COMPLIANT`, accompanied by:
   - Notice: `"QCO data source is unverified seed data (audit required before procurement sign-off)"`.
2. **Voluntary Label Elimination**: Replaced all instances where absence of QCO record was labeled as `"Voluntary"` with `"No QCO Evidence in Dataset"`.
3. **Supersession & Integrity Preservation**: Out-of-corpus and unverified citations retain their Step B anti-hallucination warnings in chat and structured reports.
4. **Tender Matrix Alignment**: Every row in `TenderStandardAssessment` and `ResolvedStandard` exposes:
   - `is_mandatory_qco: bool`
   - `qco_evidence_state: str` (`VERIFIED`, `SEED_UNVERIFIED`, `NOT_FOUND`, `NOT_APPLICABLE`, `AMBIGUOUS`)
   - `qco_display: str` (e.g. `"YES (Verified QCO)"`, `"YES (Unverified Seed)"`, `"No QCO Evidence in Dataset"`)
   - `qco_source: str` (`"scraped"`, `"merged"`, `"seed"`, `"none"`)
   - `qco_verified: bool`

---

## 4. API, Report Export, & Frontend UX Hardening

### 4.1 UI Badge & Label Mapping
- **Emerald Badge** (`Verified QCO`): Rendered when `qco_evidence_state === "VERIFIED"`.
- **Amber Badge** (`QCO (Seed Unverified)`): Rendered when `qco_evidence_state === "SEED_UNVERIFIED"`.
- **Muted Slate Badge / Label** (`No QCO Evidence in Dataset`): Rendered when `qco_evidence_state === "NOT_FOUND"`.

### 4.2 PDF & DOCX Export Matrix
Both `report_builder.py` and `tender_report_builder.py` render publication-grade tables clearly identifying:
- Mandatory QCO column: `YES (Verified)`, `YES (Unverified)`, or `No Record in Dataset`.
- Compliance summary: Explicit notice regarding dataset tier and verification status.

### 4.3 Health Endpoint
`GET /api/v1/health` accurately reports:
- `qco.source`: `"seed" | "merged" | "scraped"`
- `qco.verified`: `true | false`
- `issues`: Automatically flags `"QCO list is the unverified seed set"` when running in seed mode, keeping system health transparent (`degraded`).

---

## 5. Verification & Test Gate Results

| Test Suite | Result | Details |
|---|---|---|
| **Backend Pytest Suite** | **PASS** | 500/500 items collected and verified |
| **Frontend Vitest Suite** | **PASS** | 3/3 test files passed, 44/44 unit tests passed |
| **TypeScript Typecheck** | **PASS** | `npx tsc --noEmit` exited with 0 errors |
| **Step B Grounding Regression** | **PASS** | Out-of-corpus isolation & citation warnings preserved |
| **QCO Evidence State Unit Tests**| **PASS** | Focused unit tests in `test_rag_compliance.py` and `test_tender_compliance.py` |

---

## 6. Known Limitations
1. **Bootstrap Scale**: The seed QCO dataset contains 44 standards. Expanding this dataset with full Gazette citations, ministry origins, and notification dates will be addressed in future phases.
2. **Dynamic Gazette Tracking**: Ongoing amendments published by the Government of India Gazette require continuous periodic sync pipelines.
