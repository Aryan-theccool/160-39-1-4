#!/usr/bin/env python3
"""Scan Archive.org for missing BIS standards."""

import requests
import json
import time
from datetime import datetime

# Top 30 critical standards we're missing
missing_standards = [
    ('IS 8112:2013', 'OPC 43 grade cement'),
    ('IS 269:2015', 'Ordinary portland cement'),
    ('IS 456:2000', 'Code of practice for concrete'),
    ('IS 1786:2008', 'Steel reinforcement bars'),
    ('IS 10500:2012', 'Drinking water'),
    ('IS 3025:2023', 'Methods of test for water'),
    ('IS 2751:2007', 'Structural steel'),
    ('IS 1239:2004', 'Mild steel pipes'),
    ('IS 1077:2016', 'Common burnt clay bricks'),
    ('IS 2250:2012', 'Code of practice for brick masonry'),
    ('IS 4014:2003', 'Safety code for lifts'),
    ('IS 800:2007', 'Steel structures code'),
    ('IS 13620:2022', 'Concrete repair code'),
    ('IS 455:2015', 'Portland slag cement'),
    ('IS 12269:2013', 'OPC 53 grade cement'),
    ('IS 1161:2014', 'Structural steel tubes'),
    ('IS 226:2012', 'Steel for structural use'),
    ('IS 1905:2016', 'Code of practice for stone masonry'),
    ('IS 2030:2012', 'Water storage tanks'),
    ('IS 1172:2012', 'Stainless steel water tanks'),
]

print('='*80)
print('ARCHIVE.ORG SCAN - CRITICAL BIS STANDARDS')
print('='*80)
print(f'Target: {len(missing_standards)} standards')
print(f'Started: {datetime.now().isoformat()}')
print()

found = []
not_found = []

for i, (designation, description) in enumerate(missing_standards, 1):
    try:
        # Search archive.org
        search_term = designation.replace(':', '_').replace(' ', '+')
        url = f'https://archive.org/advancedsearch.php?q={search_term}&fl=identifier,title&output=json'
        
        response = requests.get(url, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            docs = data.get('response', {}).get('docs', [])
            
            if docs:
                status = '✓ FOUND'
                identifier = docs[0].get('identifier', 'unknown')
                found.append({
                    'designation': designation,
                    'identifier': identifier,
                    'desc': description
                })
            else:
                status = '✗ NOT FOUND'
                not_found.append(designation)
        else:
            status = f'! HTTP {response.status_code}'
            
    except Exception as e:
        status = f'✗ ERROR: {str(e)[:30]}'
    
    print(f'[{i:2d}] {designation:20s} {status:20s} {description}')
    time.sleep(0.5)

print()
print('='*80)
print(f'RESULTS: {len(found)} Found / {len(not_found)} Not Found / {len(missing_standards)} Total')
print('='*80)

if found:
    print('\nFOUND STANDARDS (downloadable from archive.org):')
    for item in found:
        print(f"  {item['designation']:20s} → {item['identifier']}")
        print(f"    Download: https://archive.org/download/{item['identifier']}/")
    
    # Save results
    with open('archive_scan_results.json', 'w') as f:
        json.dump(found, f, indent=2)
    print(f'\n✓ Saved {len(found)} results to archive_scan_results.json')

if not_found:
    print('\nNOT FOUND (will need BIS direct request or GeM scraping):')
    for j, std in enumerate(not_found, 1):
        print(f'  {j}. {std}')

print()
print('NEXT STEPS:')
print('  1. Download PDFs from archive.org links above')
print('  2. Extract text with OCR or pdftotext')
print('  3. Parse metadata and add to bis_data/')
print('  4. Wait for BIS ministry response for remaining standards')
