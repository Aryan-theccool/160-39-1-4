"""Generate a miniature but schema-exact ``bis_data/`` tree for tests.

The field names here are copied from the generators that write the real files
(``create_rag_dataset.py``, ``create_semantic_index.py``, ``merger.write_outputs``)
-- not invented. That is the whole point: a fixture using ``text`` where the real
file says ``chunk`` would make the tests pass while the real pipeline fails,
which is precisely the bug class this package exists to prevent.

The corpus is 12 real BIS standards with genuinely different subject matter, so
retrieval quality is measurable rather than a coin flip. Two supersession chains
are included (IS 456 and IS 10500) so the compliance paths have something to
find.
"""

from __future__ import annotations

import json
from pathlib import Path

# (canonical, designation, title, division, committee, year, superseded_by, QCO)
STANDARDS: list[tuple[str, str, str, str, str, int, str, bool]] = [
    ("IS|269|None|None|1989", "IS 269:1989", "Specification for ordinary Portland cement, 33 grade",
     "Civil Engineering", "CED 2", 1989, "IS 269:2015", True),
    ("IS|269|None|None|2015", "IS 269:2015", "Specification for ordinary Portland cement, 33 grade",
     "Civil Engineering", "CED 2", 2015, "", True),
    ("IS|383|None|None|2016", "IS 383:2016",
     "Coarse and fine aggregate for concrete - Specification", "Civil Engineering", "CED 2",
     2016, "", True),
    ("IS|456|None|None|1978", "IS 456:1978",
     "Code of practice for plain and reinforced concrete", "Civil Engineering", "CED 2",
     1978, "IS 456:2000", False),
    ("IS|456|None|None|2000", "IS 456:2000",
     "Plain and reinforced concrete - Code of practice", "Civil Engineering", "CED 2",
     2000, "", True),
    ("IS|1239|None|None|2004", "IS 1239:2004",
     "Steel tubes, tubular and other wrought steel fittings - Specification",
     "Mechanical Engineering", "MTD 19", 2004, "", True),
    ("IS|4985|None|None|2000", "IS 4985:2000",
     "Unplasticized PVC pipes for potable water supplies - Specification",
     "Chemical Engineering", "CED 50", 2000, "", True),
    ("IS|1786|None|None|2008", "IS 1786:2008",
     "High strength deformed steel bars and wires for concrete reinforcement",
     "Civil Engineering", "CED 16", 2008, "", True),
    ("IS|10500|None|None|1991", "IS 10500:1991",
     "Drinking water - Specification", "Chemical Engineering", "CED 25",
     1991, "IS 10500:2012", False),
    ("IS|10500|None|None|2012", "IS 10500:2012",
     "Drinking water - Specification", "Chemical Engineering", "CED 25",
     2012, "", True),
    ("IS|1|None|None|1968", "IS 1:1968",
     "Specification for the National Flag of India", "Textiles", "TXD 8", 1968, "", False),
    ("IS|302|2|None|2009", "IS 302 (Part 2):2009",
     "Safety of household and similar electrical appliances", "Electrical", "ETD 32",
     2009, "", True),
]

