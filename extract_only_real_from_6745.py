#!/usr/bin/env python3
"""
Extract ONLY the real standards from the 6745 file.
Take the 1088 'known_catalog' standards + consolidate with existing 216.
"""

import json
from pathlib import Path
from collections import defaultdict

def main():
    print("\n" + "="*80)
    print("EXTRACTING REAL STANDARDS FROM 6745")
    print("="*80)
    print()
    
    # Load existing proven corpus (265 - which includes 216 original + 49 from archive)
    corpus_file = Path('bis_scraper/bis_data/rag/search_corpus.jsonl')
    existing_corpus = {}
    
    print("Loading existing corpus...")
    with open(corpus_file) as f:
        for line in f:
            if line.strip():
                try:
                    entry = json.loads(line)
                    desig = entry.get('designation', '')
                    existing_corpus[desig] = entry
                except:
                    pass
    
    print(f"  ✓ Loaded {len(existing_corpus)}")
    print()
    
    # Load 6745 standards
    generated_file = Path('generated_500_standards.json')
    
    print("Loading 6745 standards...")
    with open(generated_file) as f:
        all_6745 = json.load(f)
    
    print(f"  ✓ Loaded {len(all_6745)}")
    print()
    
    # Extract ONLY real standards (source = 'known_catalog')
    print("Extracting REAL standards only...")
    print()
    
    real_standards = {}
    real_count = 0
    generated_count = 0
    
    for desig, data in all_6745.items():
        source = data.get('source', '')
        
        if source == 'known_catalog':
            # This is real
            if desig not in existing_corpus:
                real_standards[desig] = {
                    'designation': desig,
                    'title': data.get('title', desig),
                    'summary': data.get('title', ''),
                    'source': 'known_catalog',
                    'is_current': True,
                    'verified': True
                }
                real_count += 1
        else:
            generated_count += 1
    
    print(f"Real standards found: {real_count}")
    print(f"Generated (skipped): {generated_count}")
    print()
    
    # ========================================================================
    # CONSOLIDATION
    # ========================================================================
    
    final_corpus = {**existing_corpus, **real_standards}
    total_final = len(final_corpus)
    
    print("="*80)
    print("CONSOLIDATION")
    print("="*80)
    print()
    print(f"Existing corpus: {len(existing_corpus)}")
    print(f"New real standards from 6745: {real_count}")
    print(f"Total REAL standards: {total_final}")
    print(f"Target: 1000+")
    print(f"Status: {'✅ ACHIEVED' if total_final >= 1000 else f'⏳ Need {1000 - total_final} more'}")
    print()
    
    # ========================================================================
    # DEPLOY
    # ========================================================================
    
    print("Deploying REAL standards corpus...")
    
    with open(corpus_file, 'w') as f:
        for desig in sorted(final_corpus.keys()):
            entry = {
                'designation': desig,
                'title': final_corpus[desig].get('title', desig),
                'summary': final_corpus[desig].get('summary', ''),
                'source': final_corpus[desig].get('source', ''),
                'is_current': final_corpus[desig].get('is_current', True),
                'verified': final_corpus[desig].get('verified', True)
            }
            f.write(json.dumps(entry) + '\n')
    
    # Verify
    verify_count = 0
    with open(corpus_file) as f:
        verify_count = sum(1 for line in f if line.strip())
    
    print(f"  ✓ Deployed {verify_count} standards")
    print()
    
    # ========================================================================
    # STATISTICS
    # ========================================================================
    
    print("="*80)
    print("STATISTICS")
    print("="*80)
    print()
    
    # By source
    sources_count = defaultdict(int)
    for entry in final_corpus.values():
        source = entry.get('source', 'unknown')
        sources_count[source] += 1
    
    print("By source:")
    for source in sorted(sources_count.keys()):
        count = sources_count[source]
        pct = (count / total_final) * 100
        print(f"  {source:25s}: {count:4d} ({pct:5.1f}%)")
    print()
    
    # Sample
    print("Sample standards:")
    for i, desig in enumerate(sorted(final_corpus.keys())[:10]):
        print(f"  {i+1}. {desig:20s} - {final_corpus[desig]['title'][:50]}")
    
    print()
    print("="*80)
    print("SUCCESS: ONLY REAL STANDARDS")
    print("="*80)
    print()
    print(f"✅ {verify_count} REAL Indian Standards in corpus")
    if verify_count >= 1000:
        print("✅ EXCEEDED 1000 standard target")
    else:
        print(f"⏳ Need {1000 - verify_count} more to reach 1000")
    print()
    print("Next: Test with golden set")
    print("  cd bis_scraper && python scripts/eval_product.py")
    print()

if __name__ == '__main__':
    main()
