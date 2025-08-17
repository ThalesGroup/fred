# app/features/vector_search/service.py

import logging
from datetime import datetime, timezone
from typing import List, Optional, Set, Tuple

from fred_core import KeycloakUser
from fred_core import VectorSearchHit 
from langchain.schema.document import Document

from app.application_context import ApplicationContext
from app.features.tag.service import TagService

logger = logging.getLogger(__name__)


class VectorSearchService:
    """
    Vector Search Service
    ------------------------------------------------------
    Returns enriched VectorSearchHit objects ready for agents/UI.
    """

    def __init__(self):
        ctx = ApplicationContext.get_instance()
        self.embedder = ctx.get_embedder()
        self.vector_store = ctx.get_create_vector_store(self.embedder)
        self.tag_service = TagService()

    def _collect_document_ids_from_tags(
        self, tags_ids: Optional[List[str]], user: KeycloakUser
    ) -> Optional[Set[str]]:
        if not tags_ids:
            return None
        doc_ids: Set[str] = set()
        for tag_id in tags_ids:
            tag = self.tag_service.get_tag_for_user(tag_id, user)
            # assumes Tag.item_ids is a list of document_uids
            doc_ids.update(tag.item_ids or [])
        return doc_ids

    def _tag_names_from_ids(self, tag_ids: List[str], user: KeycloakUser) -> List[str]:
        if not tag_ids:
            return []
        # Provide a bulk method in TagService if you don't have one yet.
        names: List[str] = []
        for tid in tag_ids:
            try:
                t = self.tag_service.get_tag_for_user(tid, user)
                if t and t.name:
                    names.append(t.name)
            except Exception:
                # non-fatal: missing tag or no access
                logger.debug("Could not resolve tag name for id=%s", tid)
        return names

    def _to_hit(
        self, doc: Document, score: float, rank: int, user: KeycloakUser
    ) -> VectorSearchHit:
        md = doc.metadata or {}

        # Pull both ids and names (UI displays names; filters might use ids)
        tag_ids = md.get("tag_ids") or []
        tag_names = self._tag_names_from_ids(tag_ids, user)

        # Build VectorSearchHit — keep keys aligned with your flat metadata contract
        return VectorSearchHit(
            # content/chunk
            content=doc.page_content,
            page=md.get("page"),
            section=md.get("section"),
            viewer_fragment=md.get("viewer_fragment"),

            # identity
            uid=md.get("document_uid") or "Unknown",
            title=md.get("title") or md.get("document_name") or "Unknown",
            author=md.get("author"),
            created=md.get("created"),
            modified=md.get("modified"),

            # file/source
            file_name=md.get("document_name"),
            file_path=md.get("source") or md.get("file_path"),
            repository=md.get("repository"),
            pull_location=md.get("pull_location"),
            language=md.get("language"),
            mime_type=md.get("mime_type"),
            type=md.get("type") or "document",

            # tags
            tag_ids=tag_ids,
            tag_names=tag_names,

            # access (if you indexed them)
            license=md.get("license"),
            confidential=md.get("confidential"),

            # metrics & provenance
            score=score,
            rank=rank,
            embedding_model=str(md.get("embedding_model") or "unknown_model"),
            vector_index=md.get("vector_index") or "unknown_index",
            token_count=md.get("token_count"),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            retrieval_session_id=md.get("retrieval_session_id"),
        )

    def similarity_search_with_score(
        self,
        question: str,
        user: KeycloakUser,
        k: int = 10,
        tags_ids: Optional[List[str]] = None,
    ) -> List[VectorSearchHit]:
        # TODO auth: ensure user may query across requested tags/documents
        documents_ids = self._collect_document_ids_from_tags(tags_ids, user)

        logger.debug(
            "similarity_search question=%r k=%d doc_filter_count=%s",
            question, k, (len(documents_ids) if documents_ids else None)
        )

        # vector_store returns List[Tuple[Document, float]]
        pairs: List[Tuple[Document, float]] = self.vector_store.similarity_search_with_score(
            question, k=k, documents_ids=documents_ids
        )

        # Convert + enrich for UI/agents
        hits: List[VectorSearchHit] = [
            self._to_hit(doc, score, rank, user)
            for rank, (doc, score) in enumerate(pairs, start=1)
        ]
        return hits
