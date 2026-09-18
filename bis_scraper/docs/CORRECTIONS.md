# What was wrong with the original build guide

Every claim below was checked on 2026-09-17 against the live services. Where a
claim could not be checked from this environment, that is stated explicitly.

The guide's overall shape was right — three sources, one merged dataset, a
vector index. But three of its four components could not have produced data,
and the one that could have was pointed at the wrong endpoint. Details, with
evidence, below.

---

## 1. Scraper 1 — the BIS portal URL does not exist

**Claim:** `SEARCH_URL = "https://standards.bis.gov.in/standardlist"`, scraped
by paginating `?page=N` and selecting `div.standard-card`.

**Actual:** that URL returns BIS's 404 page:

```
GET https://standards.bis.gov.in/standardlist
-> "BIS - Bureau of Indian Standards"
   ![404 Page not found]  Page Not Found!
```

The site root redirects to `https://standards.bis.gov.in/website`, which is a
JavaScript-driven application. Its search page is:

```
https://standards.bis.gov.in/website/know-your-standards
  "Search Indian Standards (IS) by Number or Keywords"
  "Results will appear here"
```

"Results will appear here" means results are fetched by XHR and rendered
client-side. There is no `div.standard-card` in the HTML to select, and no
`?page=N` to paginate. Every CSS selector in `parse_standards_page`
(`.is-number`, `.standard-title`, `.status-badge`, `.price-india`, ...) is
invented.

**Worse, the catalogue is not enumerable by scraping at all.** BIS's own
homepage links standard detail pages of the form:

```
/website/standard-details?encryptedId=eyJpdiI6IllkL3E3d3pB...&standardNumber=SP%207:2026
```

That `encryptedId` is a base64 Laravel encrypted payload (`{"iv":...,"value":...,"mac":...,"tag":...}`).
You cannot enumerate the catalogue without the server-side key. A scraper that
walks pages 1..N will never reach the data.

**Also false:** the premise that free standards are identifiable by a listed
price of `₹0.00`. BIS's own FAQ says:

> Indian Standards can be accessed from BIS website www.bis.gov.in under the
> tab "Standards > Download Indian Standards" which will direct you to the
> Standards BIS portal: `https://standardsbis.bsbedge.com/`. You can register
> on this portal and then login to **download Indian Standards for free**.
> International (ISO) standards adopted by BIS can also be downloaded on payment.

So Indian Standards are free-after-registration, not free-by-price-tag, and
they live on a BSB Edge portal — not on `standards.bis.gov.in`.

**What this repo does instead:** `mandatory.py` scrapes BIS's server-rendered
compulsory-certification tables from www.bis.gov.in (187 QCOs covering 769
products), which is real HTML with real IS numbers in it. Portal metadata can
still be merged in via `merge --portal-json` if you obtain an export.

---

## 2. Scraper 2 — right idea, wrong API usage, and OCR is unnecessary

**What was right:** archive.org's `gov.in.is.*` collection is real and is the
single best source for this project. Confirmed:

```
GET https://archive.org/advancedsearch.php?q=identifier:gov.in.is.*&rows=5&output=json
-> "numFound": 22025
   {"identifier":"gov.in.is.11367.1985",
    "title":"IS 11367: Glossary of terms relating to textile materials for aerospace purposes"}
   {"identifier":"gov.in.is.12970.3.2.1992", ...}
   {"identifier":"gov.in.is.104.1979", "title":"IS 104: Ready mixed paint, brushing, zinc chrome, priming"}
```

22,025 items. Provenance from item metadata:

```json
"contributor": "Public.Resource.Org",
"creator": "Bureau of Indian Standards",
"licenseurl": "http://creativecommons.org/publicdomain/zero/1.0/",
"rights": "Published under the auspices of the Right to Information Act 2005"
```

This is Carl Malamud's upload, CC0-licensed. That matters: the corpus is
legally usable, which the BIS portal data is not.

**Bug — the `internetarchive` API was misused in three places:**

1. `ia.search_items(...)` yields `SearchResult` **objects**, not dicts. The
   guide's `item['identifier']` raises `TypeError`.
2. `item.files` yields `File` **objects**, not dicts. `f.get('format')` raises
   `AttributeError`.
3. `metadata.get('downloads', 0)` — `downloads` is not in item metadata; it
   comes from the separate stats API, so this silently returned 0 always.

**Bug — `sorts=['downloads desc']`** is not valid for `advancedsearch.php`'s
sort syntax and would have errored or been ignored.

**Missed — the `description` field is the richest metadata in the corpus**, and
the guide never looked at it. It carries exactly the structured fields the plan
wanted to scrape out of BIS's portal:

```
Name of Standards Organization: Bureau of Indian Standards (BIS)
Division Name: Textiles
Section Name: Textile Materials for Aerospace Purposes (TXD 13)
Designator of Legally Binding Document: IS 11367
Title of Legally Binding Document: Glossary of terms relating to textile materials...
Number of Amendments: 1
Equivalence:  Superceding:  Superceded by: ...
```

