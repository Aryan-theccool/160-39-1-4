# Step 3 — Multi-Format Tender Analysis & Compliance Matrix

## 1. Overview & Objectives

**Step 3** implemented the end-to-end **Tender RFP Ingestion, Clause Extraction, Standard Citation Matching, Compliance Matrix Assessment, and Reporting Engine**.

This capability enables procurement authorities and bidders to upload complex tender RFP documents (or paste specification text) and receive an instant, automated compliance and risk audit against Indian Standards and Quality Control Orders.

---

## 2. Step 3 Sub-Phase Architecture

Step 3 was delivered across 5 synchronized sub-phases:

```
Step 3A (Document Ingestion) -> Step 3B (Clause Extraction) -> Step 3C (Compliance Matrix) -> Step 3D (API Endpoints) -> Step 3E (UI & Reports)
```

| Phase | Component | Key Implementation Files |
|---|---|---|
| **Step 3A** | Multi-Format Document Ingestion | [`bis_scraper/src/bis_api/document_reader.py`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_scraper/src/bis_api/document_reader.py) |
| **Step 3B** | Clause Segmentation & Requirement Extraction | [`bis_scraper/src/bis_rag/tender_extractor.py`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_scraper/src/bis_rag/tender_extractor.py) |
| **Step 3C** | Tender Compliance Assessment Matrix Engine | [`bis_scraper/src/bis_rag/tender_compliance.py`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_scraper/src/bis_rag/tender_compliance.py) |
| **Step 3D** | REST API Routing & Serialization | [`bis_scraper/src/bis_api/routers/tender.py`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_scraper/src/bis_api/routers/tender.py) |
| **Step 3E** | Interactive UI & Publication Reports | [`bis_web/src/app/tender/page.tsx`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_web/src/app/tender/page.tsx), [`tender_report_builder.py`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_scraper/src/bis_rag/tender_report_builder.py) |

---

## 3. Step 3A — Multi-Format Document Ingestion

- **PDF Ingestion**: Uses PyMuPDF (`fitz`) when available for high-fidelity text and page layout extraction, with automatic fallback to `pypdf`. Preserves exact page numbers, character counts, and structural metadata.
- **DOCX Ingestion**: Uses `python-docx` to extract document headings, paragraph text, and nested table rows/columns with order preservation.
- **TXT Ingestion**: Handles raw text files with multi-encoding fallback (`utf-8`, `utf-16`, `latin-1`).
- **Defensive Safeguards**: Sanitizes filenames, enforces 50 MB upload limits, handles corrupt streams without server crashes, and prevents path traversal.

---

## 4. Step 3B — Clause Segmentation & Extraction

- **Clause Segmentation**: Identifies section boundaries, numbering schemes (`Clause 4.1`, `Section 2.3`), and clause types:
  - `technical`: Engineering limits and parameters.
  - `standards`: Explicit standard citations and codes.
  - `commercial`: Quantity, warranty, delivery times, price.
  - `scope`: Project location, supply boundary.
  - `eligibility`: Bidder qualifications, turnover.
- **Technical Parameter Extraction**: Robust regex rules extract canonical parameters (Voltage, Power, IP Rating, CCT, Frequency, Tolerance), specified numeric values, units, and operators (`>=`, `<=`, `exact`, `range`).
- **Commercial Clause Isolation**: Commercial parameters (e.g. `500 Nos.`, `5 years warranty`) are cleanly segregated so they never pollute engineering requirement checks.

---

## 5. Step 3C — Compliance Matrix & Risk Scoring

### Transparent Scoring Formula:
The engine computes a composite compliance score ($0.0 - 1.0$) with four transparently weighted metrics:
1. **Mandatory QCO Presence (Weight: 40%)**: Ratio of expected mandatory QCO standards present in the tender specification.
2. **Technical Requirement Checks (Weight: 40%)**: Ratio of technical requirements meeting standard benchmarks.
3. **Currency & Supersession (Weight: 15%)**: Deductions for cited standards that are obsolete or superseded.
4. **Requirement Consistency (Weight: 5%)**: Deductions if contradictory parameters are detected across clauses.

### Grade Assignment & Hard Overrides:
- **`FULLY COMPLIANT`**: Score $\ge 0.90$, all mandatory QCOs present, 0 requirement failures, 0 superseded standards.
- **`MOSTLY COMPLIANT`**: Score $\ge 0.75$, no missing mandatory QCOs.
- **`PARTIAL`**: Score $\ge 0.50$ or requirements flagged with warnings.
- **`NON-COMPLIANT`**: Missing compulsory QCO standards (hard cap override) or multiple failed benchmarks.

---

## 6. Step 3D — REST API Endpoints

- `POST /api/v1/tender/analyze/file`: Multipart upload endpoint accepting `.pdf`, `.docx`, or `.txt`.
- `POST /api/v1/tender/analyze/text`: Direct JSON payload endpoint for raw text tenders.
- `POST /api/v1/tender/report/docx`: Generates official Word assessment document.
- `POST /api/v1/tender/report/pdf`: Generates publication-grade PDF assessment document.

---

## 7. Step 3E — Tender Reports & UI Components

- **Executive Summary Block**: Overall grade, numerical score, risk level badge, and key warning alerts.
- **Requirements Matrix**: Interactive table with sorting and filtering by status (`PASS`, `FAIL`, `UNKNOWN`).
- **Standards & QCO Inspector**: Cards for every cited standard detailing active status, replacement years, and QCO mandates.
- **Clause Inspector**: Segmented view of all extracted tender clauses with page number references.

---

## 8. Test Suite & Verification Results

| Test Suite | File | Tests Passed |
|---|---|---|
| Ingestion Suite | [`test_document_reader.py`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_scraper/tests/test_document_reader.py) | **18 passed** |
| Extractor Suite | [`test_tender_extractor.py`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_scraper/tests/test_tender_extractor.py) | **32 passed** |
| Matrix Suite | [`test_tender_compliance.py`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_scraper/tests/test_tender_compliance.py) | **23 passed** |
| API Suite | [`test_tender_api.py`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_scraper/tests/test_tender_api.py) | **13 passed** |
| **Total Step 3 Tests** | | **86 passed** |
