# Step 1 — Professional DOCX & PDF Procurement Reports

## 1. Overview & Objectives

**Step 1** of the SIH-108 project established the generation of **publication-grade, downloadable Microsoft Word (.docx) and Adobe PDF (.pdf) procurement reports** directly from conversational recommendations and standard discovery results.

Government procurement officers, PSU evaluators, and tender committees require formal, archivable documentation that can be attached to procurement files, RFP notices, or audit binders.

---

## 2. Technical Architecture

- **Implementation File**: [`bis_scraper/src/bis_rag/report_builder.py`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_scraper/src/bis_rag/report_builder.py)
- **DOCX Engine**: `python-docx 1.2.0`
- **PDF Engine**: `reportlab 5.0.1` (using Flowables, Platypus layout, and Canvas numbering)
- **API Endpoints**:
  - `POST /api/v1/report/docx`: Generates and streams `.docx` document.
  - `POST /api/v1/report/pdf`: Generates and streams `.pdf` document.

---

## 3. Microsoft Word (.docx) Report Architecture

The `.docx` builder generates structured documents styled to government publication standards:

1. **Document Header & Cover Metadata**:
   - Official document title: *"BIS Standards Procurement Recommendation Report"*.
   - Generation timestamp, Request ID, and AI mode indicator (`LLM Assisted` / `Extractive Engine`).
2. **Executive Summary Callout Box**:
   - Shaded table cell with left accent border providing a high-level procurement summary.
3. **Recommended Standards Table**:
   - Standard Designation (bold canonical name).
   - Standard Title and Division.
   - Applicability Status with color-coded badge.
   - QCO Compulsory Certification flag.
4. **Technical Requirement Breakdown**:
   - Parameter name, required benchmark value, unit, and standard clause reference.
5. **Audit Trail & Disclaimers**:
   - Disclaimer regarding current standard editions and mandatory NABL lab testing.

---

## 4. PDF Report Architecture & Platypus Layout

The PDF builder uses ReportLab's Platypus framework with custom flowables:

1. **Two-Pass Numbered Canvas (`NumberedCanvas`)**:
   - Implements dynamic `"Page X of Y"` page numbering in the running footer.
   - Suppresses page headers/footers on the cover section.
2. **Color Palette & Typography**:
   - Primary Header: Deep Navy (`#1E3A8A`)
   - Accent / Borders: Steel Blue (`#3B82F6`)
   - Neutral Text: Dark Charcoal (`#1F2937`)
   - Background Shading: Cool Gray (`#F3F4F6`)
3. **Structured Tables**:
   - Explicit column width allocations with auto-wrapping Paragraph cells.
   - Alternating row background shading for legibility.
4. **Compliance Badges**:
   - Inline status badges for `PASS` (Green), `FAIL` (Red), `UNKNOWN` (Amber), and `APPLICABLE` (Blue).

---

## 5. API Request & Response Schema

### Request Payload (`ReportExportRequest`):
```json
{
  "question": "Outdoor LED street lighting for municipal highway",
  "answer": "The primary standard for LED street luminaires is IS 10322 (Part 5/Sec 3)...",
  "mode": "llm",
  "generator": "groq",
  "grounded": true,
  "report": {
    "executive_summary": "Applicable standards for LED luminaires.",
    "recommended_standards": [
      {
        "designation": "IS 10322 (Part 5/Sec 3):2012",
        "title": "Luminaires for road and street lighting",
        "applicability": "APPLICABLE",
        "mandatory_qco": true
      }
    ]
  },
  "citations": [
    {
      "designation": "IS 10322 (Part 5/Sec 3):2012",
      "clause": "Clause 4.1"
    }
  ],
  "warnings": []
}
```

### HTTP Response Headers:
```http
HTTP/1.1 200 OK
Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
Content-Disposition: attachment; filename="bis_procurement_report_20260921_110000.docx"
Access-Control-Expose-Headers: Content-Disposition
```

---

## 6. Binary Validation & Testing

- **Automated Tests**: [`bis_scraper/tests/test_report_export.py`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_scraper/tests/test_report_export.py) (**22 passed**).
- **Inspection**:
  - `python-docx` parses generated DOCX and verifies paragraphs, tables, cell text, and headings.
  - `pypdf.PdfReader` parses generated PDF, confirming valid stream headers, multi-page flows, and non-empty character streams.
