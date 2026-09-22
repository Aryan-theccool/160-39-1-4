# Golden Query Benchmark Set (20 Queries) — Corrected Baseline

**Corpus Baseline:** 197 BIS Standards (Golden 197 Dataset)  
**Evaluation Protocol:** Top-5 Primary Hit, Top-10 Secondary Hit, Top-20 Extended Coverage, and Out-of-Corpus Isolation Grounding.  
**Corpus Status Taxonomy:**
- `IN_CORPUS`: Relevant standard exists as a single document in the 197 corpus.
- `MULTI_PART`: Relevant standard exists as a multi-part family (e.g. `IS 101`, `IS 10028`, `IS 10096`).
- `CORPUS_LIMITATION`: Real-world target standard is absent from the 197-standard subset.
- `OUT_OF_CORPUS`: Benchmark isolation query designed to verify anti-hallucination / ungrounded warning.

---

## 1. In-Corpus & Domain Benchmark Queries (Q-01 to Q-15)

| Query ID | Query | Domain | Expected Standard | Expected Title | Corpus Status | Top-5 Requirement | Top-10 Requirement | Notes |
|---|---|---|---|---|:---:|---|---|---|
| **Q-01** | Power transformer installation, selection and maintenance code | Transformers | IS 10028 (Part 1, 2, 3) | Code of practice for selection, installation and maintenance of transformers (Parts 1–3) | `MULTI_PART` | `IS 10028` (any part) at Rank 1–5 | `IS 10028` parts in Top 10 | Fully indexed 3-part family; Top-1 hit is `IS 10028-1:1985`. |
| **Q-02** | Transformer oil maintenance and testing procedures | Transformers | IS 10028 (Part 3) | Code of practice for selection, installation and maintenance of transformers, Part 3: Maintenance | `MULTI_PART` | `IS 10028 (Part 3)` or `Part 2` at Rank 1–5 | `IS 10028` series in Top 10 | Part 2 covers oil filling; Part 3 covers maintenance testing. |
| **Q-03** | PVC insulated electrical cables and flexible cords specifications | Electrical Cables | IS 694 / IS 1554 *(Target)*<br>IS 10027:2018 *(Corpus Nearest)* | PVC Insulated Cables (IS 694) / Air-Break Switch & Fuse Units (IS 10027) | `CORPUS_LIMITATION` | Expected real standard `IS 694` outside 197 corpus | Flag as outside 197 corpus | True PVC cable standards (`IS 694`, `IS 1554`) to be ingested in Step B (500 standards). |
| **Q-04** | Electric power cables copper conductors | Electrical Cables | IS 8130 *(Target)*<br>IS 10027:2018 *(Corpus Nearest)* | Conductors for Insulated Cables (IS 8130) / Air-Break Switch Units (IS 10027) | `CORPUS_LIMITATION` | Expected real standard `IS 8130` outside 197 corpus | Flag as outside 197 corpus | `IS 10027` retrieved as nearest electrotechnical item; genuine standard `IS 8130` added in Step B. |
| **Q-05** | Industrial safety helmets and head protection equipment | PPE / Safety | IS 2925 *(Target)* | Specification for Industrial Safety Helmets (IS 2925) | `CORPUS_LIMITATION` | Expected real standard `IS 2925` outside 197 corpus | Flag as outside 197 corpus | Previous label mismatch (`IS 10040` sewing hooks) corrected. `IS 2925` to be ingested in Step B. |
| **Q-06** | Personal eye protection safety goggles and face shields | PPE / Safety | IS 5983 / IS 8521 *(Target)* | Eye-Protectors (IS 5983) / Industrial Face Shields (IS 8521) | `CORPUS_LIMITATION` | Expected real standards `IS 5983`/`IS 8521` outside 197 corpus | Flag as outside 197 corpus | Previous label mismatch (`IS 10098` infrared heaters) corrected. Real eye protection standards added in Step B. |
| **Q-07** | Structural steel tubes and hollow sections for engineering | Steel Products | IS 4923 / IS 1161 *(Target)*<br>IS 10070:1982 *(Corpus Present)* | Hollow Steel Sections (IS 4923) / Abrasion Testing Machine (IS 10070) | `CORPUS_LIMITATION` | `IS 10070` appears in Top 5 (Rank 5); `IS 10021` in Top 20 (Rank 13) | `IS 10070` in Top 10 | Target structural tube standards (`IS 4923`, `IS 1161`) to be ingested in Step B. |
| **Q-08** | Steel wire ropes for lifting and mechanical engineering | Steel Products | IS 10096 (Part 1/Sec 2)<br>IS 2266 *(Target)* | Rope Drum Hoists (IS 10096-1-2) / Steel Wire Ropes (IS 2266) | `IN_CORPUS` | `IS 10096 (Part 1/Sec 2)` in Top 5 (Rank 5) | `IS 10092` in Top 20 (Rank 15) | Rope drum hoist maintenance standard retrieved in Top 5. General wire rope standard (`IS 2266`) added in Step B. |
| **Q-09** | Common burnt clay building bricks dimensions and strength | Construction | IS 10049:1981, IS 10067:1982 | Lime based blocks (IS 10049) / Material constants in building works (IS 10067) | `IN_CORPUS` | `IS 10049:1981` at Rank 1–5 | `IS 10067:1982` in Top 10 | Masonry building materials in 197 corpus retrieved accurately at Rank 1. |
| **Q-10** | Lime and silica building blocks and mortar materials | Construction | IS 10049:1981, IS 10067:1982 | Code of practice for manufacture of lime based blocks (IS 10049) | `IN_CORPUS` | `IS 10049:1981` at Rank 1 | `IS 10067:1982` in Top 10 | Direct hit for lime-based building block manufacturing code. |
| **Q-11** | Protective coatings and bitumen emulsions for waterproofing | Coatings / Civil | IS 101 (Part 7 / Section 1)<br>IS 1580 *(Target)* | Paint Film Resistance to Water (IS 101-7-1) / Bituminous Compounds (IS 1580) | `IN_CORPUS` | `IS 101-7-1` (Water Resistance) in Top 5 (Rank 2 & 4) | `IS 101` durability series in Top 10 | Corrected previous label mismatch (lime blocks `IS 10049`). Water-resistant coatings retrieved in Top 5. |
| **Q-12** | Methods of sampling and test for paints varnishes and related products | Paints / Chemical | IS 101 Series (Active Parts) | Methods of Sampling and Test for Paints, Varnishes and Related Products | `MULTI_PART` | Any `IS 101` standard part at Rank 1–5 | `IS 101` parts in Top 10 | Evaluated at multi-part family level; `IS 101-1-1:2023` retrieved at Rank 1. |
| **Q-13** | Paint test methods for optical and colour measurements | Paints / Chemical | IS 101 (Part 4 / Section 2, 4, 1) | Optical Tests: Colour (IS 101-4-2) / Gloss (IS 101-4-4) / Opacity (IS 101-4-1) | `MULTI_PART` | `IS 101 (Part 4)` series at Rank 1–5 | `IS 101-4-2` Colour in Top 10 | Complete Part 4 optical test series present; Gloss at Rank 1, Colour at Rank 2. |
| **Q-14** | Foundry moulding boxes and cast equipment specifications | Machinery / Foundry | IS 10034:1981, IS 10086:2021 | Equipment for moisture in foundry sand (IS 10034) / Moulds (IS 10086) | `IN_CORPUS` | `IS 10034` or `IS 10086` in Top 5 (Rank 1 & Rank 4) | `IS 10034`, `IS 10086`, `IS 10094` in Top 10 | Corrected label from EMC standard `IS 10052-2` to foundry standards `IS 10034` (Rank 1) and `IS 10086` (Rank 4). |
| **Q-15** | General electrical safety code for industrial installations | Electrical Safety | IS 10028 (Part 2):1981, IS 10087:1981 | Installation of transformers (IS 10028-2) / Handling electrostatic devices (IS 10087) | `IN_CORPUS` | `IS 10028 (Part 2)` at Rank 1 | `IS 10087:1981` in Top 10 | High-precision electrical installation safety hit. |

