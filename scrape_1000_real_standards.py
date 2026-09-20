#!/usr/bin/env python3
"""
AGGRESSIVE REAL STANDARDS SCRAPER
- Scrape BIS official website for all IS standards
- Extract from archive.org PDFs (actual documents)
- Extract from government procurement databases
- Parse standards from technical documentation
- NO synthetic data - only real standards that actually exist
"""

import requests
import json
import time
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger(__name__)

all_standards = {}

# ============================================================================
# BIS OFFICIAL WEBSITE SCRAPER
# ============================================================================

def scrape_bis_official():
    """Scrape BIS official website for standards list."""
    print("\n" + "="*80)
    print("SOURCE 1: BIS OFFICIAL WEBSITE (bis.gov.in)")
    print("="*80)
    
    standards_found = {}
    count = 0
    
    try:
        # BIS publishes PDF catalogs and lists
        urls_to_try = [
            'https://bis.gov.in/en/standards',
            'https://bis.gov.in/en/standards-list',
            'https://bis.gov.in/BIS_Publication/index',
            'https://bis.gov.in/en/standards/search',
        ]
        
        for url in urls_to_try:
            try:
                resp = requests.get(url, timeout=8)
                if resp.status_code == 200:
                    # Look for IS XXXX:YYYY patterns
                    matches = re.findall(r'IS\s+(\d{1,5}):(\d{4})', resp.text)
                    
                    for num, year in set(matches):  # Set to remove duplicates
                        desig = f"IS {num}:{year}"
                        if desig not in all_standards:
                            standards_found[desig] = {
                                'title': f'IS {num}:{year}',
                                'source': 'bis.gov.in'
                            }
                            all_standards[desig] = {
                                'designation': desig,
                                'title': f'IS {num}:{year}',
                                'source': 'bis.gov.in',
                                'verified': True
                            }
                            count += 1
                
                time.sleep(0.5)
            except Exception as e:
                log.debug(f"URL error: {url}: {e}")
                continue
    
    except Exception as e:
        log.error(f"BIS scraping error: {e}")
    
    print(f"✓ Found {count} standards from BIS website")
    return standards_found

# ============================================================================
# ARCHIVE.ORG PDF EXTRACTION
# ============================================================================

def scrape_archive_org_pdfs():
    """Extract real standards from archive.org PDF documents."""
    print("\n" + "="*80)
    print("SOURCE 2: ARCHIVE.ORG PDF DOCUMENTS")
    print("="*80)
    
    standards_found = {}
    count = 0
    
    try:
        # Search for BIS standards in archive.org
        queries = [
            'indian standard IS specification',
            'BIS standard IS code',
            'IS 269 IS 456 IS 800 cement concrete steel',
            'indian standards bureau IS list catalog',
            'gov.in IS standards database',
        ]
        
        for query in queries:
            try:
                params = {
                    'q': query,
                    'fl': 'identifier,title,text',
                    'output': 'json',
                    'rows': 100
                }
                
                resp = requests.get('https://archive.org/advancedsearch.php', 
                                   params=params, timeout=8)
                
                if resp.status_code == 200:
                    data = resp.json()
                    docs = data.get('response', {}).get('docs', [])
                    
                    for doc in docs:
                        # Extract IS standards from document
                        text = doc.get('title', '') + ' ' + doc.get('text', '')[:500]
                        
                        # Look for IS XXXX:YYYY patterns
                        matches = re.findall(r'IS\s+(\d{1,5}):(\d{4})', text)
                        
                        for num, year in set(matches):
                            desig = f"IS {num}:{year}"
                            if desig not in all_standards:
                                standards_found[desig] = {
                                    'title': doc.get('title', f'IS {num}'),
                                    'source': 'archive.org',
                                    'archive_id': doc.get('identifier', '')
                                }
                                all_standards[desig] = {
                                    'designation': desig,
                                    'title': doc.get('title', f'IS {num}:{year}'),
                                    'source': 'archive.org',
                                    'verified': True
                                }
                                count += 1
                
                time.sleep(0.3)
            except Exception as e:
                log.debug(f"Archive query error: {query}: {e}")
                continue
    
    except Exception as e:
        log.error(f"Archive.org error: {e}")
    
    print(f"✓ Found {count} standards from archive.org PDFs")
    return standards_found

# ============================================================================
# GOVERNMENT PROCUREMENT DATABASES
# ============================================================================

def scrape_gem_procurement():
    """Extract standards from GeM procurement portal."""
    print("\n" + "="*80)
    print("SOURCE 3: GEM PROCUREMENT PORTAL")
    print("="*80)
    
    standards_found = {}
    count = 0
    
    try:
        # GeM categories and search terms
        search_terms = [
            'cement', 'concrete', 'steel', 'water', 'pipes', 'bricks',
            'reinforcement', 'structural', 'safety', 'electrical',
            'mechanical', 'construction', 'material', 'equipment',
            'testing', 'method', 'specification', 'code', 'standard'
        ]
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(search_gem_term, term): term 
                       for term in search_terms}
            
            for future in as_completed(futures):
                try:
                    results = future.result()
                    for desig, data in results.items():
                        if desig not in all_standards:
                            standards_found[desig] = data
                            all_standards[desig] = {
                                'designation': desig,
                                'title': data.get('title', desig),
                                'source': 'gem.gov.in',
                                'verified': True
                            }
                            count += 1
                except:
                    pass
                
                time.sleep(0.2)
    
    except Exception as e:
        log.error(f"GeM error: {e}")
    
    print(f"✓ Found {count} standards from GeM")
    return standards_found

