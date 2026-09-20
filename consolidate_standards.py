#!/usr/bin/env python3
"""
Consolidate standards from multiple sources into unified database.
Sources:
1. Archive.org scan results
2. GeM procurement extraction
3. Existing bis_data corpus
"""

import json
import os
from pathlib import Path
from collections import defaultdict

def load_json(filepath):
    """Safely load JSON file."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"  ! Could not load {filepath}: {e}")
        return []

def consolidate():
    print("="*80)
    print("CONSOLIDATING STANDARDS FROM ALL SOURCES")
    print("="*80)
    print()
    
    # Load source 1: Procurement context
    print("[1/3] Loading procurement standards...")
    procurement_stds = load_json('standards_from_procurement.json')
    print(f"  ✓ Loaded {len(procurement_stds)} procurement standards")
    
    # Load source 2: Archive.org results (if available)
    print("[2/3] Loading archive.org results...")
    archive_stds = load_json('archive_scan_results.json')
    print(f"  ✓ Loaded {len(archive_stds)} archive.org identifiers")
    
    # Load source 3: Existing corpus
    print("[3/3] Loading existing bis_data corpus...")
    existing_path = Path('bis_scraper/bis_data')
    existing_stds = []
    if existing_path.exists():
        for json_file in existing_path.glob('*.json'):
            if json_file.name != 'product_aliases.json':
                try:
                    with open(json_file, 'r') as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            existing_stds.extend(data)
                except:
                    pass
    print(f"  ✓ Loaded {len(existing_stds)} existing standards")
    
    # Create unified database
    unified_db = {}
    
    # Add procurement standards (primary)
    print()
    print("Building unified database...")
    for std in procurement_stds:
        designation = std.get('designation', '').strip()
        if designation:
            if designation not in unified_db:
                unified_db[designation] = {
                    'designation': designation,
                    'title': std.get('title', ''),
                    'category': std.get('category', 'uncategorized'),
                    'sources': [],
                    'metadata': {}
                }
            unified_db[designation]['sources'].append('procurement')
            unified_db[designation]['metadata']['procurement_frequency'] = std.get('procurement_frequency', 0)
    
    # Add from existing corpus (avoid duplicates)
    for std in existing_stds:
        # Extract designation from JSON (format may vary)
        if isinstance(std, dict):
            designation = std.get('designation', '')
        else:
            designation = str(std)
        
        if designation and designation not in unified_db:
            unified_db[designation] = {
                'designation': designation,
                'title': std.get('title', '') if isinstance(std, dict) else '',
                'category': 'testing_equipment',  # existing corpus is mostly this
                'sources': [],
                'metadata': {}
            }
        if designation:
            unified_db[designation]['sources'].append('existing_corpus')
    
    # Sort by designation
    sorted_db = dict(sorted(unified_db.items()))
    
    print(f"  ✓ Total unified standards: {len(sorted_db)}")
    
    # Statistics
    print()
    print("STATISTICS:")
    print(f"  Total standards: {len(sorted_db)}")
    
    categories = defaultdict(int)
    for std in sorted_db.values():
        categories[std['category']] += 1
    
    print(f"  Categories: {len(categories)}")
    for cat in sorted(categories.keys()):
        print(f"    - {cat}: {categories[cat]} standards")
    
    source_counts = defaultdict(int)
    for std in sorted_db.values():
        for source in std['sources']:
            source_counts[source] += 1
    
    print(f"  Source breakdown:")
    for source in sorted(source_counts.keys()):
        print(f"    - {source}: {source_counts[source]} standards")
    
    # Save unified database
    output_file = 'unified_standards_database.json'
    with open(output_file, 'w') as f:
        json.dump(sorted_db, f, indent=2)
    
    print()
    print(f"✓ Saved unified database to {output_file}")
    print(f"  Size: {len(json.dumps(sorted_db))} bytes")
    
    # Generate summary CSV for easy viewing
    print()
    print("Generating CSV summary...")
    csv_file = 'unified_standards_summary.csv'
    with open(csv_file, 'w', encoding='utf-8') as f:
        f.write('Designation,Title,Category,Sources,Procurement Frequency\n')
        for designation, std in sorted_db.items():
            title = std.get('title', '').replace(',', ';')[:100]
            category = std.get('category', '')
            sources = '|'.join(std.get('sources', []))
            freq = std.get('metadata', {}).get('procurement_frequency', '')
            f.write(f'"{designation}","{title}","{category}","{sources}","{freq}"\n')
    
    print(f"✓ Saved CSV summary to {csv_file}")
    
    # Show sample
    print()
    print("SAMPLE (first 10 standards):")
    for i, (desig, std) in enumerate(sorted_db.items()):
        if i >= 10:
            break
        print(f"  {desig:20s} | {std['title'][:50]:50s} | {std['category']}")
    
    print()
    print("="*80)
    print("CONSOLIDATION COMPLETE")
    print("="*80)
    print()
    print("NEXT STEPS:")
    print("  1. ✓ Archive.org scan (Task #1)")
    print("  2. [ ] Send BIS ministry email (Task #2)")
    print("  3. ✓ Extract procurement standards (Task #3)")
    print("  4. [ ] Parse PDF content (Task #4)")
    print("  5. ✓ Consolidate database (Task #5)")
    print("  6. [ ] Reindex bis_data/ (Task #6)")
    print("  7. [ ] Evaluate on golden set (Task #7)")
    print()
    print("BIS Response Expected: 3-7 days")
    print("Keep this unified database updated as new sources come in.")

if __name__ == '__main__':
    consolidate()
