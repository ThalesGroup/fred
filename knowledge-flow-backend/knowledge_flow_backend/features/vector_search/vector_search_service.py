# app/features/vector_search/service.py
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0 (the "License"); ...

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional, Set

from fred_core import Action, KeycloakUser, Resource, VectorSearchHit, authorize
from langchain_core.documents import Document

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.core.stores.vector.base_vector_store import AnnHit, FullTextHit, HybridHit, SearchFilter
from knowledge_flow_backend.core.stores.vector.opensearch_vector_store import OpenSearchVectorStoreAdapter
from knowledge_flow_backend.features.tag.structure import TagType
from knowledge_flow_backend.features.tag.tag_service import TagService
from knowledge_flow_backend.features.vector_search.vector_search_structures import SearchPolicyName

logger = logging.getLogger(__name__)


def _merge_attachment_and_corpus_hits(
    *,
    attachment_hits: List[VectorSearchHit],
    corpus_hits: List[VectorSearchHit],
    top_k: int,
    attachment_quota: int = 3,
) -> List[VectorSearchHit]:
    """
    Merge attachment (session-scoped) and corpus hits, ensuring attachments are represented.

    Policy:
    - Always include up to `attachment_quota` attachment hits when present.
    - Fill remaining slots with the best-scoring remaining candidates.
    """
    if top_k <= 0:
        return []
    if not attachment_hits:
        return sorted(corpus_hits, key=lambda h: h.score or 0.0, reverse=True)[:top_k]

    attachment_quota = max(0, min(int(attachment_quota), top_k))
    attachment_ranked = sorted(
        attachment_hits, key=lambda h: h.score or 0.0, reverse=True
    )
    attachment_primary = attachment_ranked[:attachment_quota]
    attachment_rest = attachment_ranked[attachment_quota:]

    remaining_ranked = sorted(
        [*attachment_rest, *corpus_hits],
        key=lambda h: h.score or 0.0,
        reverse=True,
    )
    return (attachment_primary + remaining_ranked)[:top_k]


