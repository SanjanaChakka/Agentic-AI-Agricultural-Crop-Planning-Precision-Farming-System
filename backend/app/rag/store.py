"""FAISS-backed vector store for the agricultural knowledge base.

``IndexFlatIP`` over L2-normalised vectors gives exact cosine similarity, which
is appropriate for the small corpus used here (no approximate index needed).
The index and the fitted embedder are cached on disk and rebuilt automatically
when the corpus checksum changes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import faiss
import joblib

from app.core.logging import get_logger
from app.rag.corpus import KnowledgeChunk
from app.rag.embeddings import CorpusEmbedder

logger = get_logger(__name__)

INDEX_FILE = "knowledge_index.faiss"
EMBEDDER_FILE = "knowledge_embedder.joblib"
META_FILE = "knowledge_index_meta.json"


class VectorStore:
    """Exact cosine-similarity vector store backed by FAISS."""

    backend = "faiss (IndexFlatIP, cosine)"

    def __init__(self, index: faiss.Index, embedder: CorpusEmbedder, chunks: list[KnowledgeChunk]) -> None:
        self._index = index
        self._embedder = embedder
        self._chunks = chunks
        self.built_at = datetime.now(UTC)

    # -- construction ----------------------------------------------------
    @classmethod
    def build(cls, chunks: list[KnowledgeChunk]) -> VectorStore:
        if not chunks:
            msg = "Cannot build a vector store from zero chunks"
            raise ValueError(msg)
        embedder = CorpusEmbedder().fit([chunk.text for chunk in chunks])
        vectors = embedder.transform([chunk.text for chunk in chunks])
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        logger.info("Built FAISS index with %d chunks (dim=%d)", index.ntotal, vectors.shape[1])
        return cls(index, embedder, chunks)

    # -- persistence -----------------------------------------------------
    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(directory / INDEX_FILE))
        joblib.dump(self._embedder, directory / EMBEDDER_FILE)

    @classmethod
    def load(cls, directory: Path) -> VectorStore | None:
        index_path = directory / INDEX_FILE
        embedder_path = directory / EMBEDDER_FILE
        if not index_path.exists() or not embedder_path.exists():
            return None
        try:
            index = faiss.read_index(str(index_path))
            embedder: CorpusEmbedder = joblib.load(embedder_path)
            meta_path = directory / META_FILE
            chunk_count = getattr(index, "ntotal", 0)
            if meta_path.exists():
                import json

                chunk_count = json.loads(meta_path.read_text(encoding="utf-8")).get("chunk_count", chunk_count)
            # Chunk metadata is stored alongside the index by the retriever.
            chunks_path = directory / "knowledge_chunks.joblib"
            if not chunks_path.exists():
                return None
            chunks: list[KnowledgeChunk] = joblib.load(chunks_path)
            return cls(index, embedder, chunks)
        except Exception as exc:  # noqa: BLE001 - corrupt cache must be rebuildable, not fatal
            logger.warning("Could not load cached knowledge index (%s); rebuilding", exc)
            return None

    def save_with_chunks(self, directory: Path, corpus_checksum: str) -> None:
        import json

        directory.mkdir(parents=True, exist_ok=True)
        self.save(directory)
        joblib.dump(self._chunks, directory / "knowledge_chunks.joblib")
        (directory / META_FILE).write_text(
            json.dumps(
                {
                    "corpus_checksum": corpus_checksum,
                    "chunk_count": len(self._chunks),
                    "dimension": int(self._index.d),
                    "backend": self.backend,
                    "built_at": self.built_at.isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    # -- querying --------------------------------------------------------
    def search(
        self, query: str, top_k: int, allowed_doc_keys: set[str] | None = None
    ) -> list[tuple[KnowledgeChunk, float]]:
        if not query.strip():
            return []
        query_vector = self._embedder.transform([query])
        limit = min(max(top_k * 4, top_k), max(len(self._chunks), 1))
        scores, indices = self._index.search(query_vector, limit)
        results: list[tuple[KnowledgeChunk, float]] = []
        for score, position in zip(scores[0], indices[0], strict=False):
            if position < 0:
                continue
            chunk = self._chunks[position]
            if allowed_doc_keys is not None and chunk.doc_key not in allowed_doc_keys:
                continue
            results.append((chunk, float(score)))
            if len(results) >= top_k:
                break
        return results

    @property
    def size(self) -> int:
        return int(self._index.ntotal)

    @property
    def chunks(self) -> list[KnowledgeChunk]:
        return list(self._chunks)

    @property
    def dimension(self) -> int:
        return int(self._index.d)

    @property
    def embedder_name(self) -> str:
        return self._embedder.name
