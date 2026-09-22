# UI Changes & Frontend Architecture

## 1. Executive Summary

The frontend for the **SIH-108** project (*AI-Powered Recommendation Engine for Identifying Applicable Indian Standards for Procurement Specifications*) provides a modern, responsive web application built with Next.js and Tailwind CSS. It serves procurement officers, tender evaluators, bidders, and quality inspectors by enabling them to:
1. **Discover Relevant Indian Standards (BIS / IS codes)** using natural language queries and structured procurement specifications.
2. **Evaluate Product Specification Compliance** against confirmed applicable standards with strict safety guards (preventing false failures from scope-bound or unrelated standards).
3. **Analyze Tender RFPs & Documents** (PDF, DOCX, TXT) to automatically extract clauses, technical parameters, and referenced standards into an interactive compliance matrix.
4. **Export Publication-Grade DOCX & PDF Reports** directly from both conversational search results and tender compliance matrices.

---

## 2. Frontend Technology Stack

| Layer | Technology / Library | Version | Purpose |
|---|---|---|---|
| **Framework** | Next.js (App Router) | `16.1.6` | Server/Client rendering, routing, layout orchestration |
| **Runtime / Language** | React + TypeScript | `React 19` / `TypeScript 5.x` | Strict type safety, component lifecycle management |
| **Styling** | Tailwind CSS + Lucide Icons | `tailwindcss 3.4`, `lucide-react` | Modern utility styling, responsive design, iconography |
| **Markdown Rendering** | react-markdown + remark-gfm | `react-markdown`, `remark-gfm` | Rendering structured markdown, tables, and citations |
| **Testing** | Vitest + Testing Library | `vitest 2.1.8`, `@testing-library/react` | Component and unit test execution (44 tests) |

---

## 3. Existing Pages & Navigation

The application uses the Next.js App Router layout with navigation tabs in the top navigation bar:

1. **Standards Search / Assistant (`/` or `/search`)**: Main interactive conversational RAG interface for standard discovery.
2. **Product Compliance Checker (`/compliance`)**: Dedicated form for product parameter validation against specific IS codes.
3. **Tender RFP Analyzer (`/tender`)**: Multi-format document ingestion, raw text analysis, and interactive compliance matrix workspace.
4. **Standards Browser (`/standards`)**: Directory and detail viewer for indexed Indian Standards and division hierarchies.
5. **System Health & Architecture (`/health` or `/status`)**: Real-time inspection of backend engine components, vector collections, and QCO status.

---

## 4. Chat UI & Conversational Assistant

- **Component**: [`bis_web/src/components/chat-interface.tsx`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_web/src/components/chat-interface.tsx)
- **Features**:
  - Message thread with alternating user and assistant bubbles.
  - Streaming and non-streaming response handling.
  - Extractive vs LLM generation badge (`mode: "llm"` vs `mode: "extractive"`).
  - Collapsible standard citation drawer with direct links to BIS metadata.
  - Quick-prompt suggestion chips for representative procurement domains (e.g. *LED Street Lighting*, *PVC Cables*, *Transformers*, *Cement*).
  - Integrated "Download Official Report" action buttons (DOCX and PDF).

---

## 5. Recommendation UI & Standard Cards

- **Component**: [`bis_web/src/components/standard-card.tsx`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_web/src/components/standard-card.tsx)
- **Card Elements**:
  - **Standard Designation & Title**: Canonical designation (e.g. `IS 10028 (Part 2):1981`) and standardized title.
  - **Status Badges**: `CURRENT`, `SUPERSEDED`, `WITHDRAWN`.
  - **QCO Compliance Indicator**: Red/Green badges indicating mandatory compulsory certification status.
  - **Applicability Status**: `APPLICABLE`, `NOT_APPLICABLE`, `CANDIDATE` with explicit rationale.
  - **Clause Snippets & Evidence**: Grounded text chunks extracted from the vector store with similarity scores.

---

## 6. Product Compliance UI