Committee code, amendment count and supersession — all present, all clean, no
OCR involved. `archive_scraper.parse_description_fields` extracts them.

**Biggest miss — no PDF parsing or OCR is needed.** Every item already ships a
plain-text OCR derivative:

```json
{"name": "is.11367.1985.pdf",      "format": "Text PDF", "size": "1725492"}
{"name": "is.11367.1985_djvu.txt", "format": "DjVuTXT",  "size": "24585"}
```

The `_djvu.txt` is full text at ~1/70th the size of the PDF, produced by
archive.org's own pipeline. Downloading PDFs and running PyMuPDF over them
reproduces that work slowly and pointlessly. `fetch_text` gets the text
derivative directly; PDFs are opt-in (`--pdfs`).

---

## 3. Scraper 3 — the source is access-restricted and cannot be downloaded

**Claim:** download `https://archive.org/download/bis2005completec0000vari/bis2005completec0000vari.pdf`
and OCR 246 pages with Tesseract (~1 hour).

**Actual:** the item exists, but it is a controlled-digital-lending item. Its
file list marks the content derivatives `"private": "true"`:

```json
{"name": "bis2005completec0000vari.pdf",   "format": "Text PDF", "private": "true"}
{"name": "bis2005completec0000vari_hocr.html", "format": "hOCR", "private": "true"}
{"name": "bis2005completec0000vari_chocr.html.gz", "format": "chOCR", "private": "true"}
```

It also ships only `LCP Encrypted PDF` and `ACS Encrypted PDF` public
derivatives — the standard archive.org signature of a lending-restricted book.
And requesting the text derivative returns:

```
GET https://dn720409.ca.archive.org/0/items/bis2005completec0000vari/bis2005completec0000vari_djvu.txt
-> 401 Authorization Required  (nginx)
```

The guide's `download_book()` would have written that 401 HTML error page to
`bis2005_catalogue.pdf` and then crashed inside `fitz.open()`. No amount of
retrying fixes this; it needs a library loan.

Note that the `_djvu.txt` for this item is listed *without* a `private` flag
and still 401s — which is why `is_access_restricted` checks both archive.org's
`access-restricted-item` metadata flag **and** whether any public content
derivative exists, rather than trusting the per-file flags alone.

**Also:** BIS's own link for the free-view mandatory standards is dead:

```
GET https://www.bsbedge.com/mandatory-indian-standards
-> Error 404  Page not found
```

And its stated terms were view-only anyway — BIS's 2019 notice says those
standards "should not be downloaded, printed or stored in the form of image
without prior permission from BIS." Building an index out of them would have
been the one legally wrong move in the plan.

**What this repo does instead:** `mandatory.py` parses BIS's compulsory-
certification tables for the IS numbers, then the merger records which of them
have freely licensed full text in the archive.org corpus. Same goal — "which
mandatory standards can I actually read" — from sources that permit it.

---

## 4. The IS-code regex would have corrupted the data

The guide's parser has one line that destroys the corpus:

```python
text = text.replace('|', 'I').replace('0', 'O')  # "clean up common OCR errors"
```

Replacing every digit zero with the letter O turns `IS 10500` into `IS 1O5OO`
and `2020` into `2O2O`. It is applied before the IS-code regex runs, so it
does not clean OCR errors — it *creates* them, in the identifiers themselves.

It is also unnecessary. The archive.org identifiers are mechanically derived
and authoritative (`gov.in.is.10500.2012` → IS 10500:2012), so identifiers
never need to be recovered from OCR text at all.

**The regexes are also structurally wrong.** This one:

```python
r'(IS\s+\d+(?:\s*:\s*(?:Part|Sec|Section)?\s*\d+)*(?:\s*:\s*\d{4})?)\s*[:\-]\s*(.+?)(?=IS\s+\d+|SP\s+\d+|$)'
```

requires a `:` or `-` immediately after the code group, but the code group
already optionally consumes `: 1994`. So `IS 14220 : 1994` cannot match: after
the year is consumed there is no separator left for `\s*[:\-]\s*`. The primary
pattern matches nothing on the most common format in the corpus.

And the `(?=IS\s+\d+|$)` lookahead means titles are extracted up to the *next*
`IS <digits>` anywhere in the text. Run over a real Foreword — which lists
cross-referenced standards — that attributes other standards' titles to the
document being parsed. Real example from IS 11367's `_djvu.txt`:

```
0.3 The following Indian Standards may be referred to ...
    IS : 232-1985  Glossary of textile terms - natural fibres
    IS : 1324-1966 Glossary of textile terms relating to man-made fibre
    IS : 9603-1980 Glossary of terms pertaining to textile processing
```

A naive regex reports IS 232, IS 1324 and IS 9603 as contents of IS 11367.

**What this repo does instead:** `iscode.py` implements a tested grammar that
normalises every BIS spelling to one canonical key:

