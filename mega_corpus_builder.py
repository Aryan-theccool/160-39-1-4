#!/usr/bin/env python3
"""
Build mega corpus from all data sources:
- Existing search_corpus.jsonl (202 standards)
- Unified standards database (15 standards)
- Procurement standards (15 standards)
- Archive.org data (from archive_scan_results.json)
"""

import json
from pathlib import Path
from collections import defaultdict

def main():
    print("="*80)
    print("MEGA CORPUS BUILDER - COMPREHENSIVE DATA AGGREGATION")
    print("="*80)
    print()
    
    all_standards = {}  # designation -> entry
    sources_count = defaultdict(int)
    
    # ===== SOURCE 1: Existing corpus =====
    print("SOURCE 1: Reading existing search_corpus.jsonl...")
    corpus_file = Path('bis_scraper/bis_data/rag/search_corpus.jsonl')
    existing_count = 0
    
    with open(corpus_file) as f:
        for line in f:
            if line.strip():
                try:
                    entry = json.loads(line)
                    desig = entry.get('designation', '')
                    if desig:
                        all_standards[desig] = entry
                        sources_count['existing_corpus'] += 1
                        existing_count += 1
                except json.JSONDecodeError:
                    continue
    
    print(f"  ✓ Loaded {existing_count} standards from existing corpus")
    print()
    
    # ===== SOURCE 2: Unified database =====
    print("SOURCE 2: Reading unified_standards_database.json...")
    unified_file = Path('unified_standards_database.json')
    unified_count = 0
    
    if unified_file.exists():
        with open(unified_file) as f:
            unified = json.load(f)
            for desig, data in unified.items():
                if desig not in all_standards:
                    entry = {
                        'designation': desig,
                        'title': data.get('title', ''),
                        'summary': data.get('title', ''),
                        'source': 'unified_database',
                        'is_current': True,
                        'procurement_frequency': data.get('metadata', {}).get('procurement_frequency', 0)
                    }
                    all_standards[desig] = entry
                    sources_count['unified_database'] += 1
                    unified_count += 1
    
    print(f"  ✓ Added {unified_count} new standards from unified database")
    print()
    
    # ===== SOURCE 3: Procurement standards =====
    print("SOURCE 3: Reading standards_from_procurement.json...")
    procurement_file = Path('standards_from_procurement.json')
    procurement_count = 0
    
    if procurement_file.exists():
        with open(procurement_file) as f:
            procurement = json.load(f)
            for data in procurement:
                desig = data.get('designation', '')
                if desig and desig not in all_standards:
                    entry = {
                        'designation': desig,
                        'title': data.get('title', ''),
                        'summary': data.get('context', data.get('title', '')),
                        'category': data.get('category', 'procurement'),
                        'source': 'procurement',
                        'is_current': True,
                        'procurement_frequency': data.get('procurement_frequency', 0)
                    }
                    all_standards[desig] = entry
                    sources_count['procurement'] += 1
                    procurement_count += 1
    
    print(f"  ✓ Added {procurement_count} new standards from procurement sources")
    print()
    
    # ===== SOURCE 4: Archive.org scan results =====
    print("SOURCE 4: Reading archive_scan_results.json...")
    archive_file = Path('archive_scan_results.json')
    archive_count = 0
    
    if archive_file.exists():
        with open(archive_file) as f:
            archive_results = json.load(f)
            # Handle both list and dict formats
            items = archive_results.items() if isinstance(archive_results, dict) else archive_results
            
            for item in items:
                if isinstance(archive_results, dict):
                    desig, data = item
                else:
                    data = item
                    desig = data.get('designation', '')
                
                if desig and desig not in all_standards:
                    entry = {
                        'designation': desig,
                        'title': data.get('desc', data.get('title', desig)),
                        'summary': data.get('desc', 'Archive.org document'),
                        'source': 'archive.org',
                        'is_current': True,
                        'archive_identifier': data.get('identifier', '')
                    }
                    all_standards[desig] = entry
                    sources_count['archive'] += 1
                    archive_count += 1
    
    print(f"  ✓ Added {archive_count} standards from archive.org")
    print()
    
    # ===== SAVE MEGA CORPUS =====
    print("="*80)
    print("BUILDING MEGA CORPUS")
    print("="*80)
    print()
    
    mega_corpus_file = Path('bis_scraper/bis_data/rag/search_corpus_mega.jsonl')
    
    with open(mega_corpus_file, 'w') as f:
        for desig in sorted(all_standards.keys()):
            entry = all_standards[desig]
            f.write(json.dumps(entry) + '\n')
    
    print(f"✓ Saved mega corpus to search_corpus_mega.jsonl")
    print()
    
    # ===== STATISTICS =====
    print("="*80)
    print("STATISTICS")
    print("="*80)
    print()
    print(f"Total unique standards: {len(all_standards)}")
    print()
    print("By source:")
    for source in sorted(sources_count.keys()):
        count = sources_count[source]
        pct = (count / len(all_standards)) * 100
        print(f"  {source:25s}: {count:3d} ({pct:5.1f}%)")
    print()
    
    # Categories distribution
    categories = defaultdict(int)
    for entry in all_standards.values():
        cat = entry.get('category', 'uncategorized')
        categories[cat] += 1
    
    print("By category:")
    for cat in sorted(categories.keys()):
        count = categories[cat]
        pct = (count / len(all_standards)) * 100
        print(f"  {cat:25s}: {count:3d} ({pct:5.1f}%)")
    print()
    
    # ===== SWAP & BACKUP =====
    print("="*80)
    print("DEPLOYMENT")
    print("="*80)
    print()
    
    # Backup current corpus
    backup_file = Path('bis_scraper/bis_data/rag/search_corpus_backup.jsonl')
    if corpus_file.exists():
        import shutil
        shutil.copy(corpus_file, backup_file)
        print(f"✓ Backed up existing corpus to search_corpus_backup.jsonl")
    
    # Replace with mega corpus
    import shutil
    shutil.copy(mega_corpus_file, corpus_file)
    print(f"✓ Deployed mega corpus as search_corpus.jsonl")
    print()
    
    # ===== VERIFICATION =====
    final_count = 0
    with open(corpus_file) as f:
        final_count = sum(1 for line in f if line.strip())
    
    print("="*80)
    print("MEGA CORPUS READY")
    print("="*80)
    print(f"Final corpus size: {final_count} standards")
    print()
    print("Next steps:")
    print("1. Run golden set evaluation:")
    print("   cd bis_scraper && python scripts/eval_product.py")
    print()
    print("2. Run unit tests:")
    print("   cd bis_scraper && python -m pytest tests/test_rag_products.py -v")
    print()
    print("3. Test API:")
    print("   cd bis_scraper && python -m pytest tests/test_api_product.py -v")

if __name__ == '__main__':
    main()
