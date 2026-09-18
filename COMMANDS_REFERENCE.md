# BIS Standards Commands Reference

Quick reference for common operations with the extracted BIS standards.

---

## Opening Files

### View the Main Spreadsheet (Excel)
```bash
start d:\Dprojects\sih108\landing-page\bis_scraper\bis_data\merged\merged_standards.csv
```

### View Documentation
```bash
start EXTRACTION_SUMMARY.txt
start EXTRACTION_QUICKSTART.md
start EXTRACTION_REPORT.md
```

---

## Search Commands

Change to the project directory first:
```bash
cd d:\Dprojects\sih108\landing-page\bis_scraper
set PYTHONPATH=src
```

Then run searches:

### Search for Cement Standards
```bash
python -m bis_pipeline query "cement"
```

### Search for Water/Drinking Water
```bash
python -m bis_pipeline query "drinking water"
python -m bis_pipeline query "water quality"
python -m bis_pipeline query "water treatment"
```

### Search for Electrical Safety
```bash
python -m bis_pipeline query "electrical safety"
```

### Search for Concrete
```bash
python -m bis_pipeline query "concrete"
python -m bis_pipeline query "reinforced concrete"
```

### Search for Steel
```bash
python -m bis_pipeline query "steel"
python -m bis_pipeline query "reinforcement"
```

### Multi-term Search
```bash
python -m bis_pipeline query "submersible pump" "drinking water quality"
python -m bis_pipeline query "paint varnish" "testing methods"
```

---

## View Data

### List All Files in merged/
```bash
dir bis_data\merged\
```

### List All OCR Text Files
```bash
dir bis_data\archive\text\ | head -50
```

### Count Total OCR Files
```bash
dir bis_data\archive\text\ | Measure-Object | Select-Object -ExpandProperty Count
```

### Get Data File Sizes
```bash
Get-ChildItem bis_data\merged\ | Select-Object Name, Length
```

---

## Python Examples

### Load and Display CSV
```python
import pandas as pd

df = pd.read_csv(r'd:\Dprojects\sih108\landing-page\bis_scraper\bis_data\merged\merged_standards.csv')

# View first rows
print(df.head())

# Get info
print(f"Total standards: {len(df)}")
print(df.columns.tolist())
```

### Load and Filter
```python
import pandas as pd

df = pd.read_csv(r'd:\Dprojects\sih108\landing-page\bis_scraper\bis_data\merged\merged_standards.csv')

# Find all cement standards
cement = df[df['title'].str.contains('cement', case=False, na=False)]
print(cement[['designation', 'year', 'title']])

# Find all current standards
current = df[df['is_current'] == True]
print(f"Current standards: {len(current)}")

# Find all superseded standards
superseded = df[df['is_current'] == False]
print(superseded[['designation', 'year', 'superseded_by']])
```

### Load JSON
```python
import json

with open(r'd:\Dprojects\sih108\landing-page\bis_scraper\bis_data\merged\merged_standards.json') as f:
    standards = json.load(f)

print(f"Total standards: {len(standards)}")

# Get first standard
first = standards[0]
print(f"{first['designation']}: {first['title']}")
```

### Read OCR Text of a Standard
```python
# Read a specific standard's OCR text
with open(r'd:\Dprojects\sih108\landing-page\bis_scraper\bis_data\archive\text\gov.in.is.1.1968.txt') as f:
    text = f.read()
    print(f"Text length: {len(text)} characters")
    print(text[:500])  # Print first 500 characters
```

### Export to Database
```python
import pandas as pd
import sqlite3

df = pd.read_csv(r'd:\Dprojects\sih108\landing-page\bis_scraper\bis_data\merged\merged_standards.csv')

conn = sqlite3.connect('standards.db')
df.to_sql('standards', conn, if_exists='replace', index=False)
print("✓ Exported to standards.db")

# Query the database
result = pd.read_sql("SELECT * FROM standards WHERE title LIKE '%cement%'", conn)
print(result)
```

### Filter by Division
```python
import pandas as pd

df = pd.read_csv(r'd:\Dprojects\sih108\landing-page\bis_scraper\bis_data\merged\merged_standards.csv')

# Get all Textiles standards
textiles = df[df['division'].str.contains('Textile', case=False, na=False)]
print(f"Found {len(textiles)} textile standards")

# Get all Civil Engineering standards
civil = df[df['division'].str.contains('Civil', case=False, na=False)]
print(f"Found {len(civil)} civil engineering standards")
```

### Find Standards by Committee
```python
import pandas as pd

df = pd.read_csv(r'd:\Dprojects\sih108\landing-page\bis_scraper\bis_data\merged\merged_standards.csv')

# Get all standards from a specific committee
committee = df[df['committee'] == 'CHD 20']
print(committee[['designation', 'title']])
```

