# 📍 WHERE IS MY DATA - Complete Visual Guide

## 🎯 Main Location

```
d:\Dprojects\sih108\landing-page\bis_scraper\bis_data\
```

**Copy this path and paste it in File Explorer to go directly there!**

---

## 📂 Visual File Structure

```
bis_data/
│
├── 📄 MERGED/ (START HERE!) ⭐⭐⭐
│   ├── merged_standards.csv           ← Open in Excel (197 rows)
│   ├── merged_standards.json          ← For programming
│   └── merged_standards.jsonl         ← For streaming
│
├── 🧠 RAG/
│   ├── chunked_documents.jsonl        ← 9,043 chunks (embed these)
│   ├── knowledge_base.jsonl           ← 197 structured entries
│   ├── qa_pairs.jsonl                 ← 985 Q&A pairs
│   ├── search_corpus.jsonl            ← Full-text search
│   ├── knowledge_base.json            ← Full KB structure
│   └── metadata_index.json            ← Navigation indices
│
├── 🗂️ SEMANTIC/
│   ├── category_hierarchy.json        ← 14 domains organized
│   ├── cross_references.json          ← 17 version chains
│   ├── domain_ontology.json           ← Domain structure
│   ├── temporal_index.json            ← Year/decade tracking
│   └── search_facets.json             ← Search filtering
│
├── 📜 ARCHIVE/
│   ├── items.jsonl                    ← 500 raw archive items
│   └── text/                          ← 197 OCR text files
│       ├── gov.in.is.1.1968.txt       ← National Flag
│       ├── gov.in.is.10.2.2013.txt    ← Plywood standards
│       ├── gov.in.is.101.2.1.2018.txt ← Paint testing
│       ├── gov.in.is.10052.1.1999.txt ← Steel bars
│       └── ... 190+ more files
│
├── 🔍 INDEX/
│   └── search_index.json              ← TF-IDF search index
│
├── 💾 HTTP_CACHE/
│   └── [200+ cached files]            ← Can be deleted
│
├── 📋 COVERAGE/
│   └── [empty - BIS website changed]
│
└── ⚙️ MANDATORY/
    └── [empty - QCO list unavailable]
```

---

## 🎯 What File Should I Open?

### "I want to browse in Excel"
```
→ bis_data/merged/merged_standards.csv
  (Double-click to open)
```

### "I want all data as JSON"
```
→ bis_data/merged/merged_standards.json
  OR
→ bis_data/rag/knowledge_base.json
```

### "I want to embed chunks for RAG"
```
→ bis_data/rag/chunked_documents.jsonl
  (9,043 chunks ready)
```

### "I want to train a model"
```
→ bis_data/rag/qa_pairs.jsonl
  (985 question-answer pairs)
```

### "I want full OCR text"
```
→ bis_data/archive/text/
  (197 .txt files)
```

### "I want to find related standards"
```
→ bis_data/semantic/cross_references.json
  OR
→ bis_data/semantic/category_hierarchy.json
```

### "I want to filter by year"
```
→ bis_data/semantic/search_facets.json
  OR
→ bis_data/semantic/temporal_index.json
```

---

## 📊 Quick Reference Table

| Need | File | Location | Type | Size |
|------|------|----------|------|------|
| **Browse** | CSV | `merged/` | Spreadsheet | 132 KB |
| **Program** | JSON | `merged/` | Array | 241 KB |
| **Stream** | JSONL | `merged/` | Line-delimited | 217 KB |
| **Embed** | Chunks | `rag/` | 9,043 items | 9.3 MB |
| **Train** | QA Pairs | `rag/` | 985 pairs | 418 KB |
| **Search** | Corpus | `rag/` | 197 entries | 1.1 MB |
| **Lookup** | KB | `rag/` | Structured | 142 KB |
| **OCR** | Text files | `archive/text/` | 197 files | 2 MB |
| **Search** | Index | `index/` | TF-IDF | 4.86 MB |
| **Filter** | Facets | `semantic/` | JSON | 9 KB |
| **Navigate** | Hierarchy | `semantic/` | JSON | 23 KB |
| **Relate** | References | `semantic/` | JSON | 22 KB |
| **Timeline** | Temporal | `semantic/` | JSON | 21 KB |
| **Ontology** | Domain | `semantic/` | JSON | 82 KB |

---

## 🚀 Example: Open CSV in Excel

### Windows File Explorer
1. Press `Windows Key + E` to open File Explorer
2. Paste this in address bar: `d:\Dprojects\sih108\landing-page\bis_scraper\bis_data`
3. Click `merged` folder
4. Double-click `merged_standards.csv`
5. Opens in Excel automatically ✅

### Or Direct Path
```
d:\Dprojects\sih108\landing-page\bis_scraper\bis_data\merged\merged_standards.csv
```

---

## 📝 File Contents at a Glance

