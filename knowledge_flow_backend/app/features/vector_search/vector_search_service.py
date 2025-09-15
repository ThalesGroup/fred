# app/features/vector_search/service.py
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0 (the "License"); ...

import logging
from datetime import datetime, timezone
from typing import List, Optional, Set

from fred_core import Action, KeycloakUser, Resource, VectorSearchHit, authorize
from langchain.schema.document import Document

from app.application_context import ApplicationContext
from app.core.stores.vector.base_vector_store import AnnHit, LexicalSearchable, SearchFilter
from app.features.tag.service import TagService
from app.features.tag.structure import TagType
from app.features.vector_search.vector_search_hybrid_retriever import HybridRetriever
from app.features.vector_search.vector_search_strict_retriever import StrictRetriever
from app.features.vector_search.vector_search_structures import (
    POLICIES,
    HybridPolicy,
    SearchPolicy,
    SearchPolicyName,
)

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
        self.vector_store = ctx.get_create_vector_store(self.embedder)  # BaseVectorStore (+ LexicalSearchable in OS)
        self.tag_service = TagService()

        # Inject the same vector store (capability-checked inside retrievers)
        self._hybrid_retriever = HybridRetriever(self.vector_store)
        if isinstance(self.vector_store, LexicalSearchable):
            self._strict_retriever = StrictRetriever(self.vector_store)
        else:
            self._strict_retriever = None
        # default thresholds (can be overridden per call)
        self._default_policy = SearchPolicy()

    # ---------- helpers -------------------------------------------------------

    def _collect_document_ids_from_tags(self, tags_ids: Optional[List[str]], user: KeycloakUser) -> Set[str]:
        """
        Resolve UI tag_ids -> document_uids (library scoping).
        Returns an empty set when no tags provided to keep call sites simple.
        """
        if not tags_ids:
            return set()
        doc_ids: Set[str] = set()
        for tag_id in tags_ids:
            tag = self.tag_service.get_tag_for_user(tag_id, user)
            # Tag.item_ids is expected to be a list[str] of document_uids
            doc_ids.update(tag.item_ids or [])
        return doc_ids

    def _tags_meta_from_ids(self, tag_ids: List[str], user: KeycloakUser) -> tuple[list[str], list[str]]:
        """Resolve tag IDs to human-readable names for UI chips + full breadcrumb paths."""
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

    def _all_document_library_tags_ids(self, user: KeycloakUser) -> List[str]:
        """
        Return all library tags ids for the user.
        """
        tags = self.tag_service.list_all_tags_for_user(user=user, tag_type=TagType.DOCUMENT)
        return [t.id for t in tags]

    def _to_hit(self, doc: Document, score: float, rank: int, user: KeycloakUser) -> VectorSearchHit:
        """
        Convert a LangChain Document + score into a VectorSearchHit UI DTO.
        Rationale:
          - Keep this translation in one place so fields stay consistent across policies.
        """
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

    def _semantic(self, *, question: str, user: KeycloakUser, k: int, library_tags_ids: List[str]) -> List[VectorSearchHit]:
        """
        Semantic (legacy) — fast but no lexical guardrails.
        Keep available for debugging or recall-heavy exploratory queries.
        """
        sf = SearchFilter(tag_ids=sorted(library_tags_ids)) if library_tags_ids else None
        ann_hits: List[AnnHit] = self.vector_store.ann_search(question, k=k, search_filter=sf)
        return [self._to_hit(h.document, h.score, rank, user) for rank, h in enumerate(ann_hits, start=1)]

    def _strict(self, *, question: str, user: KeycloakUser, k: Optional[int], library_tags_ids: List[str], policy: SearchPolicy) -> List[VectorSearchHit]:
        """
        Strict = ANN ∩ BM25 ∩ (optional) exact phrase; returns [] when weak.
        """
        if self._strict_retriever is None:
            logger.warning("StrictRetriever is not available for the current vector store.")
            return []
        p = policy if (k is None or k <= 0) else type(policy)(**{**policy.__dict__, "k_final": k})
        docs = self._strict_retriever.search(query=question, scoped_document_ids=sorted(library_tags_ids), policy=p)
        return [self._to_hit(doc, score=1.0, rank=i, user=user) for i, doc in enumerate(docs, start=1)]

    def _hybrid(self, *, question: str, user: KeycloakUser, k: int, library_tags_ids: List[str], policy: HybridPolicy) -> List[VectorSearchHit]:
        """
        Hybrid (default) — RRF fusion of BM25 + ANN, MMR de-dup, calibrated gates.
        """
        pairs = self._hybrid_retriever.search(query=question, scoped_document_ids=sorted(library_tags_ids), policy=policy)
        # pairs: List[Tuple[Document, ann_cosine]]
        return [self._to_hit(doc, score=ann_cos, rank=i, user=user) for i, (doc, ann_cos) in enumerate(pairs[:k], start=1)]

    # ---------- unified public API -------------------------------------------

    @authorize(Action.READ, Resource.DOCUMENTS)
    def search(
        self,
        *,
        question: str,
        user: KeycloakUser,
        top_k: int = 10,
        document_library_tags_ids: Optional[List[str]] = None,
        policy_name: Optional[SearchPolicyName] = None,
    ) -> List[VectorSearchHit]:
        """
        Unified vector search (enum-driven).
        - hybrid  (default): ANN + BM25 (RRF fusion).
        - strict            : intersection; returns [] when below bar.
        - semantic          : pure ANN (legacy/debug).
        We hard-scope by library (tags -> document_uids) to avoid cross-library leakage.
        """
        if not document_library_tags_ids or document_library_tags_ids == []:
            document_library_tags_ids = self._all_document_library_tags_ids(user)
        policy_key = policy_name or SearchPolicyName.hybrid
        if policy_key == SearchPolicyName.strict:
            pol = POLICIES[SearchPolicyName.strict]
            # If your StrictRetriever.search expects StrictPolicy, this is fine:
            return self._strict(
                question=question,
                user=user,
                k=top_k,
                library_tags_ids=document_library_tags_ids,
                policy=pol,  # ✅ pass the policy object
            )

        if policy_key == SearchPolicyName.semantic:
            return self._semantic(
                question=question,
                user=user,
                k=top_k,
                library_tags_ids=document_library_tags_ids,
            )

        # default: hybrid
        pol = POLICIES[SearchPolicyName.hybrid]
        return self._hybrid(
            question=question,
            user=user,
            k=top_k,
            library_tags_ids=document_library_tags_ids,
            policy=pol,
        )