---

## Data Exploration

### Count Standards by Year
```python
import pandas as pd

df = pd.read_csv(r'd:\Dprojects\sih108\landing-page\bis_scraper\bis_data\merged\merged_standards.csv')

# Count by year
by_year = df['year'].value_counts().sort_index()
print(by_year)

# Most recent standards
recent = df.nlargest(10, 'year')[['designation', 'year', 'title']]
print(recent)
```

### Oldest Standards
```python
import pandas as pd

df = pd.read_csv(r'd:\Dprojects\sih108\landing-page\bis_scraper\bis_data\merged\merged_standards.csv')

oldest = df.nsmallest(10, 'year')[['designation', 'year', 'title']]
print(oldest)
```

### Standards with Multiple Parts
```python
import pandas as pd

df = pd.read_csv(r'd:\Dprojects\sih108\landing-page\bis_scraper\bis_data\merged\merged_standards.csv')

# Find multi-part standards
multi_part = df[df['part'].notna()]
print(f"Standards with parts: {len(multi_part)}")
print(multi_part[['designation', 'part', 'title']].head(20))
```

---

## Re-running the Pipeline

### Run Full Extraction (Takes many hours)
```bash
cd d:\Dprojects\sih108\landing-page\bis_scraper
set PYTHONPATH=src
python -m bis_pipeline all --max-items 500
```

### Run Just Archive Scraping
```bash
python -m bis_pipeline archive --max-items 200
```

### Run Just Merging
```bash
python -m bis_pipeline merge
```

### Run Just Indexing
```bash
python -m bis_pipeline index
```

### Run Tests
```bash
python -m pytest
```

---

## Data Info Commands

### Get Directory Size
```bash
dir bis_data\ /s | tail -1
```

### List All Directories
```bash
Get-ChildItem bis_data\ -Recurse -Directory | Select-Object FullName
```

### Find Largest Files
```bash
Get-ChildItem bis_data\ -Recurse -File | Sort-Object -Property Length -Descending | Select-Object -First 10 Name, @{Name="Size MB";Expression={[math]::Round($_.Length/1MB,2)}}
```

---

## Backup & Cleanup

### Backup Data
```bash
# Create backup folder
mkdir backups

# Copy all data
Copy-Item bis_data -Destination backups\bis_data_backup -Recurse
```

### Clean HTTP Cache (saves space)
```bash
# Optional: Remove HTTP cache if space is needed
Remove-Item bis_data\http_cache\* -Force -Recurse
# Re-run extraction to rebuild cache
```

---

## Useful File Paths

```
# Main data directory
d:\Dprojects\sih108\landing-page\bis_scraper\bis_data\

# Spreadsheet (open in Excel)
bis_data\merged\merged_standards.csv

# JSON formats
bis_data\merged\merged_standards.json
bis_data\merged\merged_standards.jsonl

# Search index
bis_data\index\search_index.json

# OCR texts
bis_data\archive\text\

# Raw archive metadata
bis_data\archive\items.jsonl
```

---

## Troubleshooting

### Python not found
```bash
# Make sure Python is in PATH
python --version

# If not, use full path
C:\Users\aryan\AppData\Local\Python\pythoncore-3.14-64\python.exe --version
```

### Module not found
```bash
# Make sure PYTHONPATH is set
set PYTHONPATH=src

# Verify with
echo %PYTHONPATH%
```

### Search not working
```bash
# Make sure index exists
dir bis_data\index\search_index.json

# If missing, rebuild:
python -m bis_pipeline index
```

---

## Quick One-Liners

Get a random standard:
```bash
PowerShell -Command "Get-Random -InputObject @(Get-ChildItem bis_data\archive\text\*.txt).Name"
```

Count total files:
```bash
Get-ChildItem bis_data\ -Recurse -File | Measure-Object | Select-Object Count
```

Get total size:
```bash
Get-ChildItem bis_data\ -Recurse -File | Measure-Object -Sum -Property Length | Select-Object Sum
```

List standards by year:
```bash
python -c "import pandas as pd; df = pd.read_csv('bis_scraper/bis_data/merged/merged_standards.csv'); print(df['year'].value_counts().sort_index())"
```

---

## Getting Help

- **Overview:** Read `README_EXTRACTION.md`
- **Quick Start:** Read `EXTRACTION_QUICKSTART.md`
- **Full Report:** Read `EXTRACTION_REPORT.md`
- **Summary:** Read `EXTRACTION_SUMMARY.txt`

---

**Last Updated:** September 18, 2026
