"""High-level retrieval facade used by the agents.

Responsibilities:
* build / refresh the FAISS index from the curated corpus;
* execute similarity search with a minimum-score floor and optional filters;
* convert results into citable :class:`SourceReference` objects;
* persist the ingested documents so the API can list the knowledge base.

The retriever degrades gracefully: if the index cannot be built it reports
``available = False`` and agents continue with structured rule knowledge only,
recording a warning rather than fabricating references.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.corpus import KnowledgeChunk, build_chunks, corpus_checksum, load_documents
from app.rag.store import VectorStore
from app.schemas.common import SourceReference

logger = get_logger(__name__)


class KnowledgeRetriever:
    def __init__(self, index_dir: Path | None = None) -> None:
        self._index_dir = index_dir or (Path(settings.ml_artifacts_dir).parent / "rag_index")
        self._store: VectorStore | None = None
        self._documents = []
        self._corpus_checksum: str | None = None
        self._detail: str | None = None

    # -- lifecycle -------------------------------------------------------
    @property
    def available(self) -> bool:
        return self._store is not None

    @property
    def index_backend(self) -> str:
        return self._store.backend if self._store else "unavailable"

    @property
    def documents(self) -> list:
        return list(self._documents)

    @property
    def chunk_count(self) -> int:
        return self._store.size if self._store else 0

    @property
    def dimension(self) -> int | None:
        return self._store.dimension if self._store else None

    @property
    def embedding(self) -> str:
        return self._store.embedder_name if self._store else "unavailable"

    @property
    def built_at(self) -> datetime | None:
        return self._store.built_at if self._store else None

    @property
    def detail(self) -> str | None:
        return self._detail

    @property
    def chunks(self) -> list[KnowledgeChunk]:
        return self._store.chunks if self._store else []

    @property
    def retrieval_mode(self) -> str:
        return "faiss-vector-search" if self._store else "unavailable"

    def load(self, *, force: bool = False) -> bool:
        """Load or build the index.  Returns ``True`` when retrieval is usable."""
        self._documents = load_documents()
        if not self._documents:
            self._detail = "No reference documents were found in the knowledge corpus."
            logger.error(self._detail)
            return False

        checksum = corpus_checksum(self._documents)
        self._corpus_checksum = checksum

        if not force:
            cached = VectorStore.load(self._index_dir)
            if cached is not None:
                meta = self._read_meta()
                if meta.get("corpus_checksum") == checksum:
                    self._store = cached
                    self._detail = "Loaded cached knowledge index."
                    logger.info("Knowledge index loaded from cache (%d chunks)", cached.size)
                    return True

        if settings.rag_rebuild_on_startup:
            self._detail = "Index rebuilt on startup as configured."

        chunks: list[KnowledgeChunk] = build_chunks(self._documents)
        try:
            store = VectorStore.build(chunks)
            store.save_with_chunks(self._index_dir, checksum)
        except Exception as exc:
            self._detail = f"Failed to build the knowledge index: {exc}"
            logger.exception("Knowledge index build failed")
            return False

        self._store = store
        self._detail = "Knowledge index built from the curated corpus."
        return True

    def _read_meta(self) -> dict:
        meta_path = self._index_dir / "knowledge_index_meta.json"
        if not meta_path.exists():
            return {}
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):  # pragma: no cover - defensive
            return {}

    # -- querying --------------------------------------------------------
    def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        categories: list[str] | None = None,
        doc_keys: list[str] | None = None,
        min_score: float | None = None,
    ) -> list[tuple[KnowledgeChunk, float]]:
        """Return the most relevant chunks, or an empty list when unavailable."""
        if self._store is None:
            return []
        top_k = top_k or settings.rag_top_k
        floor = settings.rag_min_score if min_score is None else min_score

        allowed: set[str] | None = None
        if categories:
            allowed = {doc.doc_key for doc in self._documents if doc.category in set(categories)}
        if doc_keys:
            keys = set(doc_keys)
            allowed = keys if allowed is None else (allowed & keys)
        if allowed is not None and not allowed:
            return []

        results = self._store.search(query, top_k=max(top_k * 3, top_k), allowed_doc_keys=allowed)
        if not results:
            logger.debug("RAG query %r returned no candidates", query)
            return []

        # Lexical-semantic cosine scores are not calibrated in [0, 1]; combine an
        # absolute floor with a relative cut-off against the best match so that
        # weak-but-relevant results are not discarded and weak noise is.
        cutoff = max(floor, results[0][1] * settings.rag_relative_score_ratio)
        filtered = [(chunk, score) for chunk, score in results if score >= cutoff]
        return filtered[:top_k]

    def retrieve_references(self, query: str, **kwargs: Any) -> list[SourceReference]:
        """Return citable references for a query (deduplicated by document)."""
        references: list[SourceReference] = []
        seen: set[str] = set()
        for chunk, score in self.retrieve(query, **kwargs):
            if chunk.doc_key in seen:
                continue
            seen.add(chunk.doc_key)
            references.append(
                SourceReference(
                    doc_key=chunk.doc_key,
                    title=chunk.title,
                    category=chunk.category,
                    organisation=chunk.organisation,
                    url=chunk.source_url,
                    region=chunk.region,
                    score=round(score, 4),
                    excerpt=_excerpt(chunk.text),
                )
            )
        return references

    def retrieve_document(self, doc_key: str) -> list[SourceReference]:
        """Cite a known document directly (used for rule provenance)."""
        for doc in self._documents:
            if doc.doc_key == doc_key:
                return [
                    SourceReference(
                        doc_key=doc.doc_key,
                        title=doc.title,
                        category=doc.category,
                        organisation=doc.organisation,
                        url=doc.source_url,
                        region=doc.region,
                    )
                ]
        return []

    def status(self) -> dict:
        return {
            "available": self.available,
            "index_backend": self.index_backend,
            "documents": len(self._documents),
            "chunks": self.chunk_count,
            "embedding": self.embedding,
            "dimension": self.dimension,
            "built_at": self.built_at,
            "detail": self._detail,
        }


def _excerpt(text: str, limit: int = 320) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else f"{collapsed[:limit].rstrip()}..."


_retriever: KnowledgeRetriever | None = None


def get_retriever() -> KnowledgeRetriever:
    """Process-wide retriever singleton."""
    global _retriever  # noqa: PLW0603 - documented lazy singleton
    if _retriever is None:
        _retriever = KnowledgeRetriever()
        _retriever.load()
    return _retriever
