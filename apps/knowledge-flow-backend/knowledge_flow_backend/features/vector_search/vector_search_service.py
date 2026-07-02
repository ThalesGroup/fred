# app/features/vector_search/service.py
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0 (the "License"); ...

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional, Protocol, Set, cast, runtime_checkable

from fred_core import KeycloakUser
from fred_core.common import OwnerFilter
from fred_core.kpi import BaseKPIWriter, KPIActor
from fred_core.store import VectorSearchHit
from langchain_core.documents import Document

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.core.stores.vector.base_vector_store import AnnHit, FullTextHit, HybridHit, SearchFilter
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.tag.tag_service import TagService
from knowledge_flow_backend.features.vector_search.vector_search_structures import SearchPolicyName

logger = logging.getLogger(__name__)


def _log_visual_search_hits(stage: str, hits: list) -> None:
    visual_hits = [h for h in hits if getattr(h, "has_visual_evidence", False) and getattr(h, "slide_image_uri", None)]
    logger.debug(
        "[RICH][KFB][%s] total_hits=%d visual_hits=%d slide_ids=%s image_uris=%s",
        stage,
        len(hits),
        len(visual_hits),
        [getattr(h, "slide_id", None) for h in visual_hits[:5]],
        [getattr(h, "slide_image_uri", None) for h in visual_hits[:5]],
    )


@runtime_checkable
class SupportsFullTextSearch(Protocol):
    def full_text_search(
        self,
        query: str,
        top_k: int,
        search_filter: Optional[SearchFilter] = None,
    ) -> List[FullTextHit]: ...


@runtime_checkable
class SupportsHybridSearch(Protocol):
    def hybrid_search(
        self,
        query: str,
        top_k: int,
        search_filter: Optional[SearchFilter] = None,
    ) -> List[HybridHit]: ...


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
    attachment_ranked = sorted(attachment_hits, key=lambda h: h.score or 0.0, reverse=True)
    attachment_primary = attachment_ranked[:attachment_quota]
    attachment_rest = attachment_ranked[attachment_quota:]

    remaining_ranked = sorted(
        [*attachment_rest, *corpus_hits],
        key=lambda h: h.score or 0.0,
        reverse=True,
    )
    return (attachment_primary + remaining_ranked)[:top_k]


