# Quick Reference - BIS RAG System

## One-Minute Setup

```bash
cd bis_scraper
pip install -e .

# Set environment variables (Windows PowerShell)
$env:PYTHONPATH = "src"
$env:BIS_DATA_DIR = "$(pwd)\bis_data"

# Verify
python -m bis_rag doctor
```

## Common Commands

### Search
```bash
# Simple search (TF-IDF, instant)
python -m bis_rag ask "drinking water"

# Interactive REPL
python -m bis_rag repl

# With more results
python -m bis_rag ask "drinking water" -k 10

# Include superseded standards
python -m bis_rag ask "drinking water" --include-superseded
```

### Setup (One-time)
```bash
# Build vector store (takes ~30 seconds)
python -m bis_rag build

# With semantic embeddings (requires download, first time ~5 min)
pip install sentence-transformers torch
python -m bis_rag build --embedder st:BAAI/bge-large-en-v1.5

# With OpenAI API
$env:OPENAI_API_KEY = "sk-..."
python -m bis_rag build --embedder api:text-embedding-3-small
```

### Advanced
```bash
# Full system check
python -m bis_rag doctor

# Evaluate on test QA pairs
python -m bis_rag evaluate

# Check compliance
python -m bis_rag check-compliance --product "drinking water"

# Re-index (rare)
python -m bis_pipeline index
python -m bis_pipeline query "test query"
```

## Key Files

| Path | Purpose |
|------|---------|
| `bis_data/archive/text/` | 197 OCR text files |
| `bis_data/merged/` | CSV/JSON merged standards |
| `bis_data/rag/chunked_documents.jsonl` | 9,043 searchable chunks |
| `bis_data/rag/qa_pairs.jsonl` | 985 QA pairs for training |
| `bis_data/index/search_index.json` | TF-IDF index (4.9 MB) |
| `bis_data/vector_store/` | Dense embeddings (created by `build`) |
| `src/bis_rag/` | RAG system (16 modules) |
| `src/bis_pipeline/` | Extraction pipeline (11 modules) |

## What's Ready Now

✅ **Search**: `python -m bis_rag ask "query"`  
✅ **Data**: 197 standards, 9,043 chunks, 985 QA pairs  
✅ **TF-IDF Index**: Ready to use  
✅ **CLI**: Full command-line interface  

## What Needs Setup

⏳ **Vector Store**: `python -m bis_rag build`  
⏳ **Embeddings** (optional): Install `sentence-transformers`  
⏳ **LLM** (optional): Set API key or Ollama  

## Troubleshooting

```bash
# Vector store error?
python -m bis_rag build

# Memory issues?
python -m bis_rag build --embedder hash

# No results?
python -m bis_rag ask "query" --min-score 0.01

# Need LLM?
$env:GROQ_API_KEY = "gsk_..."
python -m bis_rag ask "query"
```

## GitHub

- **Source**: https://github.com/Aryan-theccool/landing-page
- **Data Only**: https://github.com/Aryan-theccool/160-39-1-4
- **Local**: `D:\Dprojects\sih108\landing-page`

## Data Stats

- **Standards**: 197 (180 current, 17 superseded)
- **Chunks**: 9,043 (~500 words, 100-word overlap)
- **QA Pairs**: 985
- **Domains**: 14
- **Years**: 1968-2023
- **Total Size**: 28.6 MB
- **Format**: CC0 (Public Domain)

## Next Step

```bash
# If you haven't already:
python -m bis_rag build

# Then try:
python -m bis_rag ask "What are drinking water standards?"
```
