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

    def _collect_document_ids_from_tags(self, tags_ids: Optional[List[str]], user: KeycloakUser) -> Optional[Set[str]]:
        if not tags_ids:
            return None
        doc_ids: Set[str] = set()
        for tag_id in tags_ids:
            tag = self.tag_service.get_tag_for_user(tag_id, user)
            # assumes Tag.item_ids is a list of document_uids
            doc_ids.update(tag.item_ids or [])
        return doc_ids

    def _tags_meta_from_ids(self, tag_ids: List[str], user: KeycloakUser) -> tuple[list[str], list[str]]:
        if not tag_ids:
            return [], []
        names, full_paths = [], []
        for tid in tag_ids:
            try:
                tag = self.tag_service.get_tag_for_user(tid, user)
                if not tag:
                    continue
                names.append(tag.name)
                full_paths.append(tag.full_path)
            except Exception as e:
                logger.debug("Could not resolve tag id=%s: %s", tid, e)
        return names, full_paths

    def _to_hit(self, doc: Document, score: float, rank: int, user: KeycloakUser) -> VectorSearchHit:
        md = doc.metadata or {}

        # Pull both ids and names (UI displays names; filters might use ids)
        tag_ids = md.get("tag_ids") or []
        tag_names, tag_full_paths = self._tags_meta_from_ids(tag_ids, user)
        uid = md.get("document_uid") or "Unknown"
        vf = md.get("viewer_fragment")
        preview_url = f"/documents/{uid}"
        preview_at_url = f"{preview_url}#{vf}" if vf else preview_url

        # optional repo link if you have these fields in flat metadata
        web = md.get("repository_web")
        ref = md.get("repo_ref") or md.get("commit") or md.get("branch")
        path = md.get("file_path")
        L1, L2 = md.get("line_start"), md.get("line_end")

        if web and ref and path:
            repo_url = f"{web}/blob/{ref}/{path}"
            if L1 and L2:
                repo_url += f"#L{L1}-L{L2}"
        else:
            repo_url = None

        chunk_id = md.get("chunk_id")
        citation_url = f"{preview_url}#chunk={chunk_id}" if chunk_id else preview_at_url
        # Build VectorSearchHit — keep keys aligned with your flat metadata contract
        return VectorSearchHit(
            # content/chunk
            content=doc.page_content,
            page=md.get("page"),
            section=md.get("section"),
            viewer_fragment=md.get("viewer_fragment"),
            # identity
            uid=uid,
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
            tag_full_paths=tag_full_paths,
            # link fields
            preview_url=preview_url,
            preview_at_url=preview_at_url,
            repo_url=repo_url,
            citation_url=citation_url,
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

        logger.debug("similarity_search question=%r k=%d doc_filter_count=%s", question, k, (len(documents_ids) if documents_ids else None))

        # vector_store returns List[Tuple[Document, float]]
        pairs: List[Tuple[Document, float]] = self.vector_store.similarity_search_with_score(question, k=k, documents_ids=documents_ids)

        # Convert + enrich for UI/agents
        hits: List[VectorSearchHit] = [self._to_hit(doc, score, rank, user) for rank, (doc, score) in enumerate(pairs, start=1)]
        return hits
