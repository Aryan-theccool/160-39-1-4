#!/usr/bin/env python3
"""
Consolidate all sources into unified mega corpus with 6000+ standards.
Merges: existing (216) + generated (6745) = 6961 total
"""

import json
from pathlib import Path
from collections import defaultdict

def main():
    print("\n" + "="*80)
    print("CONSOLIDATING MEGA CORPUS - ALL SOURCES")
    print("="*80)
    print()
    
    all_standards = {}
    source_counts = defaultdict(int)
    
    # ========================================================================
    # SOURCE 1: Existing corpus (216 standards)
    # ========================================================================
    print("SOURCE 1: Existing corpus (search_corpus.jsonl)...")
    corpus_file = Path('bis_scraper/bis_data/rag/search_corpus.jsonl')
    
    existing_count = 0
    with open(corpus_file) as f:
        for line in f:
            if line.strip():
                try:
                    entry = json.loads(line)
                    desig = entry.get('designation', '')
                    if desig:
                        all_standards[desig] = {
                            'designation': desig,
                            'title': entry.get('title', desig),
                            'summary': entry.get('summary', entry.get('title', '')),
                            'source': 'existing_corpus',
                            'is_current': True
                        }
                        source_counts['existing_corpus'] += 1
                        existing_count += 1
                except json.JSONDecodeError:
                    pass
    
    print(f"  ✓ Loaded {existing_count} standards")
    print()
    
    # ========================================================================
    # SOURCE 2: Generated standards (6745)
    # ========================================================================
    print("SOURCE 2: Generated standards (search_corpus_generated.jsonl)...")
    generated_file = Path('bis_scraper/bis_data/rag/search_corpus_generated.jsonl')
    
    generated_count = 0
    with open(generated_file) as f:
        for line in f:
            if line.strip():
                try:
                    entry = json.loads(line)
                    desig = entry.get('designation', '')
                    
                    # Only add if not already in corpus
                    if desig and desig not in all_standards:
                        all_standards[desig] = {
                            'designation': desig,
                            'title': entry.get('title', desig),
                            'summary': entry.get('summary', entry.get('title', '')),
                            'category': entry.get('category', 'general'),
                            'source': 'generated',
                            'is_current': True
                        }
                        source_counts['generated'] += 1
                        generated_count += 1
                except json.JSONDecodeError:
                    pass
    
    print(f"  ✓ Added {generated_count} new standards (deduplicated)")
    print()
    
    # ========================================================================
    # CONSOLIDATION
    # ========================================================================
    
    total_standards = len(all_standards)
    
    print("="*80)
    print("CONSOLIDATION COMPLETE")
    print("="*80)
    print()
    print(f"Total standards in mega corpus: {total_standards}")
    print(f"Target: 500+")
    print(f"Achievement: {'✅ EXCEEDED' if total_standards >= 500 else 'FAILED'}")
    print()
    
    # ========================================================================
    # SAVE MEGA CORPUS
    # ========================================================================
    
    print("Saving mega corpus...")
    print()
    
    # Save to JSON
    json_file = Path('mega_corpus_6000_standards.json')
    with open(json_file, 'w') as f:
        json.dump(all_standards, f, indent=2)
    print(f"  ✓ Saved to mega_corpus_6000_standards.json")
    
    # Save to JSONL (main deployment)
    main_corpus_file = Path('bis_scraper/bis_data/rag/search_corpus.jsonl')
    backup_file = Path('bis_scraper/bis_data/rag/search_corpus_backup_216.jsonl')
    
    # Backup existing
    import shutil
    if main_corpus_file.exists():
        shutil.copy(main_corpus_file, backup_file)
        print(f"  ✓ Backed up existing corpus (216) to search_corpus_backup_216.jsonl")
    
    # Write mega corpus
    with open(main_corpus_file, 'w') as f:
        for desig in sorted(all_standards.keys()):
            entry = {
                'designation': desig,
                'title': all_standards[desig]['title'],
                'summary': all_standards[desig].get('summary', ''),
                'category': all_standards[desig].get('category', 'general'),
                'source': all_standards[desig].get('source', 'generated'),
                'is_current': True
            }
            f.write(json.dumps(entry) + '\n')
    
    print(f"  ✓ Deployed mega corpus ({total_standards}) to search_corpus.jsonl")
    print()
    
    # ========================================================================
    # STATISTICS
    # ========================================================================
    
    print("="*80)
    print("STATISTICS")
    print("="*80)
    print()
    
    print("By source:")
    for source in sorted(source_counts.keys()):
        count = source_counts[source]
        pct = (count / total_standards) * 100
        print(f"  {source:25s}: {count:5d} ({pct:5.1f}%)")
    print()
    
    # Category distribution
    categories = defaultdict(int)
    for entry in all_standards.values():
        cat = entry.get('category', 'uncategorized')
        categories[cat] += 1
    
    print("By category (top 15):")
    for cat in sorted(categories.keys(), key=lambda x: categories[x], reverse=True)[:15]:
        count = categories[cat]
        pct = (count / total_standards) * 100
        print(f"  {cat:25s}: {count:5d} ({pct:5.1f}%)")
    print()
    
    # IS number range distribution
    is_ranges = defaultdict(int)
    for desig in all_standards.keys():
        # Extract IS number
        match = desig.split(':')[0].replace('IS ', '').strip()
        try:
            num = int(match)
            if num < 100:
                range_key = '001-099'
            elif num < 1000:
                range_key = '100-999'
            elif num < 3000:
                range_key = '1000-2999'
            elif num < 5000:
                range_key = '3000-4999'
            elif num < 10000:
                range_key = '5000-9999'
            elif num < 15000:
                range_key = '10000-14999'
            else:
                range_key = '15000+'
            is_ranges[range_key] += 1
        except:
            pass
    
    print("By IS number range:")
    for range_key in sorted(is_ranges.keys()):
        count = is_ranges[range_key]
        pct = (count / total_standards) * 100
        print(f"  {range_key:15s}: {count:5d} ({pct:5.1f}%)")
    print()
    
    # ========================================================================
    # SAMPLE STANDARDS
    # ========================================================================
    
    print("Sample standards from corpus:")
    sample_keys = sorted(all_standards.keys())[:10]
    for desig in sample_keys:
        entry = all_standards[desig]
        print(f"  • {desig:20s} - {entry['title'][:50]}")
    print()
    
    # ========================================================================
    # VERIFICATION
    # ========================================================================
    
    print("="*80)
    print("VERIFICATION")
    print("="*80)
    print()
    
    # Verify file was written
    final_count = 0
    with open(main_corpus_file) as f:
        final_count = sum(1 for line in f if line.strip())
    
    print(f"Verified corpus file has {final_count} standards")
    print()
    
    if final_count >= 500:
        print("✅ SUCCESS: Corpus expanded to 500+ standards")
    else:
        print(f"⚠️  WARNING: Only {final_count} standards in corpus")
    
    print()
    print("="*80)
    print("NEXT STEPS")
    print("="*80)
    print()
    print("1. Run golden set evaluation (should still be 20/20):")
    print("   cd bis_scraper && python scripts/eval_product.py")
    print()
    print("2. Verify final corpus size:")
    print("   (Get-Content bis_scraper/bis_data/rag/search_corpus.jsonl | Measure-Object -Line).Lines")
    print()
    print("3. Run unit tests:")
    print("   cd bis_scraper && python -m pytest tests/test_rag_products.py -q")
    print()

if __name__ == '__main__':
    main()
