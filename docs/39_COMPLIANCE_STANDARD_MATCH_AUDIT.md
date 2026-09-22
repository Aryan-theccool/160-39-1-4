# Compliance Standard Matching Bug Audit — Investigation & Fix Report

## 1. Executive Summary

An audit was conducted to investigate the browser behavior where querying product `"household electrical appliance"` with explicitly supplied standard `"IS 302"` resulted in:
- **Score:** 30/100 (0.30)
- **Status / Grade:** `NON_COMPLIANT`
- **Mandatory Met:** 0
- **Mandatory Missing:** 1 (`IS 302`)
- **Warning:** `1 mandatory standard(s) missing (IS 302)`
- **Action Item:** `Obtain and comply with IS 302 -- mandatory under a Quality Control Order for this product category.`

### Root Cause Analysis
Two distinct root causes were uncovered during the end-to-end data flow trace:

1. **Frontend Draft Uncommitted on Check (Primary UI Cause):**
   - In `bis_web/src/app/compliance/page.tsx`, the "Standards you hold" input stored typed text in `draft` state. Adding it to the `standards` array required pressing `Enter` or clicking the `+` icon button.
   - When a user typed `"IS 302"` directly into the input and clicked the primary **"Check compliance"** button without clicking `+` first, `check()` executed with `standards = []` (empty array).
   - The payload sent to `POST /api/v1/compliance/check` contained `product_description: "household electrical appliance"` and `standards: undefined`.
   - The backend received 0 held standards, matched the product description to mandatory `IS 302`, determined `mandatory_present = []`, and returned `mandatory_missing = ["IS 302"]` with score `0.30` (30% from currency and conflict baseline, 0% from mandatory weight).

2. **Standard Family vs. Part Hierarchy Mismatch (Backend Edge Case):**
   - Quality Control Orders often designate a standard series by its base number (e.g., `IS 302` for *Safety of Household and Similar Electrical Appliances*).
   - In practice, manufacturers and users hold specific parts (e.g., `IS 302-1`, `IS 302 (Part 1)`, `IS 302-2-3`).
   - `yearless_key("IS 302-1")` produces `"is 302 (part 1)"`, whereas `QCOEntry.key` is `"is 302"`.
   - In `ComplianceChecker.analyze`, strict key equality `entry.key in present_keys` evaluated `"is 302" in {"is 302 (part 1)"}` to `False`, flagging `IS 302` as missing even when the user held a valid part of the `IS 302` standard.

---

## 2. End-to-End Data Flow Trace

```
User Input in Browser:
┌────────────────────────────────────────────────────────┐
│ Product: "household electrical appliance"               │
│ Draft Standard: "IS 302"                               │
│ Click: [Check compliance]                              │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Frontend: bis_web/src/app/compliance/page.tsx          │
│ • Fix applied: Auto-commits pending `draft` to array   │
│ • effectiveStandards: ["IS 302"]                       │
│ • Payload: { product_description: "...", standards: ["IS 302"] } │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ FastAPI Router: bis_api/routers/compliance.py          │
│ • ComplianceRequest validation: standards = ["IS 302"] │
│ • Invokes: ComplianceChecker.analyze(product, standards)│
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Compliance Engine: bis_rag/compliance.py               │
│ 1. Resolve Standards:                                  │
│    "IS 302" -> ResolvedStandard(designation="IS 302",   │
│                                 key="is 302")          │
│ 2. Expected QCO Standards:                             │
│    match_product("household electrical appliance")     │
│    -> QCOEntry(key="is 302", designation="IS 302")     │
│ 3. Match Evaluation:                                   │
│    present_keys = {"is 302"}                           │
│    entry.key ("is 302") in present_keys -> TRUE        │
│ 4. Score Computation:                                  │
│    mandatory_weight (0.7) * (1/1) = 0.70               │
│    currency_weight  (0.2) * 1.0   = 0.20               │
│    conflicts_weight (0.1) * 1.0   = 0.10               │
│    Total Compliance Score = 1.00 (100/100)             │
│    Grade: FULLY COMPLIANT                              │
└────────────────────────────────────────────────────────┘
```

---

## 3. Discrepancy & Logic Audit

### A. Frontend Draft State Handling
- **Before Fix:** If a user typed a standard into the input box and clicked `Check compliance` without clicking `+`, `userStandards` was `[]`.
- **After Fix:** `check()` now checks `draft.trim()`. If non-empty, it automatically appends the draft to `userStandards`, updates React state, and clears the draft input before sending the API request.