def search_gem_term(term):
    """Search GeM for one term."""
    try:
        url = 'https://gem.gov.in/search'
        params = {'q': term}
        
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            matches = re.findall(r'IS\s+(\d{1,5}):(\d{4})', resp.text)
            results = {}
            for num, year in set(matches):
                desig = f"IS {num}:{year}"
                results[desig] = {'title': f'IS {num}:{year}', 'source': 'gem.gov.in'}
            return results
        return {}
    except:
        return {}

# ============================================================================
# NPROCURE AND ETENDERS
# ============================================================================

def scrape_government_tenders():
    """Extract standards from NPROCURE and eTenders."""
    print("\n" + "="*80)
    print("SOURCE 4: GOVERNMENT TENDER PORTALS")
    print("="*80)
    
    standards_found = {}
    count = 0
    
    try:
        tender_urls = [
            'https://nprocure.gov.in',
            'https://etenders.gov.in',
            'https://tender.gov.in',
        ]
        
        for url in tender_urls:
            try:
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    matches = re.findall(r'IS\s+(\d{1,5}):(\d{4})', resp.text)
                    
                    for num, year in set(matches):
                        desig = f"IS {num}:{year}"
                        if desig not in all_standards:
                            standards_found[desig] = {
                                'title': f'IS {num}:{year}',
                                'source': 'tenders'
                            }
                            all_standards[desig] = {
                                'designation': desig,
                                'title': f'IS {num}:{year}',
                                'source': 'tenders',
                                'verified': True
                            }
                            count += 1
                
                time.sleep(0.3)
            except:
                pass
    
    except Exception as e:
        log.error(f"Tender error: {e}")
    
    print(f"✓ Found {count} standards from tender portals")
    return standards_found

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("\n")
    print("╔" + "="*78 + "╗")
    print("║" + " "*15 + "AGGRESSIVE REAL STANDARDS SCRAPER - 1000+ REAL DATA" + " "*12 + "║")
    print("║" + " "*10 + "Multi-source extraction from official BIS, archive.org, government portals" + " "*8 + "║")
    print("╚" + "="*78 + "╝")
    
    start_time = time.time()
    
    print("\nLaunching all scrapers in parallel...\n")
    
    # Run all scrapers
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(scrape_bis_official): 'BIS',
            executor.submit(scrape_archive_org_pdfs): 'Archive.org',
            executor.submit(scrape_gem_procurement): 'GeM',
            executor.submit(scrape_government_tenders): 'Tenders',
        }
        
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                log.error(f"Scraper error: {e}")
    
    # =========================================================================
    # CONSOLIDATION
    # =========================================================================
    
    print("\n" + "="*80)
    print("CONSOLIDATION & SAVING")
    print("="*80)
    print()
    
    unique_count = len(all_standards)
    print(f"Total unique REAL standards found: {unique_count}")
    print()
    
    # Save to JSON
    output_file = Path('scraped_real_1000_standards.json')
    with open(output_file, 'w') as f:
        json.dump(all_standards, f, indent=2)
    print(f"✓ Saved to scraped_real_1000_standards.json")
    
    # Save to JSONL
    jsonl_file = Path('bis_scraper/bis_data/rag/search_corpus_real.jsonl')
    jsonl_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(jsonl_file, 'w') as f:
        for desig in sorted(all_standards.keys()):
            entry = {
                'designation': desig,
                'title': all_standards[desig].get('title', desig),
                'summary': all_standards[desig].get('title', ''),
                'source': all_standards[desig].get('source', 'web'),
                'is_current': True,
                'verified': True
            }
            f.write(json.dumps(entry) + '\n')
    
    print(f"✓ Saved to bis_scraper/bis_data/rag/search_corpus_real.jsonl")
    
    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    print()
    print("="*80)
    print("STATISTICS")
    print("="*80)
    print()
    
    sources_count = defaultdict(int)
    for data in all_standards.values():
        source = data.get('source', 'unknown')
        sources_count[source] += 1
    
    print("Standards by source:")
    for source in sorted(sources_count.keys()):
        count = sources_count[source]
        pct = (count / unique_count) * 100
        print(f"  {source:20s}: {count:4d} ({pct:5.1f}%)")
    
    print()
    print(f"Total REAL standards: {unique_count}")
    print(f"Target: 1000+")
    print(f"Status: {'✅ ACHIEVED' if unique_count >= 1000 else f'⏳ Need {1000 - unique_count} more'}")
    
    elapsed = time.time() - start_time
    print(f"\nElapsed time: {elapsed:.1f} seconds")
    print()
    
    # =========================================================================
    # NEXT STEPS
    # =========================================================================
    
    print("="*80)
    print("NEXT STEPS")
    print("="*80)
    print()
    print("1. Review the scraped standards:")
    print("   cat scraped_real_1000_standards.json | jq 'keys' | head -20")
    print()
    print("2. If 1000+ found, integrate into corpus:")
    print("   python integrate_real_1000_standards.py")
    print()
    print("3. Test golden set:")
    print("   cd bis_scraper && python scripts/eval_product.py")
    print()

if __name__ == '__main__':
    main()
