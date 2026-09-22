# Batch 3 Expansion Validation Benchmark

**Document ID**: `docs/24_BATCH3_EXPANSION_VALIDATION.md`  
**Execution Date**: 2026-09-22  
**Step**: STEP D3 — Controlled BIS Corpus Expansion (300 → 400 Standards)  
**Corpus State**: 400 Standards | 18,971 Chunks  
**Evaluator**: `bis_rag.hybrid.HybridSearch` (Dense BGE-base-en-v1.5 + BM25 + TF-IDF + RRF + Cross-Encoder)  

---

## 1. Executive Summary & Benchmark Metrics

| Metric | Target | Result (Raw / Denominator) | Percentage | Status |
|---|---|---|---|---|
| **Top-1 Recall** | $\ge 85\%$ | **27 / 30** | **90.0%** | **PASS** |
| **Top-5 Recall** | $\ge 90\%$ | **28 / 30** | **93.3%** | **PASS** |
| **Citation Grounding** | 100% | **30 / 30** | **100.0%** | **PASS** |
| **Average Retrieval Latency** | $< 3500\text{ ms}$ | **3058.39 ms** | — | **PASS** |
| **Corpus Integrity** | 100% | **400 / 400 Standards** | **100.0%** | **PASS** |

---

## 2. Detailed Query Results (30 Realistic Procurement Queries)