def _merge_corpus_scope_hits(*hit_groups: List[VectorSearchHit], top_k: int) -> List[VectorSearchHit]:
    """
    Merge corpus hit groups using union semantics with stable de-duplication.

    Why:
    - chat scoping can now mix whole libraries and explicitly selected documents
    - those two selectors must widen the allowed corpus set, not intersect it

    How:
    - pass each independently searched corpus hit list
    - duplicate chunks are collapsed by a document/chunk-ish key
    - the highest-scoring copy wins
    """
    if top_k <= 0:
        return []

    merged_by_key: dict[tuple[object, ...], VectorSearchHit] = {}
    for hit in [candidate for group in hit_groups for candidate in group]:
        key = (
            hit.uid,
            hit.page,
            hit.section,
            hit.viewer_fragment,
            hit.content,
        )
        current = merged_by_key.get(key)
        if current is None or (hit.score or 0.0) > (current.score or 0.0):
            merged_by_key[key] = hit

    return sorted(merged_by_key.values(), key=lambda h: h.score or 0.0, reverse=True)[:top_k]


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
        self.metadata_service = MetadataService()
        self.crossencoder_model = ctx.get_crossencoder_model()
        self.kpi: BaseKPIWriter = ctx.get_kpi_writer()

    def _kpi_search_dims(self, *, policy: str) -> dict[str, Optional[str]]:
        index_name = getattr(self.vector_store, "index_name", None) or getattr(self.vector_store, "index", None)
        return {
            "policy": policy,
            "backend": type(self.vector_store).__name__,
            "index": str(index_name) if index_name else None,
        }

    def _kpi_actor(self, *, user: Optional[KeycloakUser] = None) -> KPIActor:
        groups = user.groups if user else None
        return KPIActor(type="system", groups=groups)

    def _phase_timer(
        self,
        *,
        phase: str,
        user: Optional[KeycloakUser],
        extra_dims: Optional[dict[str, Optional[str]]] = None,
    ):
        dims: dict[str, Optional[str]] = {"phase": phase}
        if extra_dims:
            dims.update(extra_dims)
        return self.kpi.timer(
            "app.phase_latency_ms",
            dims=dims,
            actor=self._kpi_actor(user=user),
        )

    def _record_search_stats(
        self,
        *,
        base_dims: dict[str, Optional[str]],
        hits_count: int,
        top_k: int,
        user: Optional[KeycloakUser],
    ) -> None:
        ok_dims = {**base_dims, "status": "ok"}
        self.kpi.count(
            "rag.search_hits_total",
            hits_count,
            dims=ok_dims,
            actor=self._kpi_actor(user=user),
        )
        self.kpi.count(
            "rag.search_top_k_total",
            top_k,
            dims=ok_dims,
            actor=self._kpi_actor(user=user),
        )
        if top_k > 0:
            ratio = float(hits_count) / float(top_k)
            self.kpi.gauge(
                "rag.search_hit_ratio",
                ratio,
                dims=ok_dims,
                actor=self._kpi_actor(user=user),
            )
        if hits_count == 0:
            self.kpi.count(
                "rag.search_empty_total",
                1,
                dims=ok_dims,
                actor=self._kpi_actor(user=user),
            )

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
            slide_id=md.get("slide_id"),
            has_visual_evidence=md.get("has_visual_evidence"),
            slide_image_uri=md.get("slide_image_uri"),
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
        library_tags_ids: List[str] | None,
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

        sf = SearchFilter(tag_ids=sorted(library_tags_ids) if library_tags_ids else library_tags_ids, metadata_terms=metadata_terms)

        base_dims = self._kpi_search_dims(policy="semantic")
        with self.kpi.timer("rag.search_latency_ms", dims=base_dims, actor=self._kpi_actor(user=user)) as kpi_dims:
            try:
                ann_hits: List[AnnHit] = await asyncio.to_thread(
                    self.vector_store.ann_search,
                    question,
                    k=k,
                    search_filter=sf,
                )
            except Exception as e:
                kpi_dims["error_code"] = "ann_search_failed"
                kpi_dims["exception_type"] = type(e).__name__
                self.kpi.count(
                    "rag.search_error_total",
                    1,
                    dims={**base_dims, "status": "error"},
                    actor=self._kpi_actor(user=user),
                )
                logger.error("[VECTOR][SEARCH][ANN] Unexpected error during search: %s", str(e))
                raise
            kpi_dims["status"] = "ok"
            self.kpi.count(
                "rag.search_total",
                1,
                dims={**base_dims, "status": "ok"},
                actor=self._kpi_actor(user=user),
            )
        hits_count = len(ann_hits)
        self._record_search_stats(base_dims=base_dims, hits_count=hits_count, top_k=k, user=user)
        if not ann_hits:
            logger.debug(
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
            logger.debug(
                "[VECTOR][SEARCH][ANN] got %d hits (sample: %s)",
                len(ann_hits),
                sample,
            )

        results = await asyncio.gather(*[self._to_hit(h.document, h.score, rank, user) for rank, h in enumerate(ann_hits, start=1)])
        _log_visual_search_hits("SEMANTIC", results)
        return results

    async def _strict(
        self,
        question: str,
        user: KeycloakUser,
        k: int,
        library_tags_ids: List[str] | None,
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

        Notes:
            When the current vector store backend does not expose `full_text_search`, this
            method falls back to semantic ANN search. This keeps local dev backends
            (e.g. Chroma) usable even when the request policy defaults to `strict`.
        """
        if not isinstance(self.vector_store, SupportsFullTextSearch):
            logger.warning(
                "[VECTOR][SEARCH][STRICT] backend=%s lacks full_text_search; falling back to semantic search",
                type(self.vector_store).__name__,
            )
            return await self._semantic(
                question=question,
                user=user,
                k=k,
                library_tags_ids=library_tags_ids,
                metadata_terms_extra=metadata_terms_extra,
            )
        full_text_store = cast(SupportsFullTextSearch, self.vector_store)

        metadata_terms: dict[str, Any] = {"retrievable": [True]}
        if metadata_terms_extra:
            metadata_terms.update(metadata_terms_extra)
        search_filter = SearchFilter(tag_ids=sorted(library_tags_ids) if library_tags_ids else library_tags_ids, metadata_terms=metadata_terms)

        base_dims = self._kpi_search_dims(policy="strict")
        with self.kpi.timer("rag.search_latency_ms", dims=base_dims, actor=self._kpi_actor(user=user)) as kpi_dims:
            try:
                hits: List[FullTextHit] = await asyncio.to_thread(
                    full_text_store.full_text_search,
                    query=question,
                    top_k=k,
                    search_filter=search_filter,
                )
            except Exception as e:
                kpi_dims["error_code"] = "fulltext_search_failed"
                kpi_dims["exception_type"] = type(e).__name__
                self.kpi.count(
                    "rag.search_error_total",
                    1,
                    dims={**base_dims, "status": "error"},
                    actor=self._kpi_actor(user=user),
                )
                logger.error("[VECTOR][SEARCH][FULLTEXT] Unexpected error during search: %s", str(e))
                raise
            kpi_dims["status"] = "ok"
            self.kpi.count(
                "rag.search_total",
                1,
                dims={**base_dims, "status": "ok"},
                actor=self._kpi_actor(user=user),
            )

        hits_count = len(hits)
        self._record_search_stats(base_dims=base_dims, hits_count=hits_count, top_k=k, user=user)
        results = await asyncio.gather(*[self._to_hit(hit.document, hit.score, rank, user) for rank, hit in enumerate(hits, start=1)])
        _log_visual_search_hits("STRICT", results)
        return results

    async def _hybrid(
        self,
        question: str,
        user: KeycloakUser,
        k: int,
        library_tags_ids: List[str] | None,
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

        Notes:
            When the current vector store backend does not expose `hybrid_search`, this
            method falls back to semantic ANN search. This keeps local dev backends
            (e.g. Chroma) usable even when the request policy defaults to `hybrid`.
        """
        if not isinstance(self.vector_store, SupportsHybridSearch):
            logger.warning(
                "[VECTOR][SEARCH][HYBRID] backend=%s lacks hybrid_search; falling back to semantic search",
                type(self.vector_store).__name__,
            )
            return await self._semantic(
                question=question,
                user=user,
                k=k,
                library_tags_ids=library_tags_ids,
                metadata_terms_extra=metadata_terms_extra,
            )
        hybrid_store = cast(SupportsHybridSearch, self.vector_store)

        metadata_terms: dict[str, Any] = {"retrievable": [True]}
        if metadata_terms_extra:
            metadata_terms.update(metadata_terms_extra)
        search_filter = SearchFilter(tag_ids=sorted(library_tags_ids) if library_tags_ids else library_tags_ids, metadata_terms=metadata_terms)

        base_dims = self._kpi_search_dims(policy="hybrid")
        with self.kpi.timer("rag.search_latency_ms", dims=base_dims, actor=self._kpi_actor(user=user)) as kpi_dims:
            try:
                hits: List[HybridHit] = await asyncio.to_thread(
                    hybrid_store.hybrid_search,
                    query=question,
                    top_k=k,
                    search_filter=search_filter,
                )
            except Exception as e:
                kpi_dims["error_code"] = "hybrid_search_failed"
                kpi_dims["exception_type"] = type(e).__name__
                self.kpi.count(
                    "rag.search_error_total",
                    1,
                    dims={**base_dims, "status": "error"},
                    actor=self._kpi_actor(user=user),
                )
                logger.error("[VECTOR][SEARCH][HYBRID] Unexpected error during search: %s", str(e))
                raise
            kpi_dims["status"] = "ok"
            self.kpi.count(
                "rag.search_total",
                1,
                dims={**base_dims, "status": "ok"},
                actor=self._kpi_actor(user=user),
            )

        hits_count = len(hits)
        self._record_search_stats(base_dims=base_dims, hits_count=hits_count, top_k=k, user=user)
        results = await asyncio.gather(*[self._to_hit(hit.document, hit.score, rank, user) for rank, hit in enumerate(hits, start=1)])
        _log_visual_search_hits("HYBRID", results)
        return results

    # ---------- unified public API -------------------------------------------

    async def search(
        self,
        *,
        question: str,
        user: KeycloakUser,
        top_k: int = 10,
        document_library_tags_ids: List[str] | None,
        document_uids: Optional[List[str]] = None,
        policy_name: Optional[SearchPolicyName] = None,
        owner_filter: Optional[OwnerFilter] = None,
        team_id: Optional[str] = None,
        session_id: Optional[str] = None,
        include_session_scope: bool = True,
        include_corpus_scope: bool = True,
    ) -> List[VectorSearchHit]:
        """
        Args:
            question (str): The search query string.
            user (KeycloakUser): The user performing the search.
            top_k (int): The number of top results to return. Defaults to 10.
            document_library_tags_ids (Optional[List[str]]): List of tag IDs to filter the search by library.
            policy_name (Optional[SearchPolicyName]): The search policy to use (hybrid, strict, semantic). Defaults to hybrid.
            document_uids (Optional[List[str]]): Optional list of document UIDs to filter the search results by.
            owner_filter (Optional[OwnerFilter]): Filter by ownership: 'personal' for user-owned resources, 'team' for team-owned resources.
            team_id (Optional[str]): Team ID, required when owner_filter is 'team'.
            include_session_scope (bool): Whether to search session-scoped attachment vectors.
            include_corpus_scope (bool): Whether to search corpus/library vectors.
        Returns:
            List[VectorSearchHit]: A list of VectorSearchHit objects containing the search results.

        Raises:
            Exception: For any other unexpected errors during the search process.
        """
        corpus_hits: List[VectorSearchHit] = []
        attachment_hits: List[VectorSearchHit] = []

        try:
            if not include_session_scope and not include_corpus_scope:
                logger.info("[VECTOR][SEARCH] both session and corpus scopes disabled; returning empty result.")
                return []

            # Resolve the set of tag IDs the user is authorized to search in
            with self._phase_timer(
                phase="vector_search_authorize_tags",
                user=user,
            ):
                authorized_tag_ids = await self.tag_service.list_authorized_tags_ids(user, owner_filter, team_id)
            if document_library_tags_ids:
                # Explicit library scope: narrow to the requested tags.
                authorized_tag_ids = set(document_library_tags_ids) & authorized_tag_ids
            elif document_uids:
                # Document-only scope: the caller named specific documents and no
                # libraries. Do NOT widen back to all authorized libraries — the
                # library branch must not run, so the search returns ONLY the named
                # documents (the document branch). Without this, a document-scoped
                # search (e.g. the comparison agent) leaks the whole tagged corpus.
                authorized_tag_ids = set()

            # Validate document_uids against ReBAC permissions
            authorized_document_uids: set[str] = set()
            if document_uids:
                with self._phase_timer(
                    phase="vector_search_filter_document_uids",
                    user=user,
                ):
                    authorized_document_uids = await self.metadata_service.filter_readable_document_uids(user, document_uids)

            # Search function dispatch
            policy_key = policy_name or SearchPolicyName.hybrid
            logger.debug(
                "[SEARCH_POLICY] received=%r resolved=%r question_preview=%r",
                policy_name,
                policy_key,
                question[:80],
            )
            search_fn = {
                SearchPolicyName.strict: self._strict,
                SearchPolicyName.hybrid: self._hybrid,
                SearchPolicyName.semantic: self._semantic,
            }.get(policy_key, self._hybrid)

            logger.info(
                "[OBS][SEARCH] session=%s q=%r policy=%s libs=%d session_scope=%s top_k=%d",
                session_id,
                question[:100],
                policy_key.value,
                len(authorized_tag_ids),
                bool(include_session_scope and session_id),
                top_k,
            )

            # Attachment/session-scope query (uses user_id/session_id metadata, no tag filtering)
            if include_session_scope and session_id:
                attachment_metadata: dict[str, Any] = {
                    "user_id": [user.uid],
                    "session_id": [session_id],
                    "scope": ["session"],
                }
                if authorized_document_uids:
                    attachment_metadata["document_uid"] = list(authorized_document_uids)
                logger.debug(
                    "[VECTOR][SEARCH][ATTACH] session=%s user=%s policy=%s question=%r top_k=%d",
                    session_id,
                    user.uid,
                    policy_key,
                    question,
                    top_k,
                )
                with self._phase_timer(
                    phase="vector_search_scope_attachment",
                    user=user,
                ):
                    attachment_hits = await search_fn(
                        question=question,
                        user=user,
                        k=top_k,
                        library_tags_ids=None,
                        metadata_terms_extra=attachment_metadata,
                    )
                logger.debug(
                    "[VECTOR][SEARCH][ATTACH] count=%d hits=%s",
                    len(attachment_hits),
                    [(h.title, round(h.score, 4), h.uid) for h in attachment_hits],
                )

            # Corpus query now supports a union of:
            # - whole selected/authorized libraries
            # - specifically selected documents
            corpus_hits_from_libraries: List[VectorSearchHit] = []
            corpus_hits_from_documents: List[VectorSearchHit] = []
            if include_corpus_scope and not authorized_tag_ids and not authorized_document_uids:
                logger.warning(
                    "[OBS][SEARCH] session=%s — no authorized libs or documents, corpus search skipped",
                    session_id,
                )
            if include_corpus_scope and authorized_tag_ids:
                corpus_metadata: dict[str, Any] = {"scope": ["!session"]}
                logger.debug(
                    "[VECTOR][SEARCH][CORPUS_LIBS] policy=%s tags=%s owner=%s team=%s question=%r top_k=%d",
                    policy_key,
                    sorted(authorized_tag_ids),
                    owner_filter,
                    team_id,
                    question[:80],
                    top_k,
                )
                with self._phase_timer(
                    phase="vector_search_scope_corpus_libraries",
                    user=user,
                ):
                    corpus_hits_from_libraries = await search_fn(
                        question=question,
                        user=user,
                        k=top_k,
                        library_tags_ids=list(authorized_tag_ids),
                        metadata_terms_extra=corpus_metadata,
                    )
                logger.debug(
                    "[VECTOR][SEARCH][CORPUS_LIBS] count=%d hits=%s",
                    len(corpus_hits_from_libraries),
                    [(h.title, round(h.score, 4), h.uid) for h in corpus_hits_from_libraries],
                )
            if include_corpus_scope and authorized_document_uids:
                corpus_document_metadata: dict[str, Any] = {
                    "scope": ["!session"],
                    "document_uid": list(authorized_document_uids),
                }
                logger.debug(
                    "[VECTOR][SEARCH][CORPUS_DOCS] policy=%s docs=%s owner=%s team=%s question=%r top_k=%d",
                    policy_key,
                    sorted(authorized_document_uids),
                    owner_filter,
                    team_id,
                    question[:80],
                    top_k,
                )
                with self._phase_timer(
                    phase="vector_search_scope_corpus_documents",
                    user=user,
                ):
                    corpus_hits_from_documents = await search_fn(
                        question=question,
                        user=user,
                        k=top_k,
                        library_tags_ids=None,
                        metadata_terms_extra=corpus_document_metadata,
                    )
                logger.debug(
                    "[VECTOR][SEARCH][CORPUS_DOCS] count=%d hits=%s",
                    len(corpus_hits_from_documents),
                    [(h.title, round(h.score, 4), h.uid) for h in corpus_hits_from_documents],
                )

            corpus_hits = _merge_corpus_scope_hits(
                corpus_hits_from_libraries,
                corpus_hits_from_documents,
                top_k=top_k,
            )

            # Unambiguous resolved-scope line: states EXACTLY what was searched —
            # which corpus branches ran, the exact tag ids and document uids used,
            # the active scopes, and the candidate pool. One INFO line is enough to
            # confirm a search hit only the intended target(s).
            logger.info(
                "[OBS][SEARCH][SCOPE] session=%s branches=[%s%s%s] tag_ids=%s doc_uids=%s scopes=(session=%s,corpus=%s) policy=%s pool=%d counts=(libs=%d,docs=%d,attach=%d)",
                session_id,
                "session " if attachment_hits else "",
                "libraries " if corpus_hits_from_libraries else "",
                "documents" if corpus_hits_from_documents else "",
                sorted(authorized_tag_ids) if authorized_tag_ids else [],
                sorted(authorized_document_uids) if authorized_document_uids else [],
                include_session_scope,
                include_corpus_scope,
                policy_key,
                top_k,
                len(corpus_hits_from_libraries),
                len(corpus_hits_from_documents),
                len(attachment_hits),
            )

            with self._phase_timer(
                phase="vector_search_merge_results",
                user=user,
            ):
                merged = _merge_attachment_and_corpus_hits(
                    attachment_hits=attachment_hits,
                    corpus_hits=corpus_hits,
                    top_k=top_k,
                    attachment_quota=3,
                )
            logger.info(
                "[OBS][SEARCH] session=%s count=%d attach=%d corpus=%d top=%s",
                session_id,
                len(merged),
                len(attachment_hits),
                len(corpus_hits),
                [(h.title, round(h.score, 4), h.tag_names) for h in merged],
            )
            _log_visual_search_hits("MERGED", merged)
            return merged

        except TypeError as e:
            logger.error("[VECTOR][SEARCH]: %s", str(e))
            raise

        except Exception as e:
            logger.error("[VECTOR][SEARCH] Unexpected error during search: %s", str(e))
            raise

    async def similarity_search(
        self,
        *,
        anchor: str,
        user: KeycloakUser,
        document_uids: Optional[List[str]] = None,
        document_library_tags_ids: Optional[List[str]] = None,
        top_k: int = 10,
        rerank: bool = True,
        min_score: Optional[float] = None,
    ) -> List[VectorSearchHit]:
        """Targeted similarity / comparison search (KF-SIMILARITY-SEARCH RFC).

        Returns the passages most similar to ``anchor``, restricted to the named
        targets (documents and/or library folders), ranked best-first. This is a
        thin orchestration over the existing primitives: ``search`` does the
        targeted retrieval (with ReBAC filtering), ``rerank_documents`` reorders
        with the cross-encoder. Targeting is REQUIRED — it is a comparison
        primitive, not a corpus-wide question-answering search.

        Args:
            anchor: the text/passage to find similar content for.
            document_uids / document_library_tags_ids: the search targets.
            top_k: number of matches to return (best-first).
            rerank: re-rank best-first with the cross-encoder (default on).
            min_score: drop matches below this relevance score.
        """
        document_uids = document_uids or []
        document_library_tags_ids = document_library_tags_ids or []
        if not document_uids and not document_library_tags_ids:
            raise ValueError("similarity search requires at least one target: document_uids or document_library_tags_ids")

        # Retrieve a wider candidate pool when reranking so the cross-encoder has
        # something to reorder; otherwise just top_k.
        rerank_pool_factor, max_pool = 5, 100
        pool = min(top_k * rerank_pool_factor, max_pool) if rerank else top_k
        logger.info(
            "[OBS][SIMILARITY] anchor=%r targets=(documents=%s, libraries=%s) top_k=%d rerank=%s pool=%d min_score=%s",
            anchor[:80],
            document_uids or [],
            document_library_tags_ids or [],
            top_k,
            rerank,
            pool,
            min_score,
        )
        hits = await self.search(
            question=anchor,
            user=user,
            top_k=pool,
            document_library_tags_ids=document_library_tags_ids,
            document_uids=document_uids or None,
            include_session_scope=False,  # comparison is over the corpus targets, not chat attachments
            include_corpus_scope=True,
        )
        if rerank and hits:
            hits = self.rerank_documents(anchor, hits, top_r=top_k)
        if min_score is not None:
            hits = [hit for hit in hits if (hit.score or 0.0) >= min_score]
        logger.info(
            "[OBS][SIMILARITY] returned=%d hits from documents=%s",
            len(hits),
            sorted({hit.uid for hit in hits}),
        )
        return hits[:top_k]

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
        base_dims = self._kpi_search_dims(policy="rerank")
        model_name = getattr(self.crossencoder_model, "model_name", None) or getattr(self.crossencoder_model, "name", None)
        if model_name:
            base_dims["model"] = str(model_name)
        with self.kpi.timer("rag.rerank_latency_ms", dims=base_dims, actor=self._kpi_actor(user=None)) as kpi_dims:
            # Score and sort documents by relevance
            pairs = [(question, doc.content) for doc in documents]
            scores = self.crossencoder_model.predict(pairs)
            sorted_docs = sorted(zip(documents, scores), key=lambda x: x[1], reverse=True)

            # Keep top-R documents
            reranked_documents = [doc for doc, _ in sorted_docs[:top_r]]
            logger.info("[VECTOR][RERANK] Reranked %s documents, keeping top %s", len(documents), len(reranked_documents))
            kpi_dims["status"] = "ok"
            self.kpi.count(
                "rag.rerank_total",
                1,
                dims={**base_dims, "status": "ok"},
                actor=self._kpi_actor(user=None),
            )
            self.kpi.count(
                "rag.rerank_docs_total",
                len(documents),
                dims={**base_dims, "status": "ok"},
                actor=self._kpi_actor(user=None),
            )
            self.kpi.count(
                "rag.rerank_top_r_total",
                top_r,
                dims={**base_dims, "status": "ok"},
                actor=self._kpi_actor(user=None),
            )
            return reranked_documents