---

## 2. Out-of-Corpus Isolation Queries (Q-16 to Q-20)

| Query ID | Query | Domain | Expected Standard | Expected Title | Corpus Status | Top-5 Requirement | Top-10 Requirement | Notes |
|---|---|---|---|---|:---:|---|---|---|
| **Q-16** | Ordinary Portland cement 33 grade and 43 grade | Cement | IS 269 / IS 8112 | Ordinary Portland Cement 33 Grade (IS 269) / 43 Grade (IS 8112) | `OUT_OF_CORPUS` | Must flag ungrounded citation; zero hallucinated standard | N/A (Isolation check) | Verified out-of-corpus isolation. Standard to be ingested in Step B. |
| **Q-17** | Drinking water quality parameters and chemical limits | Drinking Water | IS 10500 | Drinking Water — Specification (IS 10500) | `OUT_OF_CORPUS` | Must flag ungrounded citation; zero hallucinated standard | N/A (Isolation check) | Verified out-of-corpus isolation. Standard to be ingested in Step B. |
| **Q-18** | Outdoor LED street lighting luminaires IP66 | LED Lighting | IS 10322 (Part 5/Sec 3) | Luminaires for Road and Street Lighting (IS 10322-5-3) | `OUT_OF_CORPUS` | Must flag ungrounded citation; zero hallucinated standard | N/A (Isolation check) | Verified out-of-corpus isolation. Standard to be ingested in Step B. |
| **Q-19** | High strength deformed steel bars for concrete rebar | Rebar Steel | IS 1786 | High Strength Deformed Steel Bars for Concrete Reinforcement (IS 1786) | `OUT_OF_CORPUS` | Must flag ungrounded citation; zero hallucinated standard | N/A (Isolation check) | Verified out-of-corpus isolation. Standard to be ingested in Step B. |
| **Q-20** | PVC insulated cables for working voltages up to 1100 V | Household Cables | IS 694 | PVC Insulated Cables for Working Voltages up to and including 1100 V (IS 694) | `OUT_OF_CORPUS` | Must flag ungrounded citation; zero hallucinated standard | N/A (Isolation check) | Verified out-of-corpus isolation. Standard to be ingested in Step B. |

---

## 3. Step B Expansion Protocol

When the corpus is expanded to 500 standards in Step B:
1. Re-run all 20 queries against the expanded vector store.
2. In-corpus queries (`IN_CORPUS` and `MULTI_PART`) must retain Rank 1–5 retrieval accuracy.
3. Queries marked `CORPUS_LIMITATION` (e.g. `IS 694`, `IS 8130`, `IS 2925`, `IS 5983`, `IS 4923`) must automatically resolve to their newly ingested Indian Standards at Rank 1.
4. Out-of-corpus isolation queries (`Q-16` to `Q-20`) whose standards are ingested (`IS 269`, `IS 10500`, `IS 10322`, `IS 1786`, `IS 694`) will transition from ungrounded flags to verified grounded citations.