"""Agricultural RAG: corpus loading, vector index and retrieval."""

from app.rag.retriever import KnowledgeRetriever, get_retriever

__all__ = ["KnowledgeRetriever", "get_retriever"]
