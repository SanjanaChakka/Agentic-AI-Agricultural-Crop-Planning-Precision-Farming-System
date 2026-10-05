"""Loading and chunking of the curated agricultural reference corpus.

The corpus lives as plain Markdown documents with a small front-matter block so
that every retrievable chunk keeps a machine-readable citation trail
(``doc_key``, ``title``, ``organisation``, ``source_url``).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import BACKEND_ROOT
from app.core.logging import get_logger

logger = get_logger(__name__)

KNOWLEDGE_DIR = BACKEND_ROOT / "app" / "data" / "knowledge"

FRONT_MATTER_DELIMITER = "---"


@dataclass(frozen=True)
class ReferenceDocumentMeta:
    doc_key: str
    title: str
    category: str
    organisation: str
    source_url: str | None
    region: str | None
    year: str | None
    path: str
    body: str = field(repr=False, default="")

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.body.encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    doc_key: str
    title: str
    category: str
    organisation: str
    source_url: str | None
    region: str | None
    text: str
    chunk_index: int


def _parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
    """Split a Markdown document into ``(front_matter, body)``.

    A deliberately small parser is used instead of a YAML dependency; the
    accepted format is one ``key: value`` pair per line.
    """
    lines = raw.splitlines()
    if not lines or lines[0].strip() != FRONT_MATTER_DELIMITER:
        return {}, raw

    meta: dict[str, str] = {}
    body_start = 1
    for position in range(1, len(lines)):
        line = lines[position].strip()
        if line == FRONT_MATTER_DELIMITER:
            body_start = position + 1
            break
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip().lower()] = value.strip().strip('"').strip("'")

    body = "\n".join(lines[body_start:])
    return meta, body


def _chunk_text(body: str, *, target_chars: int = 900, overlap_chars: int = 180) -> list[str]:
    """Split Markdown into overlapping chunks on paragraph boundaries."""
    paragraphs = [para.strip() for para in body.split("\n\n") if para.strip()]
    chunks: list[str] = []
    buffer = ""
    for para in paragraphs:
        candidate = f"{buffer}\n\n{para}" if buffer else para
        if len(candidate) <= target_chars:
            buffer = candidate
            continue
        if buffer:
            chunks.append(buffer)
        if len(para) <= target_chars:
            buffer = para
        else:
            # Long paragraph: slice with overlap so sentences are not cut mid-word.
            start = 0
            while start < len(para):
                chunks.append(para[start : start + target_chars])
                start += target_chars - overlap_chars
            buffer = ""
    if buffer:
        chunks.append(buffer)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def load_documents(directory: Path | None = None) -> list[ReferenceDocumentMeta]:
    """Load every reference document from the corpus directory."""
    directory = directory or KNOWLEDGE_DIR
    if not directory.is_dir():
        logger.warning("Knowledge corpus directory %s does not exist", directory)
        return []

    documents: list[ReferenceDocumentMeta] = []
    for path in sorted(directory.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        meta, body = _parse_front_matter(raw)
        doc_key = meta.get("doc_key")
        if not doc_key:
            logger.warning("Skipping %s: missing doc_key in front matter", path.name)
            continue
        documents.append(
            ReferenceDocumentMeta(
                doc_key=doc_key,
                title=meta.get("title", doc_key),
                category=meta.get("category", "general"),
                organisation=meta.get("organisation", "Project reference note"),
                source_url=meta.get("source_url") or None,
                region=meta.get("region") or None,
                year=meta.get("year") or None,
                path=path.name,
                body=body.strip(),
            )
        )
    logger.info("Loaded %d reference documents from %s", len(documents), directory)
    return documents


def build_chunks(documents: list[ReferenceDocumentMeta]) -> list[KnowledgeChunk]:
    """Chunk every document, preserving citation metadata per chunk."""
    chunks: list[KnowledgeChunk] = []
    for doc in documents:
        for position, text in enumerate(_chunk_text(doc.body)):
            chunks.append(
                KnowledgeChunk(
                    chunk_id=f"{doc.doc_key}#{position}",
                    doc_key=doc.doc_key,
                    title=doc.title,
                    category=doc.category,
                    organisation=doc.organisation,
                    source_url=doc.source_url,
                    region=doc.region,
                    text=text,
                    chunk_index=position,
                )
            )
    return chunks


def corpus_checksum(documents: list[ReferenceDocumentMeta]) -> str:
    """Stable digest of the whole corpus, used to detect stale indexes."""
    digest = hashlib.sha256()
    for doc in sorted(documents, key=lambda d: d.doc_key):
        digest.update(doc.doc_key.encode("utf-8"))
        digest.update(doc.checksum.encode("utf-8"))
    return digest.hexdigest()[:32]
