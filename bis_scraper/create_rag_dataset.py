#!/usr/bin/env python3
"""
Create optimized RAG datasets from extracted standards.
Generates chunked documents, embeddings metadata, and comprehensive knowledge bases.
"""

import json
import re
from pathlib import Path
from typing import Generator, List, Dict
import pandas as pd


class RAGDatasetGenerator:
    """Generate optimized datasets for Retrieval-Augmented Generation"""
    
    def __init__(self, data_dir: str = "bis_data"):
        self.data_dir = Path(data_dir)
        self.merged_csv = self.data_dir / "merged" / "merged_standards.csv"
        self.text_dir = self.data_dir / "archive" / "text"
        self.output_dir = self.data_dir / "rag"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 100) -> List[str]:
        """Split text into overlapping chunks for better RAG retrieval"""
        chunks = []
        words = text.split()
        
        chunk_word_size = chunk_size // 5  # Rough estimate: 5 chars per word
        overlap_words = overlap // 5
        
        for i in range(0, len(words), chunk_word_size - overlap_words):
            chunk = " ".join(words[i:i + chunk_word_size])
            if chunk.strip():
                chunks.append(chunk.strip())
        
        return chunks
    
    def create_chunked_documents(self) -> int:
        """Create chunked documents for each standard"""
        print("Creating chunked documents...")
        
        df = pd.read_csv(self.merged_csv)
        chunked_docs = []
        
        for idx, row in df.iterrows():
            text_path = row['text_path']
            if pd.notna(text_path):
                full_path = Path(text_path)
                if full_path.exists():
                    try:
                        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                            text = f.read()
                        
                        chunks = self.chunk_text(text, chunk_size=500, overlap=100)
                        
                        for chunk_idx, chunk in enumerate(chunks):
                            doc = {
                                'standard_id': row['canonical'],
                                'designation': row['designation'],
                                'chunk_id': f"{row['canonical']}__chunk_{chunk_idx}",
                                'chunk_index': chunk_idx,
                                'total_chunks': len(chunks),
                                'chunk': chunk,
                                'title': row['title'],
                                'division': row['division'],
                                'committee': row['committee'],
                                'year': row['year'],
                                'is_current': row['is_current'],
                                'archive_url': row['archive_url']
                            }
                            chunked_docs.append(doc)
                    except Exception as e:
                        print(f"Error processing {text_path}: {e}")
                        continue
        
        # Save chunked documents
        output_file = self.output_dir / "chunked_documents.jsonl"
        with open(output_file, 'w') as f:
            for doc in chunked_docs:
                f.write(json.dumps(doc) + '\n')
        
        print(f"✓ Created {len(chunked_docs)} chunks from {len(df)} standards")
        return len(chunked_docs)
    
    def create_knowledge_base(self) -> int:
        """Create structured knowledge base with metadata"""
        print("Creating knowledge base...")
        
        df = pd.read_csv(self.merged_csv)
        kb_entries = []
        
        for idx, row in df.iterrows():
            # Extract keywords from title
            keywords = self.extract_keywords(str(row['title']))
            
            entry = {
                'id': row['canonical'],
                'designation': row['designation'],
                'title': row['title'],
                'year': row['year'],
                'division': row['division'],
                'committee': row['committee'],
                'part': row['part'],
                'section': row['section'],
                'keywords': keywords,
                'is_current': row['is_current'],
                'superseded_by': row['superseded_by'],
                'has_full_text': row['has_full_text'],
                'archive_url': row['archive_url'],
                'license': row['license_url']
            }
            kb_entries.append(entry)
        
        # Save as JSON and JSONL
        output_json = self.output_dir / "knowledge_base.json"
        output_jsonl = self.output_dir / "knowledge_base.jsonl"
        
        with open(output_json, 'w') as f:
            json.dump(kb_entries, f, indent=2)
        
        with open(output_jsonl, 'w') as f:
            for entry in kb_entries:
                f.write(json.dumps(entry) + '\n')
        
        print(f"✓ Created knowledge base with {len(kb_entries)} entries")
        return len(kb_entries)
    
    def create_search_corpus(self) -> int:
        """Create searchable corpus with full text and metadata"""
        print("Creating search corpus...")
        
        df = pd.read_csv(self.merged_csv)
        corpus = []
        
        for idx, row in df.iterrows():
            text_path = row['text_path']
            
            # Get full text if available
            full_text = ""
            if pd.notna(text_path):
                full_path = Path(text_path)
                if full_path.exists():
                    try:
                        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                            full_text = f.read()[:5000]  # Limit to first 5000 chars
                    except:
                        pass
            
            corpus_entry = {
                'id': row['canonical'],
                'designation': row['designation'],
                'title': row['title'],
                'year': row['year'],
                'division': row['division'],
                'committee': row['committee'],
                'part': row['part'],
                'section': row['section'],
                'text_snippet': full_text,
                'text_length': len(full_text) if full_text else 0,
                'searchable': bool(full_text),
                'is_current': row['is_current'],
                'archive_url': row['archive_url']
            }
            corpus.append(corpus_entry)
        
        output_jsonl = self.output_dir / "search_corpus.jsonl"
        with open(output_jsonl, 'w') as f:
            for entry in corpus:
                f.write(json.dumps(entry) + '\n')
        
        print(f"✓ Created search corpus with {len(corpus)} standards")
        return len(corpus)
    
    def create_qa_pairs(self) -> int:
        """Create question-answer pairs for fine-tuning"""
        print("Creating QA pairs...")
        
        df = pd.read_csv(self.merged_csv)
        qa_pairs = []
        
        for idx, row in df.iterrows():
            # Generate potential questions based on standard attributes
            questions = [
                f"What is {row['designation']}?",
                f"Tell me about {row['designation']}",
                f"What standard is about {row['title'].split(':')[0]}?",
                f"Which Indian Standard covers {row['division']}?",
                f"What is the latest standard for {row['title'].split('(')[0].strip()}?",
            ]
            
            for question in questions:
                qa_pair = {
                    'question': question,
                    'answer': f"{row['designation']}: {row['title']}",
                    'metadata': {
                        'standard_id': row['canonical'],
                        'designation': row['designation'],
                        'year': row['year'],
                        'division': row['division'],
                        'archive_url': row['archive_url']
                    }
                }
                qa_pairs.append(qa_pair)
        
        output_jsonl = self.output_dir / "qa_pairs.jsonl"
        with open(output_jsonl, 'w') as f:
            for pair in qa_pairs:
                f.write(json.dumps(pair) + '\n')
        
        print(f"✓ Created {len(qa_pairs)} QA pairs")
        return len(qa_pairs)
    
    def create_metadata_index(self) -> int:
        """Create comprehensive metadata index"""
        print("Creating metadata index...")
        
        df = pd.read_csv(self.merged_csv)
        
        # Create indices by various dimensions
        indices = {
            'by_division': {},
            'by_committee': {},
            'by_year': {},
            'by_decade': {},
            'current_standards': [],
            'superseded_standards': [],
            'multi_part_standards': []
        }
        
        for idx, row in df.iterrows():
            canonical = row['canonical']
            
            # By division
            div = row['division']
            if div not in indices['by_division']:
                indices['by_division'][div] = []
            indices['by_division'][div].append(canonical)
            
            # By committee
            comm = row['committee']
            if comm not in indices['by_committee']:
                indices['by_committee'][comm] = []
            indices['by_committee'][comm].append(canonical)
            
            # By year
            year = row['year']
            if year not in indices['by_year']:
                indices['by_year'][year] = []
            indices['by_year'][year].append(canonical)
            
            # By decade
            decade = int(row['year'] // 10) * 10
            if decade not in indices['by_decade']:
                indices['by_decade'][decade] = []
            indices['by_decade'][decade].append(canonical)
            
            # Current vs superseded
            if row['is_current']:
                indices['current_standards'].append(canonical)
            else:
                indices['superseded_standards'].append(canonical)
            
            # Multi-part
            if pd.notna(row['part']) and row['part'] != '':
                indices['multi_part_standards'].append(canonical)
        
        output_file = self.output_dir / "metadata_index.json"
        with open(output_file, 'w') as f:
            json.dump(indices, f, indent=2)
        
        print(f"✓ Created metadata index with {sum(len(v) if isinstance(v, list) else 1 for v in indices.values())} entries")
        return len(indices)
    
    def extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text"""
        # Remove common words and extract noun-like terms
        common_words = {'for', 'the', 'of', 'and', 'or', 'is', 'a', 'an', 'in', 'on', 'at', 'to', 'from', 'with', 'by', 'be', 'part', 'method'}
        
        words = text.lower().split()
        keywords = [w.strip('.,()[]') for w in words if w.lower() not in common_words and len(w) > 3]
        
        return list(set(keywords))[:10]  # Top 10 unique keywords
    
    def generate_all(self) -> Dict[str, int]:
        """Generate all RAG datasets"""
        print("\n" + "="*60)
        print("GENERATING COMPREHENSIVE RAG DATASETS")
        print("="*60 + "\n")
        
        results = {
            'chunked_documents': self.create_chunked_documents(),
            'knowledge_base': self.create_knowledge_base(),
            'search_corpus': self.create_search_corpus(),
            'qa_pairs': self.create_qa_pairs(),
            'metadata_indices': self.create_metadata_index(),
        }
        
        print("\n" + "="*60)
        print("GENERATION COMPLETE!")
        print("="*60)
        print("\nGenerated files in bis_data/rag/:")
        print(f"  ✓ chunked_documents.jsonl     - {results['chunked_documents']} chunks")
        print(f"  ✓ knowledge_base.json         - {results['knowledge_base']} entries")
        print(f"  ✓ knowledge_base.jsonl        - {results['knowledge_base']} entries")
        print(f"  ✓ search_corpus.jsonl         - {results['search_corpus']} standards")
        print(f"  ✓ qa_pairs.jsonl              - {results['qa_pairs']} QA pairs")
        print(f"  ✓ metadata_index.json         - Dimensional indices")
        
        return results


if __name__ == "__main__":
    generator = RAGDatasetGenerator()
    generator.generate_all()
