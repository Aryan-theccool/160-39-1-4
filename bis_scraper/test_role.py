from bis_rag.products import classify_role
from bis_rag.data import BisData

data = BisData()
std = data.resolve_designation("IS 269:2015")

if std:
    print(f"IS 269:2015")
    print(f"  Title: {std.title}")
    print(f"  Role: {classify_role(std.title)}")
else:
    print("Standard not found!")