### B. Standard Family Hierarchy Matching in `ComplianceChecker`
- **Before Fix:** `entry.key in present_keys` strictly compared `"is 302"` against set entries. Part specifications such as `IS 302-1`, `IS 302 (Part 1)`, or `IS 302-2-3` were not recognized as satisfying base requirement `IS 302`.
- **After Fix:** When a mandatory QCO requirement specifies a standard family (i.e. `part is None` and `section is None` such as `IS 302`), holding any recognized part of that family (`IS 302 (Part 1)`, `IS 302-2-3`, etc.) satisfies the requirement.

---

## 4. Comprehensive Testing Matrix

The following matrix documents the verification across the 5 target standards and their sub-variants:

| Product Category | Input Standard | Score | Grade | Mandatory Met | Mandatory Missing | Status |
| :--- | :--- | :---: | :--- | :---: | :---: | :---: |
| **household electrical appliance** | *None / Empty* | **0.30** | `NON-COMPLIANT` | `[]` | `['IS 302']` | Expected Baseline |
| **household electrical appliance** | `"IS 302"` | **1.00** | `FULLY COMPLIANT` | `['IS 302']` | `[]` | Verified |
| **household electrical appliance** | `"is 302"` (lowercase) | **1.00** | `FULLY COMPLIANT` | `['IS 302']` | `[]` | Verified |
| **household electrical appliance** | `"IS 302:1988"` (year) | **1.00** | `FULLY COMPLIANT` | `['IS 302']` | `[]` | Verified |
| **household electrical appliance** | `"IS 302-1"` (part) | **1.00** | `FULLY COMPLIANT` | `['IS 302']` | `[]` | Verified |
| **household electrical appliance** | `"IS 302 (Part 1)"` | **1.00** | `FULLY COMPLIANT` | `['IS 302']` | `[]` | Verified |
| **household electrical appliance** | `"IS 302 Part 1"` | **1.00** | `FULLY COMPLIANT` | `['IS 302']` | `[]` | Verified |
| **household electrical appliance** | `"IS 302-2-3"` (part/sec) | **1.00** | `FULLY COMPLIANT` | `['IS 302']` | `[]` | Verified |
| **household electrical appliance** | `"IS 302 (Part 2/Sec 3)"` | **1.00** | `FULLY COMPLIANT` | `['IS 302']` | `[]` | Verified |
| **33 grade ordinary Portland cement** | `"IS 269"` | **1.00** | `FULLY COMPLIANT` | `['IS 269']` | `[]` | Verified |
| **33 grade ordinary Portland cement** | `"IS 269:2015"` | **1.00** | `FULLY COMPLIANT` | `['IS 269']` | `[]` | Verified |
| **PVC insulated cables for voltages up to 1100 V** | `"IS 694"` | **1.00** | `FULLY COMPLIANT` | `['IS 694']` | `[]` | Verified |
| **PVC insulated cables for voltages up to 1100 V** | `"IS 694:2010"` | **1.00** | `FULLY COMPLIANT` | `['IS 694']` | `[]` | Verified |
| **high strength deformed steel bars** | `"IS 1786"` | **1.00** | `FULLY COMPLIANT` | `['IS 1786']` | `[]` | Verified |
| **high strength deformed steel bars** | `"IS 1786:2008"` | **1.00** | `FULLY COMPLIANT` | `['IS 1786']` | `[]` | Verified |
| **footwear** | `"IS 15298"` | **1.00** | `FULLY COMPLIANT` | `['IS 15298']` | `[]` | Verified |
| **footwear** | `"IS 15298 (Part 2)"` | **1.00** | `FULLY COMPLIANT` | *Matches QCO Part* | `[]` | Verified |

---

## 5. Changes Applied

1. **Frontend Form Auto-Commit:**
   - File: `bis_web/src/app/compliance/page.tsx`
   - Modified `check()` to commit any pending non-empty `draft` input into `userStandards` and update state before calling `complianceCheck()`.

2. **Backend Standard Family Matching:**
   - File: `bis_scraper/src/bis_rag/compliance.py`
   - Enhanced `mandatory_present` resolution to recognize family-level mandatory standard fulfillment when a user holds specific parts (`IS 302-1`, `IS 302-2-3`, `IS 302 (Part 1)`).

3. **Regression Tests:**
   - Verified that all 75 compliance unit & integration tests pass with 0 regressions.
