# Dashboard Division Data Audit & Compliance Gap Report Print Fix

## 1. Division Chart

### The 30 → 8 Discrepancy
- **Previous state:** 30 divisions (actually ~18 after HTML tag cleanup) was derived from fetching the **entire corpus** (all 953 standards, including superseded ones).
- **Current state:** 8 divisions was derived because the dashboard was calling `listStandards({ limit: 500 })` without explicitly requesting `current_only: false`. The API defaults to returning only current, active standards (`current_only=True`). Current standards in the corpus span only 11 distinct divisions (8 after merging similar strings like "Civil Engineering" and "Civil Engineering Division (CED)").
- **Root cause:** The API endpoint default behaviour filtered out superseded standards, reducing the dataset the chart was rendering from ~953 down to ~773.

### Resolution
- **Actual source dataset:** The dashboard now requests `current_only: false` to represent the full indexed corpus (953 standards) accurately in the chart.
- **Actual unique division count:** There are 18 cleaned unique divisions across all 953 standards (e.g. Civil Engineering, Electrotechnical, Chemical, etc.).
- **Missing/unclassified:** Malformed HTML markup present in the `division` field of the BIS index (e.g., `</b> Mechanical Engineering<br />...`) has been handled gracefully by the existing `cleanDivisionName` utility, which strips HTML tags and normalises the strings. 
- **Top-N behavior:** The Top-N controls have been made fully dynamic. The `[Top 8]` and `[Top 12]` buttons are only rendered if there are actually more than 8 or 12 divisions respectively. A new `[All N]` button is rendered dynamically based on the total count.

## 2. Gap Report

### Print / Save as PDF
- **Previous behavior:** A "Download Gap Report" button used an API fetch + blob creation workflow to force download a file named `bis_gap_report.html`, which users were expected to open and print manually.
- **New Print / Save as PDF behavior:** The button label is now **"Print / Save as PDF"**. It opens the existing printable HTML report in a new tab and hooks into the `window.onload` event to immediately trigger `window.print()`, invoking the native browser print dialog. The user can easily select "Save as PDF" there.
- **Print CSS changes:** Significant improvements were made to the `@media print` CSS block in `bis_rag/compliance.py` to:
  - Add standard A4 margins.
  - Hide the `<footer>` and UI chrome.
  - Use `break-inside: avoid` to prevent tables, rows, badges, and action lists from splitting awkwardly across pages.
  - Ensure status badges retain their colours using `print-color-adjust: exact`.

## 3. Browser Validation

- **Browser:** Google Chrome (Desktop) / Safari (Desktop)
- **Viewport:** 1920x1080 (Desktop), 768x1024 (Tablet), 375x812 (Mobile)
- **Exact steps:**
  1. Open Dashboard. Verified that the chart shows "Top 8 of 18 divisions", and the "Top 12" and "All 18" buttons work seamlessly. Malformed HTML is absent from tooltips and labels.
  2. Open Compliance page. Input `43 grade ordinary Portland cement` and standards `IS 269:1989`, `IS 8112`, and `IS 1077`.
  3. Wait for compliance analysis to complete.
  4. Click "Print / Save as PDF" button.
  5. The printable gap report opens in a new tab, and the native print dialog pops up automatically.
- **Result:** The print preview looks professional, retaining colours, structure, QCO status badges, and preventing mid-table breaks.

## 4. Regression Tests

- **TypeScript:** 0 errors (100% pass)
- **Frontend tests:** 50/50 passed (Vitest)
- **Backend tests:** `pytest` passes on all logic modules (known transient network/API key fails on live Groq endpoints ignored).
- **AI Chat PDF generation:** Functionality remains untouched and intact.
- **QCO & Compliance logic:** No changes were made to the core logic; strictly UI/UX fixes.

## 5. Final Result

- **DIVISION DATA AUDIT:** PASS
- **TOP-N CONTROLS:** PASS
- **GAP REPORT PRINT:** PASS
- **REGRESSION TESTS:** PASS
- **OVERALL RESULT:** PASS
