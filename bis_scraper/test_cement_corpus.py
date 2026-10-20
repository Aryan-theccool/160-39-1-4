from bis_rag.data import BisData

data = BisData()
standards = data.standards()

print(f"Searching for cement-related standards in corpus ({len(standards)} total):")
cement_stds = []
for std in standards:
    if "cement" in std.title.lower():
        cement_stds.append(std)
        print(f"  {std.designation}: {std.title}")

print(f"\nTotal cement standards: {len(cement_stds)}")
print(f"\nIS 269:2015 in corpus: {any(std.designation == 'IS 269:2015' for std in standards)}")
print(f"IS 1200:2012 in corpus: {any(std.designation == 'IS 1200:2012' for std in standards)}")
