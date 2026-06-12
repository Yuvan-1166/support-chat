"""Local RAG knowledge store backed by Chroma + sentence-transformers.

ASK mode retrieves grounding chunks from here.  Embeddings run in-process via
a local sentence-transformers model — no API key, no external calls.

Heavy imports (``chromadb``, ``sentence_transformers``) are deferred to first
use so the rest of the app boots fast and stays importable in environments
where the models aren't downloaded yet.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class KnowledgeStore:
    """Thin wrapper over a persistent Chroma collection.

    Uses a sentence-transformers embedding function so both ingestion and
    query embed text with the same local model.
    """

    def __init__(
        self,
        *,
        persist_dir: Optional[str] = None,
        collection_name: Optional[str] = None,
        embedding_model: Optional[str] = None,
    ) -> None:
        settings = get_settings()
        self._persist_dir = persist_dir or settings.CHROMA_DIR
        self._collection_name = collection_name or settings.CHROMA_COLLECTION
        self._embedding_model = embedding_model or settings.EMBEDDING_MODEL
        self._collection = None  # lazy

    # ── lazy collection ──────────────────────────────────────────────────
    def _get_collection(self):
        if self._collection is not None:
            return self._collection

        import chromadb
        from chromadb.utils import embedding_functions

        client = chromadb.PersistentClient(path=self._persist_dir)
        embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=self._embedding_model
        )
        self._collection = client.get_or_create_collection(
            name=self._collection_name,
            embedding_function=embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "Chroma collection '%s' ready at %s (model=%s)",
            self._collection_name,
            self._persist_dir,
            self._embedding_model,
        )
        return self._collection

    # ── public API ───────────────────────────────────────────────────────
    def count(self) -> int:
        try:
            return self._get_collection().count()
        except Exception:  # pragma: no cover
            logger.exception("Chroma count failed")
            return 0

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        """Insert or replace chunks."""
        if not ids:
            return
        self._get_collection().upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )
        logger.info("Upserted %d chunks into '%s'", len(ids), self._collection_name)

    def reset(self) -> None:
        """Delete and recreate the collection (full re-ingest)."""
        import chromadb

        client = chromadb.PersistentClient(path=self._persist_dir)
        try:
            client.delete_collection(self._collection_name)
        except Exception:
            logger.debug("Collection '%s' did not exist", self._collection_name)
        self._collection = None
        self._get_collection()

    def retrieve(self, query: str, k: Optional[int] = None) -> list[dict[str, Any]]:
        """Return the top-*k* matching chunks for *query*.

        Each item: ``{"text": str, "metadata": dict, "distance": float}``.
        Returns an empty list when the store is empty or a query fails.
        """
        top_k = k or get_settings().RAG_TOP_K
        try:
            collection = self._get_collection()
            if collection.count() == 0:
                return []
            res = collection.query(query_texts=[query], n_results=top_k)
        except Exception:  # pragma: no cover
            logger.exception("RAG retrieval failed")
            return []

        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        out: list[dict[str, Any]] = []
        for i, text in enumerate(docs):
            out.append(
                {
                    "text": text,
                    "metadata": metas[i] if i < len(metas) else {},
                    "distance": dists[i] if i < len(dists) else None,
                }
            )
        return out


@lru_cache
def get_knowledge_store() -> KnowledgeStore:
    """Return a cached singleton knowledge store."""
    return KnowledgeStore()