- **Component**: [`bis_web/src/app/compliance/page.tsx`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_web/src/app/compliance/page.tsx)
- **Workflow**:
  - User enters a product description (e.g. `Outdoor LED street-light luminaire 90 W, 230 V AC, IP66, 4000 K`) and candidate standards.
  - Renders parameter breakdown with individual status badges:
    - `PASS`: Parameter strictly satisfies confirmed applicable standard requirement.
    - `FAIL`: Parameter violates confirmed applicable standard threshold.
    - `UNKNOWN`: Missing evidence in applicable standard (never falsely marked FAIL).
    - `NOT_APPLICABLE`: Candidate standard is unrelated to product domain.

---

## 7. Tender Analysis UI & Workspace

- **Component**: [`bis_web/src/app/tender/page.tsx`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_web/src/app/tender/page.tsx)
- **Dual Ingestion Options**:
  1. **Document Upload**: Drag-and-drop file upload supporting `.pdf`, `.docx`, and `.txt`.
  2. **Direct Text Input**: Paste raw tender RFP clauses and specifications directly into a rich text area.
- **Analysis Execution**: Calls `POST /api/v1/tender/analyze/file` or `POST /api/v1/tender/analyze/text` with live progress indication.

---

## 8. Upload / Drag-and-Drop Ingestion

- **Component**: [`bis_web/src/components/tender-upload.tsx`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_web/src/components/tender-upload.tsx)
- **Capabilities**:
  - File drop-zone with visual hover and drag feedback.
  - Client-side validation for allowed extensions (`.pdf`, `.docx`, `.txt`) and size limits (`50 MB`).
  - Clear file metadata preview (name, size, MIME type) before initiating analysis.
  - Graceful cancellation and re-upload support.

---

## 9. Tender Compliance Matrix Workspace

- **Component**: [`bis_web/src/components/tender-matrix-view.tsx`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_web/src/components/tender-matrix-view.tsx)
- **Workspace Views**:
  - **Executive Summary Header**: Displays Overall Grade (`FULLY COMPLIANT`, `MOSTLY COMPLIANT`, `PARTIAL`, `NON-COMPLIANT`), Numerical Compliance Score (0–100%), and Risk Level badge.
  - **Requirements Table**: Lists all extracted tender requirements (`REQ-001`, `REQ-002`, etc.), parameter names, specified tender values, mapped standards, compliance status, and evaluation rationale.
  - **Cited Standards Inspector**: Visual cards for every standard cited in the tender, showing applicability verdicts, QCO mandates, and supersession replacements.
  - **Clause Viewer**: Tabular clause inspector showing segmented clauses (Technical, Commercial, Scope, Eligibility, Standards).
  - **Actionable Recommendations**: Bulleted guidance for procurement authorities or bidders.

---

## 10. Filters & Interactive Controls

- **Filter Controls**:
  - Filter requirements by status: `ALL`, `PASS`, `FAIL`, `UNKNOWN`, `FLAGGED`.
  - Filter by category: `Electrical`, `Mechanical`, `Photometric`, `Environmental`, `Safety`.
  - Filter by mandatory status: `Mandatory Only` vs `All Requirements`.
  - Free-text search over extracted clause text and parameter names.

---

## 11. Risk & Warning Displays

- Prominent banner alerts for critical procurement risks:
  - **Missing Mandatory QCO Standards**: Alerts when a product subject to compulsory BIS certification omits the required standard.
  - **Superseded Standards**: Identifies deprecated citations and suggests the active replacement year.
  - **Conflicting Requirements**: Highlights contradictory requirements detected across different tender clauses.
  - **Outside Corpus Standards**: Clear notice that unverified standards require manual verification.

---

## 12. DOCX & PDF Download UI

- Export buttons located in both Chat recommendations and Tender Analysis matrix view.
- **Client Implementation**: [`bis_web/src/lib/api.ts`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_web/src/lib/api.ts) (`downloadTenderReportDocx`, `downloadTenderReportPdf`, `downloadReportDocx`, `downloadReportPdf`).
- Uses binary `Blob` handling with automatic `URL.createObjectURL` and dynamic anchor trigger for cross-browser file download with proper filenames.

---

## 13. Loading, Error & Empty States

- **Loading States**: Skeleton cards and animated pulse indicators during embedding generation, retrieval, and LLM evaluation.
- **Error States**: Non-blocking toast notifications and contextual inline alert boxes displaying API error messages with request IDs.
- **Empty States**: Clear instructional illustrations and sample prompts when no queries have been executed or documents uploaded.

