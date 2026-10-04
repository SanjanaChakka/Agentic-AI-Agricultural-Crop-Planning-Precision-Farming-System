"""Command-line entry point for building the FAISS knowledge index.

Run with::

    python -m app.rag.build

The API builds the index automatically on first start and rebuilds it when the
corpus checksum changes, so this script is only needed to pre-build the index
(for a slimmer container image, or to verify the corpus offline). It is the
command referenced by the ``503`` raised from ``/api/v1/knowledge/search`` when
retrieval is unavailable.
"""

from __future__ import annotations

import argparse

from app.core.logging import get_logger
from app.rag.retriever import KnowledgeRetriever

logger = get_logger(__name__)


def main() -> int:
    """Build the index and report what was produced.

    Returns a process exit code: ``0`` on success, ``1`` if the corpus could not
    be indexed.
    """
    parser = argparse.ArgumentParser(description="Build the FAISS knowledge index")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild even when a cached index matches the corpus checksum.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print the final status line.",
    )
    args = parser.parse_args()

    retriever = KnowledgeRetriever()
    ok = retriever.load(force=args.force)

    status = retriever.status()
    if not args.quiet:
        logger.info("documents=%d chunks=%d backend=%s", status["documents"], status["chunks"], status["index_backend"])
        logger.info("embedding=%s dimension=%s", status["embedding"], status["dimension"])
        if status.get("built_at"):
            logger.info("built_at=%s", status["built_at"])

    logger.info(
        "knowledge index: %s - %s chunks via %s",
        "ok" if ok else "FAILED",
        status["chunks"],
        status["index_backend"],
    )
    if not ok:
        logger.error("reason: %s", status.get("detail"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
