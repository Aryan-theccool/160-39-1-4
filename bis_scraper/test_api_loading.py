from pathlib import Path
from bis_rag.products import load_product_aliases
from bis_rag.data import BisData

# Create BisData instance
data = BisData()
print(f"BisData root: {data.root}")
print(f"File exists: {(data.root / 'product_aliases.json').exists()}")

# Try loading aliases
aliases = load_product_aliases(data.root)
print(f"Loaded {len(aliases)} aliases")

if aliases:
    print(f"Keys (first 10): {list(aliases.keys())[:10]}")
    if "cement" in aliases:
        print(f"✓ Found 'cement': {aliases['cement']['designations']}")
    else:
        print(f"✗ 'cement' NOT in aliases")
else:
    print("✗ Aliases dict is EMPTY!")
