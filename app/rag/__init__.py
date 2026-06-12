"""RAG package for ASK mode — local embeddings + Chroma vector store."""

from app.rag.store import KnowledgeStore, get_knowledge_store

__all__ = ["KnowledgeStore", "get_knowledge_store"]