### merged_standards.csv
```
197 rows × 24 columns
Columns: canonical, designation, title, year, division, committee, 
         part, section, is_current, superseded_by, has_full_text,
         archive_url, text_path, and 12 more...
         
Example rows:
IS 1:1968         | Specification for The National Flag of India
IS 10 (Part 1):1990 | Plywood Tea-Chests: Part-1 General
IS 101 (Part 2 / Section 1):2023 | Paint Testing Methods
```

### chunked_documents.jsonl
```
9,043 JSON objects, one per line
Each object has:
- standard_id
- designation
- chunk_id (e.g., "IS|1|None|None|1968|None__chunk_0")
- chunk_index (position in standard)
- total_chunks (total for that standard)
- chunk (text content, ~500 words)
- title
- division
- committee
- year
- is_current
- archive_url
```

### qa_pairs.jsonl
```
985 JSON objects, one per line
Each object has:
- question (e.g., "What is IS 1:1968?")
- answer (linked to standard)
- metadata (standard_id, year, division, url)
```

### search_facets.json
```
5 facet dimensions:
1. division: 14 categories
2. year: range 1968-2023 (32 years with data)
3. status: current (180) or superseded (17)
4. committee: 60+ technical committees
(Plus counts for each)
```

### category_hierarchy.json
```
Organized by:
- divisions: 14 domains with standards
- committees: 40+ committees with standards
- categories: 7 IS number ranges
```

---

## 🔍 How to Access from Command Line

### Show all files in merged folder
```bash
dir "d:\Dprojects\sih108\landing-page\bis_scraper\bis_data\merged"
```

### Show all OCR files
```bash
dir "d:\Dprojects\sih108\landing-page\bis_scraper\bis_data\archive\text"
```

### Count chunks
```bash
powershell -Command "(Get-Content 'd:\Dprojects\sih108\landing-page\bis_scraper\bis_data\rag\chunked_documents.jsonl' | Measure-Object -Line).Lines"
```

### Read first chunk
```bash
powershell -Command "Get-Content 'd:\Dprojects\sih108\landing-page\bis_scraper\bis_data\rag\chunked_documents.jsonl' | Select-Object -First 1 | ConvertFrom-Json | Format-List"
```

---

## 💾 Storage Breakdown

```
Total: 28.63 MB

archive/       7.42 MB (OCR texts + metadata)
rag/          10.91 MB (chunks, KB, QA, corpus)
index/         4.86 MB (search index)
semantic/      0.15 MB (indices)
http_cache/    4.71 MB (can delete)
merged/        0.58 MB (exports)
────────────────────────
TOTAL         28.63 MB
```

---

## ✅ Verification Checklist

✓ **merged_standards.csv** - 197 rows visible in Excel
✓ **chunked_documents.jsonl** - 9,043 lines (each is a chunk)
✓ **qa_pairs.jsonl** - 985 lines (each is a Q&A pair)
✓ **archive/text/** - 197 text files
✓ **semantic/*.json** - 5 index files

---

## 🎯 Examples: What You'll See

### CSV in Excel
```
Row 1: IS 1:1968 | IS 1: Specification for The National Flag...
Row 2: IS 10 (Part 1):1990 | IS 10-1: Plywood Tea-Chests...
Row 3: IS 10 (Part 2):1996 | IS 10-2: Plywood Tea-Chests...
Row 4: IS 10 (Part 2):2013 | IS 10 : Part 2 : 2013: Plywood...
... 193 more rows
```

### Text Chunk
```
standard_id: IS|1|None|None|1968|None
designation: IS 1:1968
title: IS 1: Specification for The National Flag of India
chunk_index: 0 / 69
chunk: "Disclosure to Promote the Right To Information 
Whereas the Parliament of India has set out..."
```

### OCR File Content
```
IS 1 (1968) : Specification for The National Flag of India 
(Cotton Khadi) [TXD 8: Handloom and Khadi]

Jawaharlal Nehru
Step Out From the Old to the New

Invent a new India using knowledge.
Satyanarayan Gangaram Pitroda
```

---

## 🚀 Next Steps

1. **Open CSV:** `bis_data/merged/merged_standards.csv`
2. **Load JSON:** `bis_data/merged/merged_standards.json`
3. **Read Chunks:** `bis_data/rag/chunked_documents.jsonl`
4. **Use QA:** `bis_data/rag/qa_pairs.jsonl`
5. **Check Indices:** `bis_data/semantic/`

---

## 📞 Can't Find Something?

Check these:
- **Documentation:** `d:\Dprojects\sih108\landing-page\INDEX.md`
- **README:** `d:\Dprojects\sih108\landing-page\README_RAG.md`
- **Quick Start:** `d:\Dprojects\sih108\landing-page\START_HERE.md`

---

## ✨ Remember

**Everything is in:** `d:\Dprojects\sih108\landing-page\bis_scraper\bis_data\`

**Start with:** `merged_standards.csv` (open in Excel)

**Ready to go!** 🎉
