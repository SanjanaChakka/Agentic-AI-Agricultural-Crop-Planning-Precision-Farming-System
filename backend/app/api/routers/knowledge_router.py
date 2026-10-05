"""Knowledge-base (RAG) endpoints: status, documents and semantic search."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body
from sqlalchemy import select

from app.api.deps import DbSession, PageDep, RetrieverDep, paginate
from app.core.errors import ServiceUnavailableError
from app.core.logging import get_logger
from app.models.operations import ReferenceDocument
from app.schemas.common import as_source_reference
from app.schemas.operations import (
    KnowledgeChunk,
    KnowledgeQuery,
    KnowledgeQueryResponse,
    RagStatus,
    ReferenceDocumentOut,
)

logger = get_logger(__name__)
router = APIRouter(tags=["knowledge base"])


@router.get("/knowledge/status", response_model=RagStatus, summary="Retrieval index status")
def status(retriever: RetrieverDep) -> RagStatus:
    return RagStatus(
        available=retriever.available,
        index_backend=retriever.index_backend,
        documents=len(retriever.documents),
        chunks=retriever.chunk_count,
        embedding=retriever.embedding,
        dimension=retriever.dimension,
        built_at=retriever.built_at,
        detail=retriever.detail,
    )


@router.get("/knowledge/documents", response_model=list[ReferenceDocumentOut], summary="Indexed reference documents")
def documents(db: DbSession, page: PageDep, category: str | None = None) -> list[ReferenceDocumentOut]:
    statement = select(ReferenceDocument).order_by(ReferenceDocument.category, ReferenceDocument.doc_key)
    if category:
        statement = statement.where(ReferenceDocument.category == category)
    rows, _ = paginate(db, statement, page)
    return [ReferenceDocumentOut.model_validate(row, from_attributes=True) for row in rows]


@router.post("/knowledge/search", response_model=KnowledgeQueryResponse, summary="Semantic search over the corpus")
def search(
    retriever: RetrieverDep,
    payload: Annotated[KnowledgeQuery, Body()],
) -> KnowledgeQueryResponse:
    if not retriever.available:
        msg = "The retrieval index is not available. Rebuild it with " "`python -m app.rag.build` and restart the API."
        raise ServiceUnavailableError(msg)

    chunks: list[KnowledgeChunk] = []
    hits = retriever.retrieve(
        payload.query,
        top_k=payload.top_k,
        categories=[payload.category] if payload.category else None,
    )
    for chunk, score in hits:
        chunks.append(
            KnowledgeChunk(
                chunk_id=chunk.chunk_id,
                doc_key=chunk.doc_key,
                title=chunk.title,
                category=chunk.category,
                organisation=chunk.organisation,
                source_url=chunk.source_url,
                score=round(score, 4),
                text=chunk.text,
            )
        )

    return KnowledgeQueryResponse(
        query=payload.query,
        index_backend=retriever.index_backend,
        corpus_documents=len(retriever.documents),
        corpus_chunks=retriever.chunk_count,
        retrieval_mode=retriever.retrieval_mode,
        chunks=chunks,
        references=retriever.retrieve_references(payload.query, top_k=payload.top_k),
    )


@router.get("/knowledge/documents/{doc_key:path}", summary="Citations for one known document")
def document(doc_key: str, retriever: RetrieverDep) -> dict[str, Any]:
    references = retriever.retrieve_document(doc_key)
    if not references:
        msg = f"Document '{doc_key}' is not present in the retrieval index."
        raise ServiceUnavailableError(msg)
    return {
        "doc_key": doc_key,
        "references": [as_source_reference(item).model_dump(mode="json") for item in references],
    }


@router.post("/knowledge/rebuild", summary="Rebuild the retrieval index from the corpus on disk")
def rebuild(retriever: RetrieverDep) -> dict[str, Any]:
    ok = retriever.load(force=True)
    return {
        "rebuilt": ok,
        "index_backend": retriever.index_backend,
        "documents": retriever.documents,
        "chunks": retriever.chunk_count,
        "detail": retriever.detail,
    }
