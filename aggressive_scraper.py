#!/usr/bin/env python3
"""
Aggressive BIS Standards Scraper
- Scrape archive.org directly for all IS standards
- Scrape BIS portal for catalog
- Parallel downloads
- OCR extraction
- Direct integration into bis_data
"""

import requests
import json
import time
import os
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger(__name__)

# Archive.org API
ARCHIVE_API = "https://archive.org/advancedsearch.php"
ARCHIVE_DOWNLOAD = "https://archive.org/download"

# BIS standards to scrape (most critical)
CRITICAL_STANDARDS = {
    # Cement
    'IS 8112:2013': 'OPC 43 grade cement',
    'IS 269:2015': 'OPC general',
    'IS 12269:2013': 'OPC 53 grade',
    'IS 455:2015': 'PSC slag cement',
    
    # Concrete
    'IS 456:2000': 'Plain and reinforced concrete',
    
    # Steel
    'IS 1786:2008': 'Steel reinforcement bars',
    'IS 2751:2007': 'Structural steel',
    'IS 800:2007': 'Steel structures code',
    'IS 1161:2014': 'Structural steel tubes',
    'IS 1239:2004': 'MS pipes structural',
    'IS 226:2012': 'Steel for structural use',
    
    # Water
    'IS 10500:2012': 'Drinking water',
    'IS 3025:2023': 'Water testing methods',
    'IS 1172:2012': 'Stainless steel water tanks',
    'IS 2030:2012': 'Water storage tanks',
    
    # Safety & Construction
    'IS 4014:2003': 'Lift safety',
    'IS 13620:2022': 'RCC repair code',
    'IS 1905:2016': 'Stone masonry',
    'IS 2250:2012': 'Brick masonry',
    'IS 1077:2016': 'Burnt clay bricks',
}

