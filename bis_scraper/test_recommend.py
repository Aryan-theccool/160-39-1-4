from bis_rag.products import recommend_for_product, load_product_aliases
from bis_rag.data import BisData
from bis_rag.hybrid import HybridSearch

data = BisData()
aliases = load_product_aliases(data.root)
search = HybridSearch(data)

print(f"Testing recommend_for_product:")
print(f"  Aliases loaded: {len(aliases)}")

rec = recommend_for_product(data, search, "cement", aliases=aliases)

print(f"\nInput: 'cement'")
print(f"  Product aliases_matched: {rec.product.aliases_matched}")
print(f"  Primary standards: {len(rec.primary)}")

if rec.primary:
    print(f"\n  Top 3 primary:")
    for std in rec.primary[:3]:
        print(f"    {std.designation}: {std.title}")
        print(f"      Score: {std.score}, Why: {std.why}")