#: Distinctive body text per standard, so that a query about one standard
#: should not retrieve another. Each is several chunks' worth.
BODIES: dict[str, str] = {
    "IS|269|None|None|1989": (
        "This standard covers the manufacture and chemical requirements of ordinary "
        "Portland cement. The cement shall be manufactured by intimately mixing and "
        "grinding Portland cement clinker with gypsum. Insoluble residue shall not "
        "exceed five percent by mass. Loss on ignition shall not exceed four percent. "
        "The fineness of the cement shall be measured by the specific surface area."),
    "IS|269|None|None|2015": (
        "This standard specifies the composition, manufacturing and physical "
        "requirements of 33 grade ordinary Portland cement, including the limits for "
        "magnesia, sulphuric anhydride and chloride content. Setting times measured by "
        "the Vicat apparatus shall be within the specified range for initial and final set."),
    "IS|383|None|None|2016": (
        "This standard covers the classification and grading of natural aggregates for "
        "use in concrete, including coarse aggregate, fine aggregate and manufactured "
        "sand. Sampling and testing of aggregates shall be carried out in accordance "
        "with the methods specified. Grading limits for each nominal size are tabulated."),
    "IS|456|None|None|1978": (
        "This code of practice deals with the general structural use of plain and "
        "reinforced concrete in buildings and structures, covering design, materials, "
        "workmanship and inspection. Durability requirements depend on the exposure "
        "conditions classified in this code."),
    "IS|456|None|None|2000": (
        "This code of practice covers the design and construction of plain and "
        "reinforced concrete structures in buildings. It specifies the minimum grade of "
        "concrete for different exposure conditions, nominal cover to reinforcement, "
        "durability provisions and the design of flexural and shear members. "
        "Limit state design is adopted as the basis for design."),
    "IS|1239|None|None|2004": (
        "This standard covers the requirements of steel tubes, tubular and other "
        "wrought steel fittings for use in water, gas and steam piping systems. The "
        "tubes are classified into light, medium and heavy grades according to wall "
        "thickness. Hydrostatic test pressure and galvanizing requirements are given. "
        "Dimensions and tolerances for each nominal bore are tabulated."),
    "IS|4985|None|None|2000": (
        "This standard specifies the requirements for unplasticized polyvinyl chloride "
        "pipes intended for the conveyance of potable water. The pipes shall be "
        "classified by the working pressure at which they are designed to operate. "
        "Requirements for dimensions, visual appearance, opacity and resistance to "
        "internal pressure are specified together with test methods."),
    "IS|1786|None|None|2008": (
        "This standard covers the requirements of high strength deformed steel bars and "
        "wires for use as reinforcement in concrete. The bars shall be supplied in "
        "grades Fe 415, Fe 500 and Fe 550 with specified yield strength, tensile "
        "strength and elongation. Chemical composition limits and the rib geometry that "
        "provides the bond with concrete are given."),
    "IS|10500|None|None|1991": (
        "This standard specifies the requirements for drinking water, including the "
        "tolerance limits for substances and characteristics that affect its quality. "
        "The standard covers physical, chemical and bacteriological parameters."),
    "IS|10500|None|None|2012": (
        "This standard specifies the requirements and test methods for drinking water. "
        "It prescribes limits for colour, odour, turbidity, pH, total dissolved solids, "
        "hardness, chloride, fluoride, arsenic, lead and other toxic substances, and "
        "the bacteriological requirements for potable supplies. Permissible limits are "
        "given in tables covering both acceptable and alternative sources."),
    "IS|1|None|None|1968": (
        "This standard covers the requirements for the National Flag of India, "
        "including the material, weaving, dyeing and dimenial proportions of the "
        "chakra, and the methods of test for colour fastness."),
    "IS|302|2|None|2009": (
        "This standard covers the safety requirements of household and similar "
        "electrical appliances operating at voltages up to 250 volts, including "
        "protection against electric shock, insulation resistance and temperature rise "
        "limits for electrical cables and cords."),
}

#: concepts -> member canonicals (domain_ontology.json)
CONCEPTS: dict[str, list[str]] = {
    "cement": ["IS|269|None|None|1989", "IS|269|None|None|2015"],
    "concrete": ["IS|456|None|None|1978", "IS|456|None|None|2000", "IS|383|None|None|2016"],
    "water": ["IS|10500|None|None|1991", "IS|10500|None|None|2012", "IS|4985|None|None|2000"],
    "reinforcement": ["IS|1786|None|None|2008", "IS|456|None|None|2000"],
    "pipes": ["IS|1239|None|None|2004", "IS|4985|None|None|2000"],
    "electrical": ["IS|302|2|None|2009"],
    "aggregate": ["IS|383|None|None|2016"],
    "drinking": ["IS|10500|None|None|1991", "IS|10500|None|None|2012"],
    "steel": ["IS|1239|None|None|2004", "IS|1786|None|None|2008"],
}


