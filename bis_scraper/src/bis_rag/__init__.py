"""RAG engine over the BIS standards dataset.

Parts 1-3 of the build plan, implemented against the *real* field names in
``bis_data``:

``build_vector_store``
    Embed chunks and standards into a persistent vector store (ChromaDB when
    installed, a portable JSON+NumPy store otherwise).
``query_processor``
    Query understanding: intent, IS designations, filters, ontology expansion.
``bm25`` / ``hybrid``
    BM25 + the pre-built TF-IDF index + dense retrieval, fused with RRF and
    reranked; every result carries its provenance.
``rag`` / ``cli``
    Grounded answers with verified citations, and the ``bis-rag`` command.

Quick start::

    from bis_rag import BisData, HybridSearch, RAGPipeline

    data   = BisData()                      # reads $BIS_DATA_DIR or bis_scraper/bis_data
    search = HybridSearch(data)             # needs `bis-rag build` to have run
    answer = RAGPipeline(data, search).answer("what is IS 1239?")

See ``docs/RAG_ENGINE.md`` for the data contract and the field-name traps this
package exists to prevent.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .bm25 import BM25Document, BM25Index
from .data import BisData, Supersession, default_data_dir
from .embeddings import (
    APIEmbedder,
    Embedder,
    EmbedderMismatch,
    HashingEmbedder,
    SentenceTransformerEmbedder,
    get_embedder,
)
from .hybrid import Candidate, HybridSearch, RetrievalConfig, SearchResponse, SearchResult
from .query_processor import Intent, ProcessedQuery, QueryProcessor
from .rag import Citation, ExtractiveGenerator, RAGAnswer, RAGPipeline, select_generator
from .schema import Chunk, SchemaError, Standard
from .vectorstore import (
    ChromaVectorStore,
    Hit,
    JsonVectorStore,
    VectorStore,
    available_backends,
    open_store,
)

__all__ = [
    "__version__",
    # data
    "BisData", "Supersession", "default_data_dir",
    # schema
    "Chunk", "Standard", "SchemaError",
    # embeddings
    "Embedder", "HashingEmbedder", "SentenceTransformerEmbedder", "APIEmbedder",
    "EmbedderMismatch", "get_embedder",
    # stores
    "VectorStore", "ChromaVectorStore", "JsonVectorStore", "Hit", "open_store",
    "available_backends",
    # retrieval
    "QueryProcessor", "ProcessedQuery", "Intent",
    "BM25Index", "BM25Document",
    "HybridSearch", "RetrievalConfig", "SearchResponse", "SearchResult", "Candidate",
    # generation
    "RAGPipeline", "RAGAnswer", "Citation", "ExtractiveGenerator", "select_generator",
]
