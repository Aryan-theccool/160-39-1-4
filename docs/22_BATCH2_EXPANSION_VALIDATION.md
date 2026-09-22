# Batch 2 Expansion Validation Benchmark (20 Procurement Queries)

## Overview

This validation set evaluates the retrieval, rank, and grounding accuracy of the Batch 2 expanded BIS knowledge base (~300 standards / 300 total indexed).

The 20 realistic procurement queries cover newly added categories:
1. **Civil & Construction**: Ready-Mixed Concrete (IS 4926), Concrete Admixtures & Superplasticizers (IS 9103), Paving Bitumen (IS 73), Pulverized Fuel Ash / Pozzolana (IS 3812-1), Plywood for general purposes (IS 303), Flush Door Shutters (IS 2202-1), Pressed Ceramic & Vitrified Tiles (IS 15622), Vitreous China Wash Basins (IS 2556-4), Cast Iron Soil Pipes (IS 1729).
2. **Electrotechnical & Power**: Static Energy Meters (IS 13779), Transformer Operated Energy Meters (IS 14697), Distribution Transformers (IS 1180-1), Miniature Circuit Breakers (MCB) (IS/IEC 60898-1), Residual Current Circuit Breakers (RCCB) (IS 12640-1), Moulded Case Circuit Breakers (MCCB) (IS/IEC 60947-2), Stationary Storage Water Heaters (IS 2082), Electronic UPS Systems (IS 16242-1).
3. **Safety & PPE**: High Visibility Warning Clothes (IS 15809), Industrial Safety Gloves (IS 6994-1 / IS 16648), Eye/Face Protection for Welding (IS 1179).
4. **Water & Plumbing**: High Density Polyethylene (HDPE) Pipes (IS 4984), CPVC Plumbing Pipes (IS 15778), Sluice Valves (IS 14846), Submersible Borewell Pumps (IS 8034), Domestic RO Water Purifiers (IS 16240).
5. **Fire Safety & Mechanical**: Portable Fire Extinguishers (IS 15683), Fire Hose Reels (IS 884), Automatic Sprinklers (IS 15105), Fire Doors (IS 3614), Steel Wire Ropes (IS 2266), LPG Cylinders (IS 3196-1), Automotive Safety Glass (IS 2553-2).

---

## Benchmark Query Set & Expected Standards

| Query ID | Category | Procurement Query Text | Expected IS Designation | Expected Title |
| :--- | :--- | :--- | :--- | :--- |
| **B2_Q01** | Civil / Concrete | *Ready mixed concrete RMC batching transport and compressive strength testing* | **IS 4926:2003** | Ready-mixed concrete — Code of practice |
| **B2_Q02** | Civil / Concrete | *Chemical admixtures and superplasticizers for concrete workability* | **IS 9103:1999** | Concrete Admixtures — Specification |
| **B2_Q03** | Civil / Highway | *Viscosity graded paving bitumen VG 30 VG 40 for highway road construction* | **IS 73:2013** | Paving Bitumen — Specification |
| **B2_Q04** | Civil / Pozzolana | *Pulverized fuel ash fly ash for use as pozzolana in cement mortar and concrete* | **IS 3812 (Part 1):2013** | Pulverized Fuel Ash: Part 1 For Use as Pozzolana |
| **B2_Q05** | Civil / Timber | *Moisture resistant MR and boiling water resistant BWR plywood for interior joinery* | **IS 303:1989** | Plywood for general purposes — Specification |
| **B2_Q06** | Civil / Finishing | *Vitrified and glazed pressed ceramic tiles water absorption and breaking strength* | **IS 15622:2017** | Pressed Ceramic Tiles — Specification |
| **B2_Q07** | Civil / Sanitary | *Vitreous china wash basins waste hole and load bearing test requirements* | **IS 2556 (Part 4):2004** | Vitreous sanitary appliances: Part 4 Wash basins |
| **B2_Q08** | Electrical / Metering | *AC static watt hour meters class 1 and class 2 for electricity billing* | **IS 13779:1999** | AC Static Watt-hour Meters, Class 1 and 2 |
| **B2_Q09** | Electrical / Metering | *Transformer operated static energy meters class 0.2S and 0.5S for grid substations* | **IS 14697:1999** | AC Static Transformer Operated Watt-hour and VAR-hour Meters |
| **B2_Q10** | Electrical / Distribution | *Outdoor type oil immersed distribution transformers up to 2500 kVA 33 kV energy loss limits* | **IS 1180 (Part 1):2014** | Outdoor Type Oil Immersed Distribution Transformers |
| **B2_Q11** | Electrical / Switchgear | *Miniature circuit breakers MCB for overcurrent protection in household installations* | **IS/IEC 60898-1:2002** | Circuit-breakers for overcurrent protection (MCB) |
| **B2_Q12** | Electrical / Safety | *Residual current operated circuit breakers RCCB for protection against earth leakage shock* | **IS 12640 (Part 1):2008** | Residual current operated circuit-breakers (RCCBs) |
| **B2_Q13** | Electrical / Appliances | *Stationary storage type electric water heaters geysers standing heat loss test* | **IS 2082:1993** | Stationary storage type electric water heaters |
| **B2_Q14** | Safety / PPE | *High visibility warning clothes retroreflective material performance for road workers* | **IS 15809:2008** | High Visibility Warning Clothes — Specification |
| **B2_Q15** | Safety / PPE | *Eye and face protection equipment welding helmets and filters against optical radiation* | **IS 1179:1967** | Equipment for eye and face protection during welding |
| **B2_Q16** | Water / Piping | *High density polyethylene HDPE pipes PE 100 for municipal water supply distribution* | **IS 4984:2016** | High Density Polyethylene (HDPE) Pipes for Water Supply |
| **B2_Q17** | Water / Piping | *Chlorinated polyvinyl chloride CPVC pipes for potable hot and cold water plumbing* | **IS 15778:2007** | CPVC Pipes for Potable Hot and Cold Water Distribution |
| **B2_Q18** | Fire Safety / Appliances| *Portable fire extinguishers performance construction water foam powder and CO2* | **IS 15683:2018** | Portable fire extinguishers — Specification |
| **B2_Q19** | Mechanical / Gas | *Welded low carbon steel gas cylinders for domestic liquefied petroleum gas LPG* | **IS 3196 (Part 1):2013** | Welded low carbon steel gas cylinders for LPG |
| **B2_Q20** | Automotive / Safety | *Laminated and toughened safety glass for road transport automotive windscreens* | **IS 2553 (Part 2):2019** | Safety Glass: Part 2 For Road Transport |