def search_archive_org(designation):
    """Search archive.org for standard."""
    try:
        # Search with multiple query formats
        queries = [
            f'"{designation}"',
            designation.replace(':', '_'),
            f'IS {designation.split(":")[0]}',
        ]
        
        for query in queries:
            params = {
                'q': f'(identifier:gov_in_is* OR identifier:*bis*) AND {query}',
                'fl': 'identifier,title,date,mediatype',
                'output': 'json',
                'rows': 10
            }
            
            try:
                resp = requests.get(ARCHIVE_API, params=params, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    docs = data.get('response', {}).get('docs', [])
                    if docs:
                        return docs[0]  # Return first match
            except:
                continue
        
        return None
    except Exception as e:
        log.error(f"Archive search error for {designation}: {e}")
        return None

def download_from_archive(identifier):
    """Download document from archive.org."""
    try:
        # Try to get PDF
        pdf_url = f"{ARCHIVE_DOWNLOAD}/{identifier}/{identifier}.pdf"
        resp = requests.head(pdf_url, timeout=5)
        if resp.status_code == 200:
            return pdf_url
        
        # Try DJVU
        djvu_url = f"{ARCHIVE_DOWNLOAD}/{identifier}/{identifier}_djvu.txt"
        resp = requests.head(djvu_url, timeout=5)
        if resp.status_code == 200:
            return djvu_url
        
        # Try to get any text file
        for filename in [f"{identifier}.txt", f"{identifier}_original.txt"]:
            url = f"{ARCHIVE_DOWNLOAD}/{identifier}/{filename}"
            resp = requests.head(url, timeout=5)
            if resp.status_code == 200:
                return url
        
        return None
    except:
        return None

def extract_text_from_url(url):
    """Download and extract text from URL."""
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.text[:5000]  # First 5000 chars
        return None
    except:
        return None

def scrape_bis_portal():
    """Scrape BIS official website for standards list."""
    try:
        log.info("Scraping BIS portal...")
        
        # BIS standards search page
        url = "https://bis.gov.in/index.php"
        
        standards_found = []
        
        # Search for key standards
        search_terms = [
            'cement', 'concrete', 'steel', 'water', 'safety',
            'reinforcement', 'structural', 'drinking', 'construction'
        ]
        
        for term in search_terms:
            try:
                params = {'q': term, 's': term}
                resp = requests.get(url, params=params, timeout=5)
                
                # Look for IS XXXX pattern
                matches = re.findall(r'IS\s+(\d{1,5}):(\d{4})', resp.text)
                for num, year in matches:
                    standards_found.append(f"IS {num}:{year}")
                
            except:
                continue
            
            time.sleep(0.5)  # Be nice to server
        
        return list(set(standards_found))
    
    except Exception as e:
        log.error(f"BIS portal scrape error: {e}")
        return []

def scrape_government_portals():
    """Scrape GeM and NPROCURE for referenced standards."""
    try:
        log.info("Scraping government procurement portals...")
        
        standards_found = []
        
        # GeM search
        try:
            url = "https://gem.gov.in/search"
            categories = ["cement", "steel", "water", "construction"]
            
            for cat in categories:
                try:
                    resp = requests.get(url, params={'q': cat}, timeout=5)
                    matches = re.findall(r'IS\s+(\d{1,5}):(\d{4})', resp.text)
                    for num, year in matches:
                        standards_found.append(f"IS {num}:{year}")
                except:
                    pass
                time.sleep(0.3)
        
        except:
            pass
        
        return list(set(standards_found))
    
    except Exception as e:
        log.error(f"Government portal scrape error: {e}")
        return []

def main():
    print("="*80)
    print("AGGRESSIVE BIS STANDARDS SCRAPER")
    print("="*80)
    print()
    
    all_standards = {}
    
    # Phase 1: Scrape critical standards from archive.org
    print("PHASE 1: Archive.org Scraping")
    print(f"Searching for {len(CRITICAL_STANDARDS)} critical standards...")
    print()
    
    found_count = 0
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(search_archive_org, desig): (desig, desc)
            for desig, desc in CRITICAL_STANDARDS.items()
        }
        
        for i, future in enumerate(as_completed(futures), 1):
            desig, desc = futures[future]
            try:
                result = future.result()
                if result:
                    identifier = result.get('identifier')
                    download_url = download_from_archive(identifier)
                    
                    if download_url:
                        text = extract_text_from_url(download_url)
                        all_standards[desig] = {
                            'title': desc,
                            'identifier': identifier,
                            'source': 'archive.org',
                            'text_preview': text[:500] if text else 'N/A',
                            'download_url': download_url
                        }
                        print(f"✓ [{i:2d}] {desig:20s} FOUND - {identifier[:40]}")
                        found_count += 1
                    else:
                        print(f"⚠ [{i:2d}] {desig:20s} Found but no download available")
                else:
                    print(f"✗ [{i:2d}] {desig:20s} NOT FOUND")
            except Exception as e:
                print(f"✗ [{i:2d}] {desig:20s} ERROR: {str(e)[:40]}")
            
            time.sleep(0.2)
    
    print()
    print(f"Archive.org Results: {found_count}/{len(CRITICAL_STANDARDS)} found")
    print()
    
    # Phase 2: Scrape BIS portal
    print("PHASE 2: BIS Portal Scraping")
    bis_standards = scrape_bis_portal()
    print(f"Found {len(bis_standards)} additional standards from BIS portal")
    print()
    
    for std in bis_standards[:10]:  # Show first 10
        if std not in all_standards:
            all_standards[std] = {
                'title': 'TBD',
                'source': 'bis.gov.in',
                'text_preview': 'N/A'
            }
    
    # Phase 3: Scrape government portals
    print("PHASE 3: Government Procurement Portal Scraping")
    gem_standards = scrape_government_portals()
    print(f"Found {len(gem_standards)} standards from procurement portals")
    print()
    
    for std in gem_standards[:10]:  # Show first 10
        if std not in all_standards:
            all_standards[std] = {
                'title': 'TBD (from procurement)',
                'source': 'gem.gov.in',
                'text_preview': 'N/A'
            }
    
    # Phase 4: Save results
    print("PHASE 4: Saving Results")
    print()
    
    # Save to JSON
    output_file = 'scraped_standards_direct.json'
    with open(output_file, 'w') as f:
        json.dump(all_standards, f, indent=2)
    
    print(f"✓ Saved {len(all_standards)} standards to {output_file}")
    
    # Save to JSONL for bis_data integration
    bis_data_dir = Path('bis_scraper/bis_data/rag')
    bis_data_dir.mkdir(parents=True, exist_ok=True)
    
    jsonl_file = bis_data_dir / 'search_corpus_scraped.jsonl'
    with open(jsonl_file, 'w') as f:
        for desig, data in all_standards.items():
            entry = {
                'designation': desig,
                'title': data.get('title', ''),
                'summary': data.get('text_preview', '')[:200],
                'source': data.get('source', 'web'),
                'is_current': True
            }
            f.write(json.dumps(entry) + '\n')
    
    print(f"✓ Saved to bis_data/rag/search_corpus_scraped.jsonl")
    
    # Summary
    print()
    print("="*80)
    print("SCRAPING COMPLETE")
    print("="*80)
    print(f"Total standards found: {len(all_standards)}")
    print(f"Archive.org: {found_count}/{len(CRITICAL_STANDARDS)}")
    print(f"BIS Portal: +{len(bis_standards)}")
    print(f"Gov Portals: +{len(gem_standards)}")
    print()
    print("Next steps:")
    print("1. Review scraped_standards_direct.json")
    print("2. Integrate into bis_data/")
    print("3. Re-index corpus")
    print("4. Re-run golden set evaluation")
    print()
    print("Files created:")
    print(f"  - {output_file}")
    print(f"  - bis_scraper/bis_data/rag/search_corpus_scraped.jsonl")

if __name__ == '__main__':
    main()