---

## 14. API Integration

All frontend API calls are centralized in [`bis_web/src/lib/api.ts`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_web/src/lib/api.ts):
- `POST /api/v1/recommend`: Natural language query recommendation.
- `POST /api/v1/compliance/check`: Product specification compliance check.
- `POST /api/v1/tender/analyze/file`: Multi-part document upload analysis.
- `POST /api/v1/tender/analyze/text`: Direct text tender analysis.
- `POST /api/v1/tender/report/docx`: Download tender assessment DOCX.
- `POST /api/v1/tender/report/pdf`: Download tender assessment PDF.
- `GET /api/v1/health`: System health and vector store availability.

---

## 15. TypeScript Types

All data contracts match backend schemas in [`bis_web/src/lib/types.ts`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_web/src/lib/types.ts):
- `TenderAnalysisResponse`: Full response payload from tender analyzer.
- `TenderComplianceMatrix`: Summary score, grade, risks, and recommendations.
- `TenderRequirementEvaluation`: Individual requirement check structure.
- `TenderStandardAssessment`: Standard applicability and QCO evaluation.
- `TenderClause`: Structured tender clause metadata.

---

## 16. Responsive & Accessibility Considerations

- Full responsive layout supporting mobile, tablet, and desktop viewports.
- Accessible ARIA attributes on interactive tabs, modal dialogs, and upload dropzones.
- Semantic HTML tags (`<header>`, `<main>`, `<section>`, `<table>`, `<article>`).
- High-contrast color palette adhering to WCAG 2.1 AA standards for status badges.

---

## 17. Testing & Quality Assurance

- **Vitest Test Suite**: 44 tests across 3 test suites verifying UI rendering, API payload formatting, matrix table filtering, and download triggers.
- **TypeScript Compilation**: `npm run typecheck` passes with **0 errors**.
- **Production Build**: `npm run build` succeeds cleanly with **11/11 static/dynamic pages compiled**.

---

## 18. Files Created & Modified

### Created Files:
- [`bis_web/src/app/tender/page.tsx`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_web/src/app/tender/page.tsx): Main tender analysis workspace page.
- [`bis_web/src/components/tender-upload.tsx`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_web/src/components/tender-upload.tsx): Drag-and-drop document upload component.
- [`bis_web/src/components/tender-matrix-view.tsx`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_web/src/components/tender-matrix-view.tsx): Interactive compliance matrix view.
- [`bis_web/src/components/tender-clause-view.tsx`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_web/src/components/tender-clause-view.tsx): Segmented clause inspector.
- [`bis_web/src/components/tender-standards-view.tsx`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_web/src/components/tender-standards-view.tsx): Cited standards cards and QCO inspector.

### Modified Files:
- [`bis_web/src/lib/api.ts`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_web/src/lib/api.ts): Added tender endpoints and report download functions.
- [`bis_web/src/lib/types.ts`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_web/src/lib/types.ts): Added Step 3 TypeScript interfaces.
- [`bis_web/src/components/navbar.tsx`](file:///d:/Shreyansh%20PC/Project/160-39-1-4-main/bis_web/src/components/navbar.tsx): Added Tender RFP Analysis navigation link.

---

## 19. Before vs After Comparison

| Capability | Before Project Iterations | Current Implementation |
|---|---|---|
| **Tender Analysis** | Not available | Full multi-format upload, clause extraction, matrix visualization |
| **Compliance Presentation** | Generic text output | Structured parameter breakdown with PASS / FAIL / UNKNOWN badges |
| **Report Export** | Not available | One-click publication-grade DOCX and PDF downloads |
| **Applicability Awareness** | Standards assumed valid | Explicit APPLICABLE / NOT_APPLICABLE / CANDIDATE rationale |
| **Error & Safety Handling** | Silent failures or false FAIL | Explicit UNKNOWN indicators and risk warning banners |

---

## 20. Known Limitations

- **Scanned PDF Text Selection**: Image-only PDF inspection in UI depends on server-side OCR availability.
- **Very Large Tenders (>500 pages)**: Browser rendering of >1000 extracted clauses should use virtualized list scrolling (planned for future optimization).
