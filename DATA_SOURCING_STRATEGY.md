# BIS Standards Data Sourcing Strategy

## Problem
Current corpus: **197 testing/equipment standards** (IS 10000-10069 range)
Missing: **Procurement/material standards** users actually need
- IS 8112 (43 OPC cement) - CRITICAL
- IS 10500 (drinking water) - CRITICAL
- IS 1786 (steel reinforcement) - CRITICAL
- IS 456 (concrete) - CRITICAL
- IS 3025 (water testing methods) - HIGH
- IS 269 (ordinary portland cement) - HIGH
- IS 2751 (structural steel)
- IS 1239 (mild steel pipes)
- IS 455 (portland slag cement)
- IS 12269 (53 grade cement)
- And 100+ more...

**Goal:** Bring in 300-500 more standards covering procurement, materials, civil engineering, water, steel, construction.

---

## Data Source Options

### Option 1: BIS Archive.org (Current Method - Limited)
**Status:** Already scraping  
**URL:** https://archive.org/details/bis_standards  
**Current yield:** 197 standards (mostly testing equipment)  
**Problem:** Archive.org may not have complete catalog; limited to what's already indexed  
**Solution:** Expand search across multiple archive collections

**Action:**
```bash
# Search for specific standards on archive.org
curl -s "https://archive.org/advancedsearch.php?q=IS+8112&fl=identifier&output=json" | jq

# Batch download known standards
# https://archive.org/download/bis_standards_IS_8112_2013/
# https://archive.org/download/bis_standards_IS_10500_2012/
# https://archive.org/download/bis_standards_IS_1786_2008/
```

**Time:** 2-3 days to locate and verify all standards

---

### Option 2: BIS Official Portal (RECOMMENDED)
**Source:** https://bis.gov.in/  
**Method:** Official BIS standards catalog  
**Coverage:** 100% of all published standards (1000+)  
**Problem:** No direct API; requires scraping or manual download

**What to scrape:**
- Title, Designation (IS XXXX:YYYY)
- Scope/Specification
- PDF links (if available publicly)
- Amendment dates
- Status (current/superseded)

**Action:**
```bash
# BIS publishes searchable catalog
# 1. Go to https://bis.gov.in/
# 2. Search by sector (Civil, Steel, Water, Cement, etc.)
# 3. Extract standard metadata and categorize

# Scrape BIS search results
python -c "
import requests
from bs4 import BeautifulSoup

# BIS catalog search
sectors = ['Civil', 'Steel', 'Water', 'Cement', 'Materials']
for sector in sectors:
    url = f'https://bis.gov.in/index.php?q=search&s={sector}'
    response = requests.get(url, timeout=10)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Extract standards
    standards = soup.find_all('div', {'class': 'standard-item'})
    for std in standards:
        designation = std.find('span', {'class': 'designation'}).text
        title = std.find('span', {'class': 'title'}).text
        print(f'{designation}: {title}')
"
```

**Time:** 3-5 days (with BIS server rate limiting)  
**Risk:** BIS may block scraping; may need to contact them for data export

---

### Option 3: Government E-Procurement Portals
**Sources:**
- GeM (Government e-Marketplace): https://gem.gov.in/
- NPROCURE: https://www.nprocure.gov.in/
- Udyam Portal (MSME): https://udyamregistrar.gov.in/

**Why:** These portals link to applicable BIS standards in procurement tenders  
**Yield:** Real-world usage patterns + standards mapping

**Action:**
```bash
# Scrape tender documents from GeM
# Extract referenced standards from technical specifications

# Example: Mining equipment tender
# References: IS 8112 (cement), IS 456 (concrete), IS 1786 (steel)

# Python script to extract
from selenium import webdriver
from bs4 import BeautifulSoup

driver = webdriver.Chrome()
driver.get('https://gem.gov.in/search')

# Search for tenders by category
categories = ['cement', 'steel', 'water', 'construction']
for cat in categories:
    search_input = driver.find_element("name", "search")
    search_input.send_keys(cat)
    search_input.submit()
    
    # Extract tender details
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    tenders = soup.find_all('div', {'class': 'tender'})
    # Extract IS references...
```

**Time:** 1-2 weeks  
**Data quality:** ⭐⭐⭐⭐ (real usage patterns)

---

### Option 4: Ministry/Department Direct Contact
**Contact:** Ministry of Consumer Affairs, DoCA  
**Email:** standards@bis.gov.in  
**Request:** Bulk export of standards database

**What to request:**
- Complete standards catalog (CSV/Excel)
- All designations with publication dates
- Sector classification
- Current/superseded status
- PDF links (if shareable)

**Time:** 5-10 days (bureaucratic delays expected)  
**Data quality:** ⭐⭐⭐⭐⭐ (official source)

---

### Option 5: ISO Standards Database Mapping
**Source:** https://www.iso.org/ics/  
**Insight:** ISO Codes map to Indian Standards  
- ISO 9001 → IS 9001
- ISO 286 → IS 286
- ISO 14644 → IS 14644 (cleanrooms)

**Action:**
```bash
# Fetch ISO ICS (Classification) structure
# Map to Indian Standards equivalents
# Download ICS metadata

curl -s "https://www.iso.org/ics/download/" > ics_structure.xml
# Parse and map to IS equivalents
```

**Time:** 1-2 days  
**Yield:** 800+ standards mapped from ISO

---

### Option 6: GitHub/Open Data Sources
**Search repositories:**
- https://github.com/topics/indian-standards
- https://github.com/topics/bis-standards
- Open data initiatives (data.gov.in)

**Likely yield:** Community-compiled lists, but low quality  
**Time:** 1 day (screening required)

---

## Recommended Approach (Hybrid)