| Query ID | Procurement Category | Realistic Procurement Query | Expected Standard | Actual Top-1 Result | Top-1 Match | Top-5 Match | Latency (ms) | Notes |
|---|---|---|---|---|---|---|---|---|
| `B3-01` | Civil / Infrastructure | Cationic bitumen emulsion for road tack coat and surface dressing | `IS 8887:2018` | `IS 8887:2018` | YES | YES | 3463.7 | Highway paving tack coat staple |
| `B3-02` | Civil / Infrastructure | Precast concrete interlocking paver blocks for city footpaths and heavy traffic roads | `IS 15658:2006` | `IS 15658:2006` | YES | YES | 4197.2 | Urban infrastructure paver standard |
| `B3-03` | Civil / Masonry | Autoclaved cellular aerated concrete AAC blocks for masonry wall construction | `IS 2185 (Part 3)` | `IS 2185 (Part 3):1984` | YES | YES | 3857.9 | Green building masonry standard |
| `B3-04` | Civil / Formwork | Film faced plywood for concrete shuttering and high cycle formwork | `IS 4990:2011` | `IS 4990:2011` | YES | YES | 3096.1 | Concrete formwork shuttering |
| `B3-05` | Civil / NDT Testing | Ultrasonic pulse velocity non destructive testing method for concrete structural integrity | `IS 13311 (Part 1)` | `IS 13311 (Part 1):1992` | YES | YES | 3142.3 | Core civil QA/QC audit method |
| `B3-06` | Civil / NDT Testing | Rebound hammer test method for non destructive assessment of concrete compressive strength | `IS 13311 (Part 2)` | `IS 13311 (Part 2):1992` | YES | YES | 2763.9 | Concrete surface rebound test |
| `B3-07` | Civil / Seismic Codes | Criteria for earthquake resistant design of structures seismic zone factor and building provisions | `IS 1893 (Part 1)` | `IS 1893 (Part 1):2016` | YES | YES | 2562.3 | Foundational seismic structural code |
| `B3-08` | Civil / Seismic Codes | Ductile design and detailing of reinforced concrete structures subjected to seismic forces | `IS 13920:2016` | `IS 13920:2016` | YES | YES | 3307.2 | Mandatory companion code to IS 1893 |
| `B3-09` | Civil / Structural | Wind loads on buildings and structures design code of practice basic wind speed | `IS 875 (Part 3)` | `IS 875 (Part 3):2015` | YES | YES | 2607.5 | Structural wind engineering code |
| `B3-10` | Metallurgical / Steel | Hollow steel sections square and rectangular SHS RHS for structural use | `IS 4923:2017` | `IS 4923:1997` | YES (Part) | YES | 4457.3 | Structural tubular sections |
| `B3-11` | Water / Transmission | Centrifugally cast ductile iron DI pressure pipes for water supply and sewerage trunk lines | `IS 8329:2000` | `IS 8329:2000` | YES | YES | 3215.7 | Jal Jeevan Mission major transmission pipe |
| `B3-12` | Water / Transmission | Ductile iron fittings bends tees and collars for pressure water pipelines | `IS 9523:2000` | `IS 9523:2000` | YES | YES | 2857.4 | Ductile iron fittings standard |
| `B3-13` | Water / Utility | Glass fibre reinforced plastics GRP pipes for water supply and sewerage | `IS 12709:1994` | `IS 12709:1994` | YES | YES | 2860.6 | Large diameter corrosion proof pipes |
| `B3-14` | Water / Metering | Domestic water meters multi jet and inferential volumetric type for municipal water connections | `IS 779:1994` | `IS 779:1994` | YES | YES | 2794.7 | Municipal volumetric water meters |
| `B3-15` | Mechanical / Pumps | Submersible non-clog sewage and drainage pumps for sewage treatment plants | `IS 5600:1991` | `IS 5600:1991` | YES | YES | 2567.4 | STP non-clog pump specification |
| `B3-16` | Mechanical / Valves | Resilient seated wafer and flanged butterfly valves for waterworks and HVAC piping | `IS 13095:1991` | `IS 13095:1991` | YES | YES | 3920.3 | High performance flow control valve |
| `B3-17` | Mechanical / Valves | Swing check single door reflux non-return valves for water works pumping mains | `IS 5312 (Part 1)` | `IS 5312 (Part 1):1984` | YES | YES | 3370.3 | Water hammer prevention valve |
| `B3-18` | Renewable / Solar PV | Crystalline silicon terrestrial photovoltaic PV modules design qualification and type approval | `IS 14286:2010` | `IS 14286:2010` | YES | YES | 2852.4 | MNRE mandatory solar module standard |
| `B3-19` | Renewable / Solar Inverters | Safety of power converters for photovoltaic power systems particular requirements for solar inverters | `IS 16221 (Part 2)` | `IS 16221 (Part 2):2015` | YES | YES | 2921.0 | Grid-tied inverter safety standard |
| `B3-20` | Electrotechnical / Smart Metering | AC static direct connected watt hour smart electricity meters for smart metering | `IS 16444 (Part 1)` | `IS 16444 (Part 1):2015` | YES | YES | 3538.8 | National RDSS smart prepaid meters |
| `B3-21` | Electrotechnical / Lighting | Electronic controlgear and LED driver for LED modules street lighting | `IS 15885 (Part 2 / Section 13)` | `IS 15885 (Part 2 / Section 13):2012` | YES | YES | 3541.1 | BIS CRS LED driver standard |
| `B3-22` | Electrotechnical / Earthing | Code of practice for earthing earth pit electrode installation and chemical earthing | `IS 3043:2018` | `IS 427:2013` | NO | NO | 1583.5 | General search miss |
| `B3-23` | Electrotechnical / Lightning | Protection against lightning general principles and surge protection | `IS/IEC 62305-1` | `IS/IEC 62305-1:2010` | YES | YES | 2858.0 | International harmonized lightning code |
| `B3-24` | Electrotechnical / Motors | Line operated three phase induction motors energy efficiency classes IE2 IE3 | `IS 12615:2018` | `IS 12615:2018` | YES | YES | 2866.2 | Energy efficiency motor standard |
| `B3-25` | Electrotechnical / Energy Storage | Lithium ion secondary cells and battery packs safety requirements for energy storage | `IS 16046 (Part 2)` | `IS 16046 (Part 2):2018` | YES | YES | 2833.8 | Electric vehicles & BESS safety standard |
| `B3-26` | Electrotechnical / Cables | Aerial bunched cables XLPE insulated for low voltage overhead distribution lines | `IS 14255:1995` | `IS 14255:1995` | YES | YES | 2697.6 | Anti-theft AB cable distribution |
| `B3-27` | Mechanical / HVAC | Split air conditioners inverter room air conditioners energy performance and cooling | `IS 1391 (Part 2)` | `IS 1391 (Part 2):2018` | YES | YES | 2666.9 | Government GeM split AC staple |
| `B3-28` | Mechanical / Pressure Vessels | Code for unfired pressure vessels design fabrication welding inspection and hydrotest | `IS 2825:1969` | `IS 2825:1969` | YES | YES | 2366.0 | Industrial pressure vessels standard |
| `B3-29` | Fire Safety / Hydrants | External hydrant systems ring main landing valves and hose pipe installation maintenance | `IS 13039:2014` | `IS 3844:1989` | NO | NO | 3243.1 | Closely related hydrant code retrieved |
| `B3-30` | Fire Safety / Suppression | Gaseous clean agent automatic fire extinguishing systems physical properties and system design | `IS 15493:2004` | `IS 15493:2004` | YES | YES | 2741.7 | Data center clean agent gas suppression |

---

## 3. Metric Summary
* **Top-1 Accuracy**: $27 / 30 = 90.0\%$
* **Top-5 Accuracy**: $28 / 30 = 93.3\%$
* **Citation Isolation**: 100% (No fabricated or phantom standards introduced)
* **Average Retrieval Latency**: $3058.39\text{ ms}$
