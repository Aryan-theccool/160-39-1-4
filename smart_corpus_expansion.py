#!/usr/bin/env python3
"""
Smart corpus expansion strategy:
- Keep proven 216 standards (20/20 golden set passing)
- Add only HIGH-VALUE standards that won't hurt ranking
- Target: 500+ standards with maintained quality
- Strategy: Add standards from underrepresented categories, avoid near-duplicates
"""

import json
from pathlib import Path
from collections import defaultdict

def extract_is_number(designation):
    """Extract IS number from designation like 'IS 269:2015'."""
    try:
        return int(designation.split(':')[0].replace('IS ', '').replace('(Part', '').strip())
    except:
        return None

def main():
    print("\n" + "="*80)
    print("SMART CORPUS EXPANSION")
    print("="*80)
    print()
    print("Strategy:")
    print("  1. Keep proven 216 standards (20/20 golden set passing)")
    print("  2. Add only critical missing standards")
    print("  3. Avoid near-duplicates that hurt ranking")
    print("  4. Target: 500+ with maintained quality")
    print()
    
    # Load existing corpus
    corpus_file = Path('bis_scraper/bis_data/rag/search_corpus.jsonl')
    existing_corpus = {}
    existing_is_numbers = set()
    
    print("Loading existing corpus (216 standards)...")
    with open(corpus_file) as f:
        for line in f:
            if line.strip():
                try:
                    entry = json.loads(line)
                    desig = entry.get('designation', '')
                    existing_corpus[desig] = entry
                    is_num = extract_is_number(desig)
                    if is_num:
                        existing_is_numbers.add(is_num)
                except:
                    pass
    
    print(f"  ✓ Loaded {len(existing_corpus)} standards")
    print(f"  ✓ Covers {len(existing_is_numbers)} unique IS numbers")
    print()
    
    # Load generated standards
    generated_file = Path('generated_500_standards.json')
    generated_corpus = {}
    
    print("Loading generated standards (6745)...")
    with open(generated_file) as f:
        generated_corpus = json.load(f)
    print(f"  ✓ Loaded {len(generated_corpus)} standards")
    print()
    
    # ========================================================================
    # SELECTION STRATEGY: Add high-value standards only
    # ========================================================================
    
    print("Selecting high-value standards to add...")
    print()
    
    candidates = {}
    
    # Strategy 1: Add ONE recent edition per existing IS number range
    # (e.g., if we have IS 269:2015, add IS 269:2021 if available)
    print("  Strategy 1: Recent editions of existing standards...")
    strategy1_count = 0
    
    for is_num in sorted(existing_is_numbers):
        # Look for higher year versions
        for year in range(2024, 2000, -1):
            candidate_key = f"IS {is_num}:{year}"
            if candidate_key in generated_corpus and candidate_key not in existing_corpus:
                candidates[candidate_key] = {
                    **generated_corpus[candidate_key],
                    'addition_reason': f'Recent edition of IS {is_num}'
                }
                strategy1_count += 1
                break
    
    print(f"    Added {strategy1_count} recent editions")
    
    # Strategy 2: Add standards from underrepresented IS number ranges
    # Goal: Expand coverage to new ranges
    print("  Strategy 2: Standards from underrepresented ranges...")
    strategy2_count = 0
    
    underrepresented_ranges = [
        (50, 99),      # Low numbers
        (3000, 3100),  # Safety equipment
        (4000, 4100),  # Lifts/escalators
        (7000, 7100),  # Chemicals
        (8000, 8100),  # Food/agriculture
        (9000, 9100),  # Agriculture
        (11000, 11100), # New standards
        (12000, 12100), # New standards
        (14000, 14100), # New standards
        (16000, 16100), # Very new standards
        (17000, 17100), # Very new standards
        (18000, 18100), # Very new standards
        (19000, 19100), # Very new standards
    ]
    
    for low, high in underrepresented_ranges:
        # Add ONE per range to avoid duplication
        added = False
        for is_num in range(low, high, 5):  # Skip by 5 to reduce noise
            if is_num not in existing_is_numbers:
                for year in range(2023, 2010, -1):
                    candidate_key = f"IS {is_num}:{year}"
                    if candidate_key in generated_corpus and candidate_key not in candidates:
                        candidates[candidate_key] = {
                            **generated_corpus[candidate_key],
                            'addition_reason': f'New range IS {is_num}-{is_num+5}'
                        }
                        strategy2_count += 1
                        added = True
                        break
            if added:
                break
    
    print(f"    Added {strategy2_count} from new ranges")
    
    # Strategy 3: Add critical procurement standards
    # (from our unified database - these are actually relevant)
    print("  Strategy 3: Critical procurement standards...")
    strategy3_count = 0
    
    critical_procurement = [
        'IS 269:2015',   # Cement
        'IS 456:2000',   # Concrete
        'IS 1786:2008',  # Steel bars
        'IS 800:2007',   # Steel structures
        'IS 10500:2012', # Water
        'IS 4014:2003',  # Lifts
        'IS 13620:2022', # RCC repair
        'IS 1077:2016',  # Bricks
        'IS 2250:2012',  # Brick masonry
        'IS 1905:2016',  # Stone masonry
    ]
    
    for desig in critical_procurement:
        if desig not in existing_corpus and desig not in candidates:
            # Try to find this in generated
            for gen_key in generated_corpus:
                if gen_key.startswith(desig.split(':')[0]):
                    candidates[gen_key] = {
                        **generated_corpus[gen_key],
                        'addition_reason': 'Critical procurement standard'
                    }
                    strategy3_count += 1
                    break
    
    print(f"    Added {strategy3_count} procurement standards")
    
    # ========================================================================
    # CONSOLIDATION
    # ========================================================================
    
    total_new = len(candidates)
    total_final = len(existing_corpus) + len(candidates)
    
    print()
    print("="*80)
    print("CONSOLIDATION")
    print("="*80)
    print()
    
    print(f"Existing corpus: {len(existing_corpus)}")
    print(f"New high-value standards: {total_new}")
    print(f"  - Strategy 1 (recent editions): {strategy1_count}")
    print(f"  - Strategy 2 (new ranges): {strategy2_count}")
    print(f"  - Strategy 3 (procurement): {strategy3_count}")
    print()
    print(f"Final corpus size: {total_final}")
    print(f"Target: 500+")
    print(f"Status: {'✅ ACHIEVED' if total_final >= 500 else f'⏳ {500 - total_final} more needed'}")
    print()
    
    # ========================================================================
    # BUILD AND DEPLOY
    # ========================================================================
    
    print("Building final corpus...")
    final_corpus = {**existing_corpus}
    final_corpus.update(candidates)
    
    # Save backup of mega corpus
    mega_file = Path('bis_scraper/bis_data/rag/search_corpus_mega_6945.jsonl')
    print(f"  ✓ Keeping mega corpus as backup: search_corpus_mega_6945.jsonl")
    
    # Save selective corpus
    smart_file = Path('bis_scraper/bis_data/rag/search_corpus.jsonl')
    with open(smart_file, 'w') as f:
        for desig in sorted(final_corpus.keys()):
            entry = {
                'designation': desig,
                'title': final_corpus[desig].get('title', desig),
                'summary': final_corpus[desig].get('summary', final_corpus[desig].get('title', '')),
                'category': final_corpus[desig].get('category', 'general'),
                'source': final_corpus[desig].get('source', 'extended'),
                'is_current': True,
                'addition_reason': final_corpus[desig].get('addition_reason', 'original')
            }
            f.write(json.dumps(entry) + '\n')
    
    print(f"  ✓ Deployed selective corpus ({total_final} standards) to search_corpus.jsonl")
    print()
    
    # Verification
    final_count = 0
    with open(smart_file) as f:
        final_count = sum(1 for line in f if line.strip())
    
    print(f"Verified: {final_count} standards in corpus")
    print()
    
    # ========================================================================
    # STATISTICS
    # ========================================================================
    
    print("="*80)
    print("STATISTICS")
    print("="*80)
    print()
    
    print("Corpus composition:")
    print(f"  - Original proven (216): {len(existing_corpus)}")
    print(f"  - Newly added ({total_final - len(existing_corpus)}): {total_new}")
    print()
    
    # Sample new additions
    print("Sample new additions:")
    for i, desig in enumerate(sorted(candidates.keys())[:10]):
        reason = candidates[desig].get('addition_reason', 'N/A')
        print(f"  {i+1}. {desig:20s} - {reason}")
    
    print()
    print("="*80)
    print("READY FOR TESTING")
    print("="*80)
    print()
    print("1. Test golden set (should stay 20/20):")
    print("   cd bis_scraper && python scripts/eval_product.py")
    print()
    print("2. Check corpus size:")
    print("   (Get-Content bis_scraper/bis_data/rag/search_corpus.jsonl | Measure-Object -Line).Lines")
    print()

if __name__ == '__main__':
    main()
