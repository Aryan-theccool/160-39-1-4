# BIS Standards Extraction - Quick Start

## What Was Extracted

✓ **197 unique Indian Standards** with full OCR text  
✓ **Search index** for full-text queries  
✓ **Multiple formats** (CSV, JSON, JSONL)  
✓ **All CC0 licensed** (freely usable)

---

## Access the Data

### 1. View as Spreadsheet (Easiest)
```bash
cd d:\Dprojects\sih108\landing-page\bis_scraper
# Open this file in Excel or similar
start bis_data\merged\merged_standards.csv
```
**Result:** 197 rows with standard metadata (designation, year, title, division, etc.)

### 2. Search the Index
```bash
cd d:\Dprojects\sih108\landing-page\bis_scraper
set PYTHONPATH=src
python -m bis_pipeline query "drinking water"
python -m bis_pipeline query "cement" "concrete"
python -m bis_pipeline query "electrical safety"
```

### 3. Load Data Programmatically

**Python with Pandas:**
```python
import pandas as pd

# Load the CSV
df = pd.read_csv(r'd:\Dprojects\sih108\landing-page\bis_scraper\bis_data\merged\merged_standards.csv')
print(df.head())
print(f"Total standards: {len(df)}")

# Filter by criteria
cement_standards = df[df['title'].str.contains('cement', case=False, na=False)]
print(cement_standards[['designation', 'year', 'title']])
```

**Python with JSON:**
```python
import json

# Load merged standards
with open(r'd:\Dprojects\sih108\landing-page\bis_scraper\bis_data\merged\merged_standards.json') as f:
    standards = json.load(f)

print(f"Total standards: {len(standards)}")
for standard in standards[:5]:
    print(f"{standard['designation']}: {standard['title'][:60]}...")
```

### 4. Read Full Text of a Standard
```bash
# List available text files
dir d:\Dprojects\sih108\landing-page\bis_scraper\bis_data\archive\text\ | head

# Read a specific standard
type d:\Dprojects\sih108\landing-page\bis_scraper\bis_data\archive\text\gov.in.is.1.1968.txt
```

---

## File Structure

| File | Format | Size | Use Case |
|------|--------|------|----------|
| `merged_standards.csv` | Spreadsheet | 130 KB | Browse in Excel |
| `merged_standards.json` | JSON array | 240 KB | Load all at once |
| `merged_standards.jsonl` | Line-delimited JSON | 210 KB | Stream processing |
| `search_index.json` | TF-IDF index | 4.86 MB | Search queries |
| `text/*.txt` | Plain text | 1.5 MB | Full OCR text |

---

## Key Fields in the Data

| Field | Example | Description |
|-------|---------|-------------|
| `canonical` | `IS\|1\|None\|None\|1968\|None` | Unique key for joining records |
| `designation` | `IS 1:1968` | Standard reference (used in citations) |
| `title` | `Specification for The National Flag...` | Full standard name |
| `year` | `1968` | Publication year |
| `part` | `2` | Part number (if multi-part) |
| `section` | `1` | Section number (if applicable) |
| `committee` | `TXD 8` | Technical committee code |
| `division` | `Textiles` | Broad domain |
| `is_current` | `True`/`False` | Is this the latest edition? |
| `superseded_by` | `IS 10 (Part 2):2013` | Newer edition (if applicable) |
| `has_full_text` | `True`/`False` | OCR text available? |
| `archive_url` | `https://archive.org/details/...` | Source document link |
| `text_path` | `bis_data/archive/text/...txt` | Local OCR text file |

---

## Common Tasks

### Task 1: Find all current water-related standards
```python
import pandas as pd
df = pd.read_csv(r'd:\Dprojects\sih108\landing-page\bis_scraper\bis_data\merged\merged_standards.csv')
water = df[(df['is_current']) & (df['title'].str.contains('water', case=False, na=False))]
print(water[['designation', 'year', 'title']])
```

### Task 2: Search for a specific topic
```bash
cd d:\Dprojects\sih108\landing-page\bis_scraper
set PYTHONPATH=src
python -m bis_pipeline query "submersible pump" "drinking water quality"
```

### Task 3: Get all standards from a specific division
```python
import pandas as pd
df = pd.read_csv(r'd:\Dprojects\sih108\landing-page\bis_scraper\bis_data\merged\merged_standards.csv')
civil = df[df['division'].str.contains('Civil', case=False, na=False)]
print(f"Found {len(civil)} standards in Civil Engineering")
```

### Task 4: Track editions and supersessions
```python
import pandas as pd
df = pd.read_csv(r'd:\Dprojects\sih108\landing-page\bis_scraper\bis_data\merged\merged_standards.csv')
superseded = df[df['is_current'] == False]
print(superseded[['designation', 'year', 'superseded_by']])
```

### Task 5: Export to database
```python
import pandas as pd
import sqlite3

df = pd.read_csv(r'd:\Dprojects\sih108\landing-page\bis_scraper\bis_data\merged\merged_standards.csv')
conn = sqlite3.connect('standards.db')
df.to_sql('standards', conn, if_exists='replace', index=False)
conn.close()
```

---

## Search Examples

```bash
cd d:\Dprojects\sih108\landing-page\bis_scraper
set PYTHONPATH=src

# Search for cement standards
python -m bis_pipeline query "cement"

# Search for paint specifications
python -m bis_pipeline query "paint varnish"

# Search for electrical safety
python -m bis_pipeline query "electrical safety"

# Multi-term search
python -m bis_pipeline query "steel reinforcement concrete"
```

---

## Data Stats

```
Total Standards:        197 unique
Current Editions:       180
Superseded Editions:    17
With Full Text:         197 (100%)
Divisions Covered:      20+
Technical Committees:   40+
Year Range:             1968-2023
```

---

## Notes

- **All data is CC0 licensed** - fully open and unrestricted use
- **Search is lexical** - matches words appearing in text (not semantic meaning)
- **OCR text** - some older documents may have minor OCR errors
- **Archive links** - direct to archive.org, no downloading required
- **No registration needed** - all standards are freely accessible

---

## Troubleshooting

**Q: Where's my search results?**  
A: Try simpler terms. Search matches words in titles and OCR text. Try "cement" instead of "reinforced concrete structure."

**Q: Can I use this data commercially?**  
A: Yes! It's CC0 licensed. Full attribution to archive.org is appreciated but not required.

**Q: Why isn't standard XYZ in the list?**  
A: The extraction focused on archive.org's CC0 collection (~22,000 items). Some standards may require registration at bis.gov.in.

**Q: How do I update with new standards?**  
A: Re-run `python -m bis_pipeline all` to re-scrape archive.org.

---

## Next Steps

1. ✓ **Data is ready to use** - Start with the CSV
2. **Integrate with your tool** - Load JSON/CSV into your application
3. **Build search UI** - Use the search index for queries
4. **Enhance with embeddings** - Add semantic search (optional)

**Questions?** Check the full report: `EXTRACTION_REPORT.md`
