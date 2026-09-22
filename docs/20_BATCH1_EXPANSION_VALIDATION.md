# Batch 1 Expansion Validation Benchmark (20 Procurement Queries)

## Overview

This benchmark validates the retrieval and grounding performance of the newly expanded BIS corpus (~250 standards / 253 total indexed). It consists of 20 realistic, procurement-style technical queries covering every newly introduced domain:

1. **Civil & Structural**: Cements (IS 8112, IS 12269, IS 1489-1), High-Strength TMT Reinforcement Bars (IS 1786), Structural Hollow Sections (IS 4923), Steel Pipes & Fittings (IS 1239-1), Burnt Clay Bricks (IS 1077), Concrete Masonry Units (IS 2185-1).
2. **Electrotechnical & Cables**: PVC Domestic Cables up to 1100V (IS 694), XLPE Low Voltage Cables (IS 7098-1), XLPE Medium/High Voltage Heavy Duty Cables 3.3kV-33kV (IS 7098-2), Copper/Aluminium Conductors (IS 8130), Road & Street Lighting Luminaires (IS 10322-5-3).
3. **Safety & Personal Protective Equipment (PPE)**: Industrial Safety Helmets (IS 2925), Industrial Eye-Protectors / Goggles (IS 5983), Fall Arrest Safety Belts & Harnesses (IS 3521).
4. **Water Supply & Fluid Systems**: Potable Drinking Water Quality Limits (IS 10500), Centrifugally Cast Spun Iron Pressure Pipes (IS 1536), Rotodynamic Centrifugal Pumps (IS 5120).
5. **Fire Safety**: Internal Fire Hydrants and Hose Reels (IS 3844).

---

## Benchmark Query Set & Expectations

| Query ID | Domain / Category | Procurement Query Text | Expected IS Designation | Expected Standard Title |
| :--- | :--- | :--- | :--- | :--- |
| **BQ01** | Civil / Cement | *Ordinary Portland Cement 43 Grade physical and chemical requirements* | **IS 8112** | Ordinary Portland Cement, 43 Grade — Specification |
| **BQ02** | Civil / Cement | *Ordinary Portland Cement 53 Grade high strength specification* | **IS 12269** | Ordinary Portland Cement, 53 Grade — Specification |
| **BQ03** | Civil / Cement | *Portland Pozzolana Cement fly ash based specification for construction* | **IS 1489 (Part 1)** | Portland Pozzolana Cement — Specification: Part 1 Fly Ash Based |
| **BQ04** | Civil / Steel | *High strength deformed steel bars and wires TMT bars for concrete reinforcement* | **IS 1786** | High strength deformed steel bars and wires for concrete reinforcement |
| **BQ05** | Civil / Steel | *Hollow steel sections for structural use rectangular and square tubes* | **IS 4923** | Hollow steel sections for structural use — Specification |
| **BQ06** | Civil / Pipes | *Steel tubes tubulars and other wrought steel fittings for water gas air lines* | **IS 1239 (Part 1)** | Steel Tubes, Tubulars and Other Wrought Steel Fittings — Part 1: Steel Tubes |
| **BQ07** | Civil / Masonry | *Common burnt clay building bricks compressive strength and water absorption* | **IS 1077** | Common Burnt Clay Building Bricks — Specification |
| **BQ08** | Civil / Masonry | *Concrete masonry units hollow and solid concrete blocks specification* | **IS 2185 (Part 1)** | Concrete Masonry Units — Specification: Part 1 Hollow and Solid Concrete Blocks |
| **BQ09** | Electrical / Cables | *PVC insulated unsheathed and sheathed electric cables up to 1100V* | **IS 694** | PVC insulated unsheathed and sheathed cables / cords for working voltages up to and including 1100 V |
| **BQ10** | Electrical / Cables | *Cross-linked polyethylene XLPE insulated PVC sheathed cables up to 1.1 kV* | **IS 7098 (Part 1)** | Cross-linked Polyethylene Insulated PVC Sheathed Cables: Part 1 For Working Voltages up to and Including 1100 V |
| **BQ11** | Electrical / Cables | *XLPE insulated heavy duty electric cables for working voltages from 3.3 kV up to 33 kV* | **IS 7098 (Part 2)** | Cross-linked Polyethylene Insulated Thermoplastic Sheathed Cables: Part 2 For Working Voltages From 3.3 kV Up to and Including 33 kV |
| **BQ12** | Electrical / Conductors | *Conductors for insulated electric cables and flexible cords aluminium and copper* | **IS 8130** | Conductors for insulated electric cables and flexible cords |
| **BQ13** | Electrical / Lighting | *Luminaires for road and street lighting safety and photometric requirements* | **IS 10322 (Part 5/Sec 3)** | Luminaires — Particular requirements: Luminaires for road and street lighting |
| **BQ14** | Safety / PPE | *Industrial safety helmets impact and electrical resistance specification* | **IS 2925** | Specification for industrial safety helmets |
| **BQ15** | Safety / PPE | *Industrial eye-protectors safety goggles and visors against mechanical hazard* | **IS 5983** | Eye-protectors |
| **BQ16** | Safety / Fall Protection | *Industrial safety belts and harnesses for fall arrest specification* | **IS 3521** | Industrial safety belts and harnesses — Specification |
| **BQ17** | Water / Supply | *Drinking water acceptable and permissible limits of physical and chemical parameters* | **IS 10500** | Drinking Water — Specification |
| **BQ18** | Water / Pipes | *Centrifugally cast spun iron pressure pipes for water gas and sewage* | **IS 1536** | Centrifugally Cast (Spun) Iron Pressure Pipes for Water, Gas and Sewage |
| **BQ19** | Mechanical / Pumps | *Technical requirements for rotodynamic centrifugal pumps* | **IS 5120** | Technical requirements for rotodynamic special purpose pumps |
| **BQ20** | Fire Safety / Hydrants | *Code of practice for installation and maintenance of internal fire hydrants and hose reels* | **IS 3844** | Code of practice for installation and maintenance of internal fire hydrants and hose reels on premises |

---

## Evaluation Criteria

1. **Top-5 Retrieval Hit**: The expected standard must appear in the top 5 hybrid search results.
2. **Top-1 Primary Match**: The exact standard or designated standard part ranks #1.
3. **Citation Verifiability**: Standard has verifiable source URL (`archive_url`), non-empty OCR chunk evidence, and deterministic standard metadata.
4. **No Hallucination**: Score is based strictly on indexed content retrieval.
