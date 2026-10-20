from pathlib import Path
import json

# Load the aliases file
with open("bis_data/product_aliases.json") as f:
    data = json.load(f)

# Check first product
product = data["products"][0]
print(f"First product phrase: '{product['phrase']}'")
print(f"Aliases: {product['aliases'][:3]}")
print(f"Designations: {product['designations']}")

# Simulate the lookup building
lookup = {}
for product in data.get("products", [])[:5]:  # First 5 only
    phrase = product["phrase"].lower()
    designations = product.get("designations", [])
    
    lookup[phrase] = {
        "designations": designations,
        "aliases": product.get("aliases", []),
    }
    
    for alias in product.get("aliases", []):
        lookup[alias.lower()] = {
            "designations": designations,
            "primary_phrase": phrase,
        }

print(f"\nLookup keys (first 15): {list(lookup.keys())[:15]}")
print(f"\nSearching for 'cement' in normalized='cement':")
if "cement" in lookup:
    print(f"  ✓ Found! Maps to: {lookup['cement']['designations']}")
else:
    print(f"  ✗ Not found!")

print(f"\nSearching for 'concrete' in normalized='concrete':")
if "concrete" in lookup:
    print(f"  ✓ Found! Maps to: {lookup['concrete']['designations']}")
else:
    print(f"  ✗ Not found!")

print(f"\nSearching for 'steel' in normalized='steel':")
if "steel" in lookup:
    print(f"  ✓ Found! Maps to: {lookup['steel']['designations']}")
else:
    print(f"  ✗ Not found!")
