#!/usr/bin/env python3
"""Evaluate product recommendations against golden set."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bis_rag.data import BisData
from bis_rag.hybrid import HybridSearch
from bis_rag.products import recommend_for_product, load_product_aliases
from bis_rag.compliance import QCODatabase


def main():
    # Load data and search
    data_dir = Path(__file__).parent.parent / "bis_data"
    data = BisData(data_dir)
    search = HybridSearch(data)
    aliases = load_product_aliases(data_dir)
    qco_db = QCODatabase(data)
    
    # Load golden set
    cases_path = Path(__file__).parent.parent / "eval" / "product_cases.jsonl"
    
    with open(cases_path) as f:
        cases = [json.loads(line) for line in f]
    
    print(f"\n{'='*80}")
    print(f"PRODUCT RECOMMENDATION EVALUATION")
    print(f"{'='*80}\n")
    print(f"Golden set: {len(cases)} cases\n")
    
    hits = 0
    misses = []
    
    for i, case in enumerate(cases, 1):
        description = case["description"]
        expected = case.get("expected_primary", [])
        notes = case.get("notes", "")
        
        # Get recommendation
        rec = recommend_for_product(data, search, description, aliases=aliases, qco_db=qco_db)
        
        # Check if any expected standard is in primary
        found = [r.designation for r in rec.primary]
        
        hit = any(exp in found for exp in expected if exp)
        
        if hit or not expected:
            hits += 1
            status = "[PASS]"
        else:
            status = "[FAIL]"
            misses.append({
                "case": i,
                "description": description,
                "expected": expected,
                "found": found,
                "notes": notes,
            })
        
        print(f"{status} Case {i:2d}: {description[:50]}")
        if found:
            print(f"         -> {', '.join(found[:3])}")
    
    print(f"\n{'='*80}")
    print(f"RESULTS: {hits}/{len(cases)} passed ({100*hits//len(cases)}%)")
    print(f"{'='*80}\n")
    
    if misses:
        print("MISSES:\n")
        for miss in misses:
            print(f"Case {miss['case']}: {miss['description']}")
            print(f"  Expected: {miss['expected']}")
            print(f"  Found: {miss['found']}")
            if miss['notes']:
                print(f"  Note: {miss['notes']}")
            print()
    
    print(f"\nEvaluation complete.")


if __name__ == "__main__":
    main()