| input | canonical |
|---|---|
| `IS 302-2-15 : 2009` | `IS\|302\|2\|15\|2009\|None` |
| `is 302 (part 2 / section 15):2009` | `IS\|302\|2\|15\|2009\|None` |
| `IS 232-1985` | `IS 232:1985` (year, not Part 1985) |
| `IS 16103 Part 1: 2012` | `IS 16103 (Part 1):2012` |
| `IS 1 113C7 - 1905` | `None` (rejected, not guessed) |
| `IS 11367 (1985)` | `IS 11367:1985` (year, not Part 1985) |

Those last two rejections are real strings from the corpus. IS 11367's text
layer renders its own designation as `IS 1 113C7 - 1905` and `IS : 11367 . IMS`
— 1985 scanned as 1905, and the number itself mangled. `find_all` is kept
separate from `parse_designation` precisely so cross-references can be
extracted without ever letting OCR text decide what a document *is*.

---

## 5. Dependencies that were never needed

The guide installs `selenium`, `webdriver-manager`, `pytesseract`, `pdf2image`,
`Pillow`, `PyMuPDF` and `internetarchive`. Given the above:

| package | verdict |
|---|---|
| `selenium`, `webdriver-manager` | Unused — imported nowhere in the guide's own code |
| `pytesseract` | Unnecessary — archive.org ships `_djvu.txt` |
| `pdf2image`, `Pillow` | Unnecessary — they exist only to feed pytesseract |
| `PyMuPDF` | Only needed for `--pdfs` |
| `internetarchive` | Optional; `advancedsearch.php` is plain HTTP |
| `openpyxl` | Only for `--xlsx` |

Also `python-dotenv` / `.env` for "BIS login credentials": nothing in the
pipeline authenticates, and the portal that would need credentials
(`standardsbis.bsbedge.com`) is not scraped. Storing unused credentials is
just exposure.

`requirements.txt` in this repo lists the four packages the default path
actually imports, with the rest commented and annotated.

---

## 6. Things the guide got right

Worth keeping:

- Three sources feeding one unified JSON dataset, then an index. Correct
  architecture.
- archive.org needs no API key or login. True.
- `internetarchive-downloader` for bulk transfer with resume and hash
  verification is a good tool. This repo implements the same two properties
  directly (`http.download`): resumable via HTTP `Range`, and verified against
  the md5 archive.org publishes per file.
- Rate limiting and retry logic. Kept, and made correct — retries only on
  408/429/5xx, honouring `Retry-After`.

---

## 7. Legal position

**Corrected 2026-09-17.** An earlier version of this section said BIS's
QCO-mandated standards could not be stored. That conflated two different
platforms, one of which no longer exists.

- **`bsbedge.com/mandatory-indian-standards`** — BIS's 2019 view-only viewer.
  Its terms said standards "should not be downloaded, printed or stored in the
  form of image without prior permission from BIS." **That URL now returns
  404.** Its restrictions died with it and say nothing about the current portal.

- **`standardsbis.bsbedge.com`** — the current portal BIS's own FAQ points to:
  "You can register on this portal and then login to **download Indian Standards
  for free**. International (ISO) standards adopted by BIS can also be
  downloaded on payment." Registration is free; Indian Standards download free;
  files carry FileOpen DRM. This is BIS's sanctioned distribution channel, so
  obtaining standards there is legitimate. What a scraper should not do is
  bulk-mirror it or strip the DRM — those downloads are a per-account
  entitlement.

- **archive.org `gov.in.is.*`** — CC0, explicitly published under the Right to
  Information Act 2005. Indexing and redistributing is fine. A large share of
  the QCO-mandated standards are here; `coverage.py` measures exactly how much.

- **BIS compulsory-certification lists** — BIS's own published pages; using the
  IS numbers and titles is ordinary factual reference.

- **Lending-restricted archive.org items** (the BIS 2005 catalogue) — not
  accessible without a loan. Detected and skipped rather than circumvented.

So the honest split is: most QCO standards are already free to index from the
CC0 corpus, and the remainder are free to *you* after registering — not free to
mirror.

---

## 8. Not verified from this environment

Stated plainly, because it affects how much to trust the run:

- **This sandbox cannot reach the scrape targets.** Its network is allowlisted;
  `pypi.org` returns HTTP 200 while `archive.org`, `bis.gov.in` and even
  `example.com` fail at the TLS layer (`HTTP 000`, curl exit 35). So the
  scrapers were **not** run against the live services here. Everything above
  was verified through a separate web-fetch path, and the scrapers themselves
  are covered by tests that replay captured real API payloads.
- **The live HTML shape of BIS's compulsory-certification tables** was read
  from search-result extracts, not the raw page, and BIS's WordPress markup
  will drift. `parse_tables` reports `tables_seen` / `rows_seen` /
  `rows_with_is` so a silent markup change is visible instead of quietly
  returning nothing.
- **`services.bis.gov.in`** (the "old portal" BIS links to) did not load
  through the fetch path, so its structure is unexamined. It may be the best
  portal target if you want to reverse-engineer an API.
