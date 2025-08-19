import logging
from datetime import datetime, date, timezone
from typing import Iterable, List, Tuple, Dict, Any

from langchain.embeddings.base import Embeddings
from langchain.schema.document import Document
from langchain_core.vectorstores import InMemoryVectorStore

from app.common.utils import get_embedding_model_name
from app.core.stores.vector.base_vector_store import BaseVectoreStore

logger = logging.getLogger(__name__)


def _to_json_safe(v: Any) -> Any:
    """Recursively make values JSON/Pydantic friendly:
    - datetime/date -> ISO8601 string (UTC if naive)
    - sets -> lists
    - keep dict/list traversal
    """
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, set):
        return list(v)
    if isinstance(v, dict):
        return {k: _to_json_safe(val) for k, val in v.items()}
    if isinstance(v, list):
        return [_to_json_safe(x) for x in v]
    return v


def _normalize_metadata(md: Dict[str, Any]) -> Dict[str, Any]:
    """Boundary normalization before storing metadata into the vector store."""
    md = dict(md or {})
    # Ensure known datetime fields are strings (works even if absent)
    for key in ("created", "modified", "date_added_to_kb"):
        if key in md:
            md[key] = _to_json_safe(md[key])

    # Ensure tag_ids is always a list of strings
    tag_ids = md.get("tag_ids")
    if tag_ids is None:
        md["tag_ids"] = []
    elif isinstance(tag_ids, str):
        md["tag_ids"] = [tag_ids]
    else:
        md["tag_ids"] = [str(x) for x in list(tag_ids)]

    # Make everything else JSON-safe recursively
    return _to_json_safe(md)


class InMemoryLangchainVectorStore(BaseVectoreStore):
    """
    In-Memory LangChain Vector Store.

    Dev-friendly design:
    - We normalize metadata to JSON-safe (ISO datetimes) before indexing.
    - Guarantees downstream models (e.g., VectorSearchHit) see strings for dates.
    """

    def __init__(self, embedding_model: Embeddings):
        self.embedding_model = embedding_model
        self.vectorstore = InMemoryVectorStore(embedding=embedding_model)

    def add_documents(self, documents: List[Document]) -> None:
        # Normalize metadata for every document before adding
        for d in documents:
            d.metadata = _normalize_metadata(d.metadata or {})
        self.vectorstore.add_documents(documents)

        logger.info("✅ Documents added successfully to in-memory store.")
        # Optional: quick peek for debugging
        for i, (doc_id, rec) in enumerate(self.vectorstore.store.items()):
            if i >= 3:
                break
            logger.debug("%s: %s", doc_id, rec.get("text"))

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 5,
        documents_ids: Iterable[str] | None = None,
    ) -> List[Tuple[Document, float]]:
        if documents_ids:

            def doc_filter(doc: Document) -> bool:
                doc_uid = doc.metadata.get("document_uid")
                return bool(doc_uid and doc_uid in documents_ids)

            results = self.vectorstore.similarity_search_with_score(query, k=k, filter=doc_filter)
        else:
            results = self.vectorstore.similarity_search_with_score(query, k=k)

        enriched: List[Tuple[Document, float]] = []
        for rank0, (doc, score) in enumerate(results):
            # Ensure metadata stays normalized (in case upstream mutated anything)
            md = _normalize_metadata(doc.metadata or {})
            md["score"] = float(score)
            md["rank"] = int(rank0 + 1)  # 1-based rank (matches UI)
            md["retrieved_at"] = datetime.now(timezone.utc).isoformat()
            md["embedding_model"] = get_embedding_model_name(self.embedding_model)
            md["vector_index"] = "in-memory"
            md["token_count"] = len(doc.page_content.split())  # crude estimate
            doc.metadata = md
            enriched.append((doc, score))

        return enriched

    def delete_vectors(self, document_uid: str) -> None:
        """Delete the vectors associated with a document (not implemented for LC in-memory)."""
        pass
