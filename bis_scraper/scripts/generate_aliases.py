#!/usr/bin/env python3
"""Generate product_aliases.json from corpus titles."""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bis_rag.data import BisData

def main():
    # Load corpus
    data = BisData(Path(__file__).parent.parent / "bis_data")
    standards = data.standards()
    
    # Extract products from titles
    product_map = {}
    
    for std in standards:
        title = std.title
        designation = std.designation
        
        # Skip non-product standards
        skip_words = ['Method', 'Code of practice', 'Glossary', 'Terminology', 'Index']
        if any(w in title for w in skip_words):
            continue
        
        # Extract product phrase
        for prefix in ['Specification for ', 'Specification of ']:
            if title.startswith(prefix):
                phrase = title[len(prefix):].strip()
                # Normalize
                phrase_lower = phrase.lower()
                
                if phrase_lower not in product_map:
                    product_map[phrase_lower] = {
                        'designations': [],
                        'phrase': phrase
                    }
                product_map[phrase_lower]['designations'].append(designation)
                break
    
    # Build the alias file
    products_list = []
    for phrase_lower, d in sorted(product_map.items()):
        products_list.append({
            'phrase': phrase_lower,
            'designations': sorted(list(set(d['designations']))),
            'aliases': [],
            'sector': None
        })
    
    # Hand-curated aliases and sectors for common products
    common_aliases = {
        'ordinary portland cement': {
            'aliases': ['opc', 'portland cement'],
            'sector': 'cement'
        },
        '43 grade ordinary portland cement': {
            'aliases': ['opc 43', '43 grade opc'],
            'sector': 'cement'
        },
        '53 grade ordinary portland cement': {
            'aliases': ['opc 53', '53 grade opc'],
            'sector': 'cement'
        },
        'portland slag cement': {
            'aliases': ['psc', 'slag cement'],
            'sector': 'cement'
        },
        'steel reinforcement bars': {
            'aliases': ['rebar', 'tmt', 'thermo mechanically treated'],
            'sector': 'steel'
        },
        'mild steel pipes': {
            'aliases': ['ms pipe', 'black iron pipe'],
            'sector': 'steel'
        },
        'plain and reinforced concrete': {
            'aliases': ['concrete', 'rcc', 'reinforced concrete'],
            'sector': 'construction'
        },
        'code of practice for design, fabrication and erection of steel structures': {
            'aliases': ['steel structure code', 'steel design code'],
            'sector': 'construction'
        },
        'drinking water': {
            'aliases': ['potable water', 'water for drinking'],
            'sector': 'water'
        },
        'safety code for industrial lifts and hoists': {
            'aliases': ['lift safety', 'hoist safety'],
            'sector': 'safety'
        },
    }
    
    # Merge hand-curated data
    for product in products_list:
        key = product['phrase']
        if key in common_aliases:
            product['aliases'] = common_aliases[key].get('aliases', [])
            product['sector'] = common_aliases[key].get('sector')
    
    # Write output
    output = {
        'version': 1,
        'generated_from': 'bis_data standards titles + hand-curated aliases',
        'products': products_list
    }
    
    output_path = Path(__file__).parent.parent / 'bis_data' / 'product_aliases.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"✓ Generated {len(products_list)} product entries")
    print(f"✓ Saved to {output_path}")
    print(f"\nSample entries:")
    for p in products_list[:5]:
        print(f"  {p['phrase']}: {p['designations'][:2]}")

if __name__ == '__main__':
    main()
