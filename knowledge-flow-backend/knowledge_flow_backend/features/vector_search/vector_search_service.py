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

    async def _semantic(self, question: str, user: KeycloakUser, k: int, library_tags_ids: List[str]) -> List[VectorSearchHit]:
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

        sf = SearchFilter(tag_ids=sorted(library_tags_ids) if library_tags_ids else [], metadata_terms=metadata_terms)

        try:
            ann_hits: List[AnnHit] = self.vector_store.ann_search(question, k=k, search_filter=sf)
        except Exception as e:
            logger.error("[VECTOR][SEARCH][ANN] Unexpected error during search: %s", str(e))
            raise

        return await asyncio.gather(*[self._to_hit(h.document, h.score, rank, user) for rank, h in enumerate(ann_hits, start=1)])

    async def _strict(self, question: str, user: KeycloakUser, k: int, library_tags_ids: List[str]) -> List[VectorSearchHit]:
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
        search_filter = SearchFilter(tag_ids=sorted(library_tags_ids) if library_tags_ids else [], metadata_terms=metadata_terms)

        try:
            hits: List[FullTextHit] = self.vector_store.full_text_search(query=question, top_k=k, search_filter=search_filter)
        except Exception as e:
            logger.error("[VECTOR][SEARCH][FULLTEXT] Unexpected error during search: %s", str(e))
            raise

        return await asyncio.gather(*[self._to_hit(hit.document, hit.score, rank, user) for rank, hit in enumerate(hits, start=1)])

    async def _hybrid(self, question: str, user: KeycloakUser, k: int, library_tags_ids: List[str]) -> List[VectorSearchHit]:
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
        self, *, question: str, user: KeycloakUser, top_k: int = 10, document_library_tags_ids: Optional[List[str]] = None, policy_name: Optional[SearchPolicyName] = None
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
            if not document_library_tags_ids or document_library_tags_ids == []:
                document_library_tags_ids = await self._all_document_library_tags_ids(user)

            policy_key = policy_name or SearchPolicyName.hybrid
            if policy_key == SearchPolicyName.strict:
                logger.info("[VECTOR][SEARCH] Using strict search policy")
                return await self._strict(question=question, user=user, k=top_k, library_tags_ids=document_library_tags_ids)

            elif policy_key == SearchPolicyName.hybrid:
                logger.info("[VECTOR][SEARCH] Using hybrid search policy")
                return await self._hybrid(question=question, user=user, k=top_k, library_tags_ids=document_library_tags_ids)
            else:
                logger.info("[VECTOR][SEARCH] Using semantic search policy (legacy)")
                return await self._semantic(question=question, user=user, k=top_k, library_tags_ids=document_library_tags_ids)

        except TypeError as e:
            logger.error("[VECTOR][SEARCH]: %s", str(e))
            raise

        except Exception as e:
            logger.error("[VECTOR][SEARCH] Unexpected error during search: %s", str(e))
            raise
