#!/usr/bin/env python3
"""
Synchronize ChromaDB Vector Store with Expanded 1,000 Standards Corpus
SIH-108 · Indian Standards RAG Knowledge Base
"""

import json
import sys
import time
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path("bis_scraper/src").resolve()))

import chromadb
from bis_rag.embeddings import get_embedder

def sync_vector_store():
    print("=" * 80)
    print("SYNCHRONIZING CHROMA VECTOR STORE WITH 1,000 STANDARDS CORPUS")
    print("=" * 80)
    
    # 1. Load data
    with open("rag/knowledge_base.json", "r", encoding="utf-8") as f:
        kb = json.load(f)
    print(f"Loaded {len(kb)} standards from knowledge_base.json")
    
    with open("rag/chunked_documents.jsonl", "r", encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f if line.strip()]
    print(f"Loaded {len(chunks)} chunks from chunked_documents.jsonl")
    
    # 2. Open Chroma client
    client = chromadb.PersistentClient(path="vector_store")
    std_col = client.get_collection("bis_standards")
    chunk_col = client.get_collection("bis_chunks")
    
    existing_std_ids = set(std_col.get(include=[])["ids"])
    existing_chunk_ids = set(chunk_col.get(include=[])["ids"])
    print(f"Existing in bis_standards: {len(existing_std_ids)}")
    print(f"Existing in bis_chunks:    {len(existing_chunk_ids)}")
    
    # Identify new standards and chunks
    new_standards = [s for s in kb if s["identifier"] not in existing_std_ids]
    new_chunks = [c for c in chunks if c["chunk_id"] not in existing_chunk_ids]
    print(f"New standards to embed: {len(new_standards)}")
    print(f"New chunks to embed:    {len(new_chunks)}")
    
    # 3. Load embedder
    embedder = get_embedder("st:BAAI/bge-base-en-v1.5")
    
    # 4. Embed and insert new standards
    if new_standards:
        print("\nEmbedding new standards...")
        batch_size = 64
        for i in range(0, len(new_standards), batch_size):
            batch = new_standards[i:i + batch_size]
            texts = [f"{s['designation']} - {s['title']}\nDepartment: {s.get('department', 'General')}\n{s.get('description', '')}" for s in batch]
            embeddings = embedder.encode(texts, batch_size=len(texts))
            
            ids = [s["identifier"] for s in batch]
            metadatas = [{
                "canonical": s["identifier"],
                "designation": s["designation"],
                "title": s["title"],
                "division": s.get("department") or "General",
                "is_current": True,
                "year": int(s["designation"].split(":")[-1]) if ":" in s["designation"] and s["designation"].split(":")[-1].isdigit() else 2020,
                "archive_url": s.get("archive_url", "")
            } for s in batch]
            
            std_col.add(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=texts)
            print(f"  Inserted standards {i + len(batch)} / {len(new_standards)}")
            
    # 5. Embed and insert new chunks
    if new_chunks:
        print("\nEmbedding new chunks...")
        batch_size = 128
        for i in range(0, len(new_chunks), batch_size):
            batch = new_chunks[i:i + batch_size]
            texts = [c["chunk"] for c in batch]
            embeddings = embedder.encode(texts, batch_size=len(texts))
            
            ids = [c["chunk_id"] for c in batch]
            metadatas = [{
                "standard_id": c["standard_id"],
                "designation": c["designation"],
                "chunk_id": c["chunk_id"],
                "chunk_index": c["chunk_index"],
                "total_chunks": c["total_chunks"],
                "title": c["title"],
                "division": c["division"],
                "committee": c.get("committee", ""),
                "year": c.get("year", 2020),
                "is_current": c.get("is_current", True),
                "archive_url": c.get("archive_url", "")
            } for c in batch]
            
            chunk_col.add(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=texts)
            if (i // batch_size) % 5 == 0 or i + len(batch) >= len(new_chunks):
                print(f"  Inserted chunks {i + len(batch)} / {len(new_chunks)}")
                
    # 6. Verify final vector counts
    final_std_count = std_col.count()
    final_chunk_count = chunk_col.count()
    print("\n" + "=" * 80)
    print("VECTOR STORE SYNCHRONIZATION COMPLETE")
    print(f"Final bis_standards vector count: {final_std_count} (Target: 1,000)")
    print(f"Final bis_chunks vector count:    {final_chunk_count} (Target: 24,371)")
    print("=" * 80)
    
    assert final_std_count == 1000, f"Expected 1000 standard vectors, got {final_std_count}"
    assert final_chunk_count == 24371, f"Expected 24371 chunk vectors, got {final_chunk_count}"

if __name__ == "__main__":
    sync_vector_store()
