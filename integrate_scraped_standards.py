#!/usr/bin/env python3
"""
Integrate unified standards database into bis_data search corpus
"""

import json
from pathlib import Path

def main():
    print("="*80)
    print("INTEGRATING UNIFIED STANDARDS DATABASE INTO CORPUS")
    print("="*80)
    print()
    
    # Read unified database
    unified_file = Path('unified_standards_database.json')
    with open(unified_file) as f:
        unified = json.load(f)
    
    print(f"Loaded {len(unified)} standards from unified_standards_database.json")
    print()
    
    # Read current corpus
    corpus_file = Path('bis_scraper/bis_data/rag/search_corpus.jsonl')
    existing_designations = set()
    
    with open(corpus_file) as f:
        for line in f:
            if line.strip():
                entry = json.loads(line)
                existing_designations.add(entry.get('designation', ''))
    
    print(f"Current corpus has {len(existing_designations)} standards")
    print()
    
    # Prepare new entries to add
    new_entries = []
    skipped = 0
    
    for designation, data in unified.items():
        if designation not in existing_designations:
            entry = {
                'designation': designation,
                'title': data.get('title', ''),
                'summary': data.get('title', ''),
                'category': data.get('category', 'general'),
                'source': 'unified_database',
                'is_current': True,
                'procurement_frequency': data.get('metadata', {}).get('procurement_frequency', 0)
            }
            new_entries.append(entry)
        else:
            skipped += 1
    
    print(f"New standards to add: {len(new_entries)}")
    print(f"Skipped (already in corpus): {skipped}")
    print()
    
    # Append to corpus
    if new_entries:
        with open(corpus_file, 'a') as f:
            for entry in new_entries:
                f.write(json.dumps(entry) + '\n')
        
        print(f"✓ Appended {len(new_entries)} new standards to search_corpus.jsonl")
    else:
        print("No new standards to add")
    
    # Verify
    total_count = 0
    with open(corpus_file) as f:
        total_count = sum(1 for line in f if line.strip())
    
    print()
    print("="*80)
    print("INTEGRATION COMPLETE")
    print("="*80)
    print(f"Total standards in corpus: {total_count}")
    print()
    print("Next: Run golden set evaluation")
    print("  cd bis_scraper")
    print("  python scripts/eval_product.py")

if __name__ == '__main__':
    main()