class VectorSearchService:
    """
    Fred — Vector Search Service (policy-driven).
    Public API: `search(...)` → returns enriched VectorSearchHit for UI/agents.

    Strategies:
      - hybrid (default): ANN + BM25 via RRF; robust general choice.
      - strict          : ANN ∩ BM25 ∩ (optional) phrase; returns [] when weak.
      - semantic        : pure ANN (legacy); useful for debug/recall tests.
    """

    def __init__(self):
        ctx = ApplicationContext.get_instance()
        self.embedder = ctx.get_embedder()
        self.vector_store = ctx.get_create_vector_store(self.embedder)
        self.tag_service = TagService()
        self.crossencoder_model = ctx.get_crossencoder_model()

    # ---------- helpers -------------------------------------------------------

    async def _collect_document_ids_from_tags(self, tags_ids: Optional[List[str]], user: KeycloakUser) -> Set[str]:
        """
        Resolve UI tag_ids -> document_uids (library scoping).
        Returns an empty set when no tags provided to keep call sites simple.
        """
        if not tags_ids:
            return set()
        doc_ids: Set[str] = set()
        for tag_id in tags_ids:
            tag = await self.tag_service.get_tag_for_user(tag_id, user)
            # Tag.item_ids is expected to be a list[str] of document_uids
            doc_ids.update(tag.item_ids or [])
        return doc_ids

    async def _tags_meta_from_ids(self, tag_ids: List[str], user: KeycloakUser) -> tuple[list[str], list[str]]:
        """Resolve tag IDs to human-readable names for UI chips + full breadcrumb paths."""
        if not tag_ids:
            return [], []
        names, full_paths = [], []
        for tid in tag_ids:
            try:
                tag = await self.tag_service.get_tag_for_user(tid, user)
                if not tag:
                    continue
                names.append(tag.name)
                full_paths.append(tag.full_path)
            except Exception as e:
                logger.debug("Could not resolve tag id=%s: %s", tid, e)
        return names, full_paths

    async def _all_document_library_tags_ids(self, user: KeycloakUser) -> List[str]:
        """
        Return all library tags ids for the user.
        """
        tags = await self.tag_service.list_all_tags_for_user(user=user, tag_type=TagType.DOCUMENT)
        return [t.id for t in tags]

    async def _to_hit(self, doc: Document, score: float, rank: int, user: KeycloakUser) -> VectorSearchHit:
        """
        Convert a LangChain Document + score into a VectorSearchHit UI DTO.
        Rationale:
          - Keep this translation in one place so fields stay consistent across policies.
        """
        md = doc.metadata or {}

        # Pull both ids and names (UI displays names; filters might use ids)
        tag_ids = md.get("tag_ids") or []
        tag_names, tag_full_paths = await self._tags_meta_from_ids(tag_ids, user)
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
            repo_url = f"{web}/blob/{ref}/{path}" + (f"#L{L1}-L{L2}" if L1 and L2 else "")
        else:
            repo_url = None

        chunk_id = md.get("chunk_id")
        citation_url = f"{preview_url}#chunk={chunk_id}" if chunk_id else preview_at_url

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

    # ---------- private strategies -------------------------------------------

    async def _semantic(
        self,
        question: str,
        user: KeycloakUser,
        k: int,
        library_tags_ids: List[str],
        metadata_terms_extra: Optional[dict[str, Any]] = None,
    ) -> List[VectorSearchHit]:
        """
        Perform a semantic search using the ANN (Approximate Nearest Neighbors) strategy.
        This strategy relies purely on vector similarity.

        Args:
            question (str): The query string to search for.
            user (KeycloakUser): The user performing the search.
            k (int): The number of top results to return.
            library_tags_ids (List[str]): List of tag IDs to filter the search results by.
            document_uid (Optional[str]): Optional document UID to filter the search results by.

        Returns:
            List[VectorSearchHit]: A list of VectorSearchHit objects containing the search results.
        """
        metadata_terms: dict[str, Any] = {"retrievable": [True]}
        if metadata_terms_extra:
            metadata_terms.update(metadata_terms_extra)

        sf = SearchFilter(tag_ids=sorted(library_tags_ids) if library_tags_ids else [], metadata_terms=metadata_terms)

        try:
            ann_hits: List[AnnHit] = self.vector_store.ann_search(question, k=k, search_filter=sf)
        except Exception as e:
            logger.error("[VECTOR][SEARCH][ANN] Unexpected error during search: %s", str(e))
            raise
        if not ann_hits:
            logger.warning(
                "[VECTOR][SEARCH][ANN] no hits returned; tags=%s metadata_terms=%s question_len=%d",
                library_tags_ids,
                metadata_terms,
                len(question),
            )
        else:
            sample = [
                {
                    "score": h.score,
                    "uid": h.document.metadata.get("document_uid"),
                    "chunk": h.document.metadata.get("chunk_id"),
                    "session": h.document.metadata.get("session_id"),
                    "tag_ids": h.document.metadata.get("tag_ids"),
                    "scope": h.document.metadata.get("scope"),
                }
                for h in ann_hits[:3]
            ]
            logger.info(
                "[VECTOR][SEARCH][ANN] got %d hits (sample: %s)",
                len(ann_hits),
                sample,
            )

        return await asyncio.gather(*[self._to_hit(h.document, h.score, rank, user) for rank, h in enumerate(ann_hits, start=1)])

    async def _strict(
        self,
        question: str,
        user: KeycloakUser,
        k: int,
        library_tags_ids: List[str],
        metadata_terms_extra: Optional[dict[str, Any]] = None,
    ) -> List[VectorSearchHit]:
        """
        Perform a strict search using BM25 (Best Matching 25).
        This strategy is only available when using OpenSearch as the vector store.

        Args:
            question (str): The query string to search for.
            user (KeycloakUser): The user performing the search.
            k (int): The number of top results to return.
            library_tags_ids (List[str]): List of tag IDs to filter the search results by.

        Returns:
            List[VectorSearchHit]: A list of VectorSearchHit objects containing the search results.

        Raises:
            TypeError: If the vector_store is not an instance of OpenSearchVectorStoreAdapter.
        """
        if not isinstance(self.vector_store, OpenSearchVectorStoreAdapter):
            raise TypeError(f"Strict search requires Opensearch, but vector_store is of type {type(self.vector_store).__name__}")

        metadata_terms: dict[str, Any] = {"retrievable": [True]}
        if metadata_terms_extra:
            metadata_terms.update(metadata_terms_extra)
        search_filter = SearchFilter(tag_ids=sorted(library_tags_ids) if library_tags_ids else [], metadata_terms=metadata_terms)

        try:
            hits: List[FullTextHit] = self.vector_store.full_text_search(query=question, top_k=k, search_filter=search_filter)
        except Exception as e:
            logger.error("[VECTOR][SEARCH][FULLTEXT] Unexpected error during search: %s", str(e))
            raise

        return await asyncio.gather(*[self._to_hit(hit.document, hit.score, rank, user) for rank, hit in enumerate(hits, start=1)])

    async def _hybrid(
        self,
        question: str,
        user: KeycloakUser,
        k: int,
        library_tags_ids: List[str],
        metadata_terms_extra: Optional[dict[str, Any]] = None,
    ) -> List[VectorSearchHit]:
        """
        Hybrid search strategy that combines vector similarity and keyword matching.
        This strategy is only available when using OpenSearch as the vector store.

        Args:
            question (str): The search query.
            user (KeycloakUser): The user performing the search.
            k (int): The number of top results to retrieve.
            library_tags_ids (List[str]): The list of tag IDs to scope the search.

        Returns:
            List[VectorSearchHit]: A list of search hits with relevant metadata.

        Raises:
            TypeError: If the vector store is not an instance of OpenSearchVectorStoreAdapter.
        """
        if not isinstance(self.vector_store, OpenSearchVectorStoreAdapter):
            raise TypeError(f"Hybrid search requires Opensearch, but vector_store is of type {type(self.vector_store).__name__}")

        metadata_terms: dict[str, Any] = {"retrievable": [True]}
        if metadata_terms_extra:
            metadata_terms.update(metadata_terms_extra)
        search_filter = SearchFilter(tag_ids=sorted(library_tags_ids) if library_tags_ids else [], metadata_terms=metadata_terms)

        try:
            hits: List[HybridHit] = self.vector_store.hybrid_search(query=question, top_k=k, search_filter=search_filter)
        except Exception as e:
            logger.error("[VECTOR][SEARCH][HYBRID] Unexpected error during search: %s", str(e))
            raise

        return await asyncio.gather(*[self._to_hit(hit.document, hit.score, rank, user) for rank, hit in enumerate(hits, start=1)])

    # ---------- unified public API -------------------------------------------

    @authorize(Action.READ, Resource.DOCUMENTS)
    async def search(
        self,
        *,
        question: str,
        user: KeycloakUser,
        top_k: int = 10,
        document_library_tags_ids: Optional[List[str]] = None,
        policy_name: Optional[SearchPolicyName] = None,
        session_id: Optional[str] = None,
        include_session_scope: bool = True,
    ) -> List[VectorSearchHit]:
        """
        Args:
            question (str): The search query string.
            user (KeycloakUser): The user performing the search.
            top_k (int): The number of top results to return. Defaults to 10.
            document_library_tags_ids (Optional[List[str]]): List of tag IDs to filter the search by library.
            policy_name (Optional[SearchPolicyName]): The search policy to use (hybrid, strict, semantic). Defaults to hybrid.
            document_uid (Optional[str]): Optional document UID to filter the search results by.
        Returns:
            List[VectorSearchHit]: A list of VectorSearchHit objects containing the search results.

        Raises:
            TypeError: If the vector store does not support the selected search policy.
            Exception: For any other unexpected errors during the search process.
        """
        try:
            original_tag_ids = document_library_tags_ids or []

            policy_key = policy_name or SearchPolicyName.hybrid
            corpus_hits: List[VectorSearchHit] = []
            attachment_hits: List[VectorSearchHit] = []

            # Attachment/session-scope query (semantic vector only), optional
            if include_session_scope and session_id:
                logger.info(
                    "[VECTOR][SEARCH][ATTACH] session=%s user=%s policy=%s question=%r top_k=%d",
                    session_id,
                    user.uid,
                    policy_key,
                    question,
                    top_k,
                )
                attachment_hits = await self._semantic(
                    question=question,
                    user=user,
                    k=top_k,
                    library_tags_ids=[],  # no tag filter for attachments
                    metadata_terms_extra={
                        "user_id": [user.uid],
                        "session_id": [session_id],
                        "scope": ["session"],
                    },
                )

            # Resolve library tags only if the caller provided some; otherwise stay empty so
            # we can short-circuit when attachments already cover the request.
            document_library_tags_ids = original_tag_ids
            if not document_library_tags_ids:
                logger.info(
                    "[VECTOR][SEARCH] user=%s has not restricted library tags → fetching all visible tags",
                    user.uid,
                )
                document_library_tags_ids = await self._all_document_library_tags_ids(user)

            # Exclude session-scoped vectors from corpus/library search to avoid leakage across sessions
            corpus_metadata_extra = {"scope": ["!session"]}

            # Corpus/library query: only run when the user actually has accessible tags
            if document_library_tags_ids:
                if policy_key == SearchPolicyName.strict:
                    logger.info(
                        "[VECTOR][SEARCH][CORPUS] policy=strict tags=%s question=%r top_k=%d",
                        document_library_tags_ids,
                        question,
                        top_k,
                    )
                    corpus_hits = await self._strict(
                        question=question,
                        user=user,
                        k=top_k,
                        library_tags_ids=document_library_tags_ids,
                        metadata_terms_extra=corpus_metadata_extra,
                    )
                elif policy_key == SearchPolicyName.hybrid:
                    logger.info(
                        "[VECTOR][SEARCH][CORPUS] policy=hybrid tags=%s question=%r top_k=%d",
                        document_library_tags_ids,
                        question,
                        top_k,
                    )
                    corpus_hits = await self._hybrid(
                        question=question,
                        user=user,
                        k=top_k,
                        library_tags_ids=document_library_tags_ids,
                        metadata_terms_extra=corpus_metadata_extra,
                    )
                else:
                    logger.info(
                        "[VECTOR][SEARCH][CORPUS] policy=semantic tags=%s question=%r top_k=%d",
                        document_library_tags_ids,
                        question,
                        top_k,
                    )
                    corpus_hits = await self._semantic(
                        question=question,
                        user=user,
                        k=top_k,
                        library_tags_ids=document_library_tags_ids,
                        metadata_terms_extra=corpus_metadata_extra,
                    )

            merged = _merge_attachment_and_corpus_hits(
                attachment_hits=attachment_hits,
                corpus_hits=corpus_hits,
                top_k=top_k,
                attachment_quota=3,
            )
            logger.info(
                "[VECTOR][SEARCH] merged results attachment=%d corpus=%d forced_attachment=%d returned=%d",
                len(attachment_hits),
                len(corpus_hits),
                min(3, top_k, len(attachment_hits)),
                len(merged),
            )
            return merged

        except TypeError as e:
            logger.error("[VECTOR][SEARCH]: %s", str(e))
            raise

        except Exception as e:
            logger.error("[VECTOR][SEARCH] Unexpected error during search: %s", str(e))
            raise

    def rerank_documents(self, question: str, documents: List[VectorSearchHit], top_r: int) -> List[VectorSearchHit]:
        """
        Re-rank a list of documents using a cross-encoder model based on the relevance to a given question.

        Args:
            question (str): The query string used to re-rank the documents.
            documents (List[VectorSearchHit]): A list of VectorSearchHit objects representing the documents to be re-ranked.
            top_r (int): The number of top relevant documents to return after re-ranking.

        Returns:
            List[VectorSearchHit]: A list of VectorSearchHit objects sorted by relevance to the question, limited to top_r documents.
        """
        # Score and sort documents by relevance
        pairs = [(question, doc.content) for doc in documents]
        scores = self.crossencoder_model.predict(pairs)
        sorted_docs = sorted(zip(documents, scores), key=lambda x: x[1], reverse=True)

        # Keep top-R documents
        reranked_documents = [doc for doc, _ in sorted_docs[:top_r]]
        logger.info("[VECTOR][RERANK] Reranked %s documents, keeping top %s", len(documents), len(reranked_documents))

        return reranked_documents
