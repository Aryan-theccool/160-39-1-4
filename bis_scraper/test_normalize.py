from bis_rag.products import normalize_product, load_product_aliases
from bis_rag.data import BisData

data = BisData()
aliases = load_product_aliases(data.root)

print(f"Testing normalization:")
print(f"  Aliases loaded: {len(aliases)}")

product = normalize_product("cement", aliases)
print(f"\nInput: 'cement'")
print(f"  Normalized: '{product.normalized}'")
print(f"  Aliases matched: {product.aliases_matched}")

if product.aliases_matched:
    print(f"  ✓ Alias matching WORKS!")
else:
    print(f"  ✗ No aliases matched!")
    print(f"  Debug: checking 'cement' in '{product.normalized}':")
    print(f"    'cement' in 'cement': {'cement' in 'cement'}")