### Phase 1: Quick Wins (Week 1)
1. **Archive.org expansion** (2 days)
   - Search for known missing standards
   - Download PDFs for: IS 8112, IS 10500, IS 1786, IS 456, IS 3025
   - Extract text with OCR if needed

2. **Direct Ministry Request** (1 day to send)
   - Email BIS requesting standards export
   - Ask for: CSV with all standards, designations, status, scope

3. **Tender portal scraping** (2-3 days)
   - GeM + NPROCURE scraping script
   - Extract "applicable standards" from 100 procurement tenders
   - Map to standards

### Phase 2: Bulk Data (Week 2-3)
4. **BIS portal scraping** (3-5 days once approval/data received)
   - Full catalog from bis.gov.in
   - Parse by sector (Civil, Steel, Water, Materials, etc.)

5. **ISO mapping** (1-2 days)
   - Cross-reference with ISO to fill gaps

### Phase 3: Data Enrichment (Week 3-4)
6. **PDF text extraction**
   - Parse downloaded PDFs for scope, key terms, keywords
   - Build richer metadata (not just designation + title)

---

## Implementation: Archive.org Expansion (Fastest)

### Step 1: Identify Missing Standards
```python
import requests
import json

# Known high-priority standards
missing_standards = [
    'IS 8112:2013',    # 43 OPC
    'IS 10500:2012',   # Drinking water
    'IS 1786:2008',    # Steel bars
    'IS 456:2000',     # Concrete
    'IS 3025:2023',    # Water testing
    'IS 269:2015',     # OPC general
    'IS 12269:2013',   # 53 OPC
    'IS 455:2015',     # PSC
    'IS 2751:2007',    # Structural steel
    'IS 1239:2004',    # MS pipes
    # ... add 50+ more
]

# Search archive.org for each
for std in missing_standards:
    designation = std.replace(':', '_')
    url = f"https://archive.org/advancedsearch.php?q='{designation}'&fl=identifier,title&output=json"
    try:
        resp = requests.get(url, timeout=5)
        results = resp.json()['response']['docs']
        print(f"{std}: Found {len(results)} results")
        for doc in results[:3]:
            print(f"  → {doc['identifier']}")
    except:
        print(f"{std}: Not found")
```

### Step 2: Download & Extract
```python
import subprocess
import os

# Download identified standards
for identifier in found_identifiers:
    # Check if PDF available
    pdf_url = f"https://archive.org/download/{identifier}/{identifier}.pdf"
    
    # Try direct download
    result = subprocess.run(
        ['curl', '-I', pdf_url],
        capture_output=True,
        timeout=5
    )
    
    if result.returncode == 0:
        # Download PDF
        subprocess.run(['wget', '-q', pdf_url, '-O', f'pdf/{identifier}.pdf'])
        
        # Extract text with pdftotext or PyPDF
        os.system(f"pdftotext pdf/{identifier}.pdf txt/{identifier}.txt")
        
        print(f"✓ Downloaded {identifier}")
```

### Step 3: Parse & Index
```python
import os
import re
from pathlib import Path

standards_data = {}

for txt_file in Path('txt').glob('*.txt'):
    with open(txt_file) as f:
        text = f.read()
    
    # Extract key info
    # IS XXXX:YYYY format
    match = re.search(r'IS\s+(\d+)\s*\(?\s*Part\s+(\d+)?\)?\s*:\s*(\d{4})', text[:500])
    if match:
        designation = match.group(0)
        
        # Extract title (usually first line or after "Title:")
        title = re.search(r'(?:Title|Specification):\s*(.+)', text[:1000])
        if title:
            title_text = title.group(1).strip()[:200]
        
        standards_data[designation] = {
            'file': txt_file.name,
            'title': title_text,
            'text': text[:2000],  # First 2000 chars for indexing
            'source': 'archive.org'
        }

# Save to JSON
with open('standards_imported.json', 'w') as f:
    json.dump(standards_data, f, indent=2)
```

---

## Cost/Effort Estimate

| Method | Time | Cost | Data Quality | Feasibility |
|--------|------|------|-------------|-------------|
| Archive.org expand | 2-3 days | $0 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| BIS direct request | 1 week | $0 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| GeM scraping | 1-2 weeks | $0 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| BIS portal scraping | 1-2 weeks | $0 | ⭐⭐⭐⭐ | ⭐⭐ (may block) |
| ISO mapping | 2-3 days | $0 | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Hybrid (all)** | **3-4 weeks** | **$0** | **⭐⭐⭐⭐⭐** | **⭐⭐⭐⭐** |

---

## Recommended Next Step: Archive.org Quick Scan

Let me scan Archive.org right now for the 10 most critical missing standards:

```
1. IS 8112 (43 OPC cement)
2. IS 10500 (drinking water)
3. IS 1786 (steel bars)
4. IS 456 (concrete)
5. IS 3025 (water testing)
6. IS 269 (OPC general)
7. IS 12269 (53 OPC)
8. IS 455 (PSC)
9. IS 2751 (structural steel)
10. IS 1239 (MS pipes)
```

**Shall I start this scan and attempt to locate these standards on archive.org?**

---

## Decision for You

Choose one:

**A. Do the quick Archive.org scan** (2 hours)
- Try to find top 10 missing standards
- See if PDFs are available
- Report findings

**B. Send official request to BIS** (24 hours wait)
- Email: standards@bis.gov.in
- Request: Complete standards database export
- Likely to get CSV with all 1000+ standards

**C. Hybrid approach** (Start both immediately)
- Start Archive.org scan in parallel
- Send BIS request
- Begin GeM scraping while waiting

**D. Something else?** (Tell me)

Your choice?