def _chunks(n_per: int = 4) -> list[dict]:
    """Chunk bodies the way create_rag_dataset.chunk_text does: word windows."""
    out: list[dict] = []
    for canonical, designation, title, division, committee, year, _sb, _ in STANDARDS:
        words = BODIES[canonical].split()
        size = max(1, len(words) // n_per)
        pieces = [" ".join(words[i:i + size]) for i in range(0, len(words), size)][:n_per]
        superseded_by = next(t[6] for t in STANDARDS if t[0] == canonical)
        for index, piece in enumerate(pieces):
            out.append({
                "standard_id": canonical,
                "designation": designation,
                "chunk_id": f"{canonical}__chunk_{index}",
                "chunk_index": index,
                "total_chunks": len(pieces),
                "chunk": piece,
                "title": title,
                "division": division,
                "committee": committee,
                "year": year,
                "is_current": superseded_by == "",
                "archive_url": f"https://archive.org/details/gov.in.is.{canonical.split('|')[1]}",
            })
    return out


def make_synth_data(root: Path, *, n_per_standard: int = 4) -> Path:
    """Write a complete ``bis_data/`` tree under ``root`` and return it."""
    root = Path(root)
    for sub in ("rag", "semantic", "merged", "index"):
        (root / sub).mkdir(parents=True, exist_ok=True)

    # Mark the tree as generated. `bis_rag.doctor` reads this and refuses to
    # certify an evaluation run over it: a hit rate measured on twelve
    # hand-picked standards, with a case file written to match them, is not
    # evidence about the retrieval engine.
    (root / ".synthetic_fixture.json").write_text(
        json.dumps({
            "generator": "tests/synth_bis_data.py",
            "standards": len(STANDARDS),
            "chunks_per_standard": n_per_standard,
            "warning": "Generated fixture. Not the scraped 197-standard corpus.",
        }, indent=2) + "\n", encoding="utf-8")

    chunks = _chunks(n_per_standard)
    (root / "rag" / "chunked_documents.jsonl").write_text(
        "".join(json.dumps(c) + "\n" for c in chunks), encoding="utf-8")

    kb = [{
        "id": canonical,
        "designation": designation,
        "title": title,
        "year": year,
        "division": division,
        "committee": committee,
        "part": None,
        "section": None,
        "keywords": sorted({w.strip(".,").lower() for w in title.split()
                            if len(w) > 4})[:6],
        "is_current": superseded_by == "",
        "superseded_by": superseded_by,
        "has_full_text": True,
        "archive_url": f"https://archive.org/details/gov.in.is.{canonical.split('|')[1]}",
        "license": "https://creativecommons.org/publicdomain/zero/1.0/",
    } for canonical, designation, title, division, committee, year, superseded_by, _ in STANDARDS]
    (root / "rag" / "knowledge_base.json").write_text(json.dumps(kb, indent=2), encoding="utf-8")
    (root / "rag" / "knowledge_base.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in kb), encoding="utf-8")

    corpus = [{
        "id": entry["id"],
        "designation": entry["designation"],
        "title": entry["title"],
        "year": entry["year"],
        "division": entry["division"],
        "committee": entry["committee"],
        "part": None,
        "section": None,
        "text_snippet": BODIES[entry["id"]],
        "text_length": len(BODIES[entry["id"]]),
        "searchable": True,
        "is_current": entry["is_current"],
        "archive_url": entry["archive_url"],
    } for entry in kb]
    (root / "rag" / "search_corpus.jsonl").write_text(
        "".join(json.dumps(c) + "\n" for c in corpus), encoding="utf-8")

    merged = []
    for canonical, designation, title, division, committee, year, superseded_by, compulsory in STANDARDS:
        prefix, number, part, section, yr = (canonical.split("|") + [None] * 5)[:5]
        merged.append({
            "canonical": canonical,
            "key_without_year": "|".join([prefix, number, str(part), str(section), "None", "None"]),
            "designation": designation,
            "prefix": prefix,
            "number": int(number),
            "part": None if part == "None" else int(part),
            "section": None if section == "None" else int(section),
            "year": int(yr),
            "title": title,
            "division": division,
            "section_name": division,
            "committee": committee,
            "status": "current" if superseded_by == "" else "superseded",
            "product_category": "",
            "scheme": "",
            "amendments": None,
            "superseded_by_text": superseded_by,
            "sources": ["archive"],
            "archive_identifier": f"gov.in.is.{number}.{yr}",
            "archive_url": f"https://archive.org/details/gov.in.is.{number}.{yr}",
            "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
            "text_path": "",
            "pdf_path": "",
            "has_full_text": True,
            "is_compulsory": compulsory,
            "is_current": superseded_by == "",
            "superseded_by": superseded_by,
        })
    (root / "merged" / "merged_standards.json").write_text(
        json.dumps(merged, indent=2), encoding="utf-8")

    # -- semantic ------------------------------------------------------
    divisions: dict[str, dict] = {}
    committees: dict[str, dict] = {}
    for entry in merged:
        divisions.setdefault(entry["division"], {"count": 0, "standards": []})
        divisions[entry["division"]]["standards"].append(entry["canonical"])
        divisions[entry["division"]]["count"] += 1
        committees.setdefault(entry["committee"], {"count": 0, "standards": []})
        committees[entry["committee"]]["standards"].append(entry["canonical"])
        committees[entry["committee"]]["count"] += 1
    (root / "semantic" / "category_hierarchy.json").write_text(json.dumps({
        "divisions": divisions,
        "committees": committees,
        "categories": {"Concrete and cement (1-500)": {
            "count": 2,
            "standards": ["IS|269|None|None|1989", "IS|383|None|None|2016"]}},
    }, indent=2), encoding="utf-8")

    (root / "semantic" / "cross_references.json").write_text(json.dumps({
        "supersession_chains": {
            "IS|456|None|None|1978": "IS 456:2000",
            "IS|10500|None|None|1991": "IS 10500:2012",
        },
        "related_by_division": {d: v["standards"] for d, v in divisions.items()},
        "related_by_committee": {c: v["standards"] for c, v in committees.items()},
        "latest_editions": [e["canonical"] for e in merged if e["is_current"]],
    }, indent=2), encoding="utf-8")

    domains: dict[str, dict] = {}
    for entry in merged:
        domain = domains.setdefault(entry["division"], {
            "count": 0, "standards": [], "committees": set(),
            "year_range": [entry["year"], entry["year"]]})
        domain["standards"].append({"id": entry["canonical"], "title": entry["title"],
                                    "year": entry["year"]})
        domain["count"] += 1
        domain["committees"].add(entry["committee"])
        domain["year_range"][0] = min(domain["year_range"][0], entry["year"])
        domain["year_range"][1] = max(domain["year_range"][1], entry["year"])
    for domain in domains.values():
        domain["committees"] = sorted(domain["committees"])
    (root / "semantic" / "domain_ontology.json").write_text(json.dumps({
        "domains": domains, "relationships": [],
        "concepts": {k: sorted(v) for k, v in CONCEPTS.items()},
    }, indent=2), encoding="utf-8")

    years = sorted({e["year"] for e in merged})
    (root / "semantic" / "temporal_index.json").write_text(json.dumps({
        "by_year": {str(y): {"count": sum(1 for e in merged if e["year"] == y),
                             "standards": [e["canonical"] for e in merged if e["year"] == y]}
                    for y in years},
        "by_decade": {str((y // 10) * 10): {"count": 1, "standards": [
            e["canonical"] for e in merged if (e["year"] // 10) * 10 == (y // 10) * 10]}
            for y in years},
        "evolution": {"IS 456": [{"old_year": 1978, "designation": "IS 456:1978",
                                  "superseded_by": "IS 456:2000"}]},
        "statistics": {"earliest_year": min(years), "latest_year": max(years),
                       "total_standards": len(merged),
                       "current_standards": sum(1 for e in merged if e["is_current"]),
                       "superseded_standards": sum(1 for e in merged if not e["is_current"]),
                       "average_year": sum(years) // len(years)},
    }, indent=2), encoding="utf-8")

    (root / "semantic" / "search_facets.json").write_text(json.dumps({
        "facets": {
            "division": {"type": "categorical",
                         "values": [{"name": d, "count": v["count"]}
                                    for d, v in sorted(divisions.items())]},
            "year": {"type": "range", "min": min(years), "max": max(years),
                     "values": [{"year": y, "count": sum(1 for e in merged if e["year"] == y)}
                                for y in years]},
        }
    }, indent=2), encoding="utf-8")

    _write_tfidf(root / "index" / "search_index.json")
    return root


def _write_tfidf(path: Path) -> None:
    """Build a real TF-IDF index with the repo's own SearchIndex."""
    from bis_pipeline.index import SearchIndex
    from bis_pipeline.merger import StandardRecord

    records = []
    for canonical, designation, title, division, committee, year, superseded_by, compulsory in STANDARDS:
        prefix, number, part, section, _ = (canonical.split("|") + [None] * 5)[:5]
        records.append(StandardRecord(
            canonical=canonical,
            key_without_year=f"{prefix}|{number}|{part}|{section}",
            designation=designation,
            prefix=prefix,
            number=int(number),
            part=None if part == "None" else int(part),
            section=None if section == "None" else int(section),
            year=year,
            title=title,
            division=division,
            section_name=division,
            committee=committee,
            status="current" if superseded_by == "" else "superseded",
            is_compulsory=compulsory,
            is_current=superseded_by == "",
            superseded_by=superseded_by,
            archive_url=f"https://archive.org/details/gov.in.is.{number}.{year}",
        ))
    index = SearchIndex().build(
        records,
        documents=[f"{r.designation}\n{r.title}\n{BODIES[r.canonical]}" for r in records],
        texts_for_snippets=[BODIES[r.canonical] for r in records],
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    index.save(path)
