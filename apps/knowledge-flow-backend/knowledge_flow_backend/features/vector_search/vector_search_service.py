# app/features/vector_search/service.py
# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import asyncio
import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, List, Optional, Protocol, cast, runtime_checkable
from uuid import UUID

from fastapi import HTTPException
from fred_core import KeycloakUser
from fred_core.documents.access import Candidate, SearchScope, resolve_scope, verify_candidates
from fred_core.documents.transport import DocumentAccessContext
from fred_core.kpi import BaseKPIWriter, KPIActor
from fred_core.security.delegation import AssertedUser
from fred_core.store import VectorSearchHit
from langchain_core.documents import Document

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.core.stores.vector.base_vector_store import AnnHit, BaseVectorHit, FullTextHit, HybridHit, SearchFilter
from knowledge_flow_backend.core.stores.vector.opensearch_vector_store import OpenSearchVectorStoreAdapter
from knowledge_flow_backend.features.vector_search.vector_search_structures import SearchPolicyName

logger = logging.getLogger(__name__)


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


def _coerce_chunk_index(raw: Any) -> Optional[int]:
    """Stores return chunk_index as int, float or string depending on the backend."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    if isinstance(raw, str):
        try:
            return int(raw)
        except ValueError:
            return None
    return None


def _merge_rankings(rankings: Sequence[Sequence[BaseVectorHit]]) -> list[tuple[Document, float]]:
    """Reciprocal ranks, with source/rank encounter order breaking ties."""
    merged: dict[str, tuple[Document, float]] = {}
    for ranking in rankings:
        seen: set[str] = set()
        for rank, hit in enumerate(ranking, 1):
            uid = str(hit.document.metadata.get("chunk_uid") or "")
            if not uid or uid in seen:
                continue
            seen.add(uid)
            previous = merged.get(uid)
            merged[uid] = (previous[0] if previous else hit.document, (previous[1] if previous else 0.0) + 1.0 / (60 + rank))
    return sorted(merged.values(), key=lambda item: -item[1])


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
        self.vector_store = ctx.get_create_vector_store(self.embedder, read_only=True)
        self.kpi: BaseKPIWriter = ctx.get_kpi_writer()
        self._crossencoder_model: Optional[Any] = None

    async def _require_corpus_ready(self) -> None:
        if isinstance(self.vector_store, OpenSearchVectorStoreAdapter):
            try:
                await asyncio.to_thread(self.vector_store.ensure_ready)
            except Exception:
                logger.warning("[VECTOR] corpus is not ready", exc_info=True)
                raise HTTPException(status_code=503, detail="corpus_not_ready") from None

    @property
    def crossencoder_model(self) -> Any:
        # Loaded on first actual rerank, not at service construction: constructing this
        # service (e.g. FastAPI route registration, OpenAPI generation) must not require
        # a working HF model client — see cross-encoder CI 429s on generate-openapi.
        if self._crossencoder_model is None:
            self._crossencoder_model = ApplicationContext.get_instance().get_crossencoder_model()
        return self._crossencoder_model

    def _kpi_search_dims(self, *, policy: str) -> dict[str, Optional[str]]:
        index_name = getattr(self.vector_store, "index_name", None) or getattr(self.vector_store, "index", None)
        return {
            "policy": policy,
            "backend": type(self.vector_store).__name__,
            "index": str(index_name) if index_name else None,
        }

    def _kpi_actor(self, *, user: Optional[KeycloakUser | AssertedUser] = None) -> KPIActor:
        return KPIActor(type="system")

    def _phase_timer(
        self,
        *,
        phase: str,
        user: Optional[KeycloakUser | AssertedUser],
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
        user: Optional[KeycloakUser | AssertedUser],
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

    async def _to_hit(
        self,
        doc: Document,
        score: float,
        rank: int,
        user: KeycloakUser | AssertedUser,
    ) -> VectorSearchHit:
        """
        Convert a LangChain Document + score into a VectorSearchHit UI DTO.
        Rationale:
          - Keep this translation in one place so fields stay consistent across policies.
        """
        md = doc.metadata or {}

        # Pull both ids and names (UI displays names; filters might use ids)
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
            chunk_kind=md.get("chunk_kind"),
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
            tag_ids=[],
            tag_names=[],
            tag_full_paths=[],
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
            chunk_index=_coerce_chunk_index(md.get("chunk_index")),
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
        user: KeycloakUser | AssertedUser,
        k: int,
        library_tags_ids: List[str] | None,
        metadata_terms_extra: Optional[dict[str, Any]] = None,
        metadata_any: tuple[dict[str, list[str]], ...] = (),
    ) -> Sequence[BaseVectorHit]:
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
            Sequence[BaseVectorHit]: Raw candidates; search authorizes them before enrichment.
        """
        metadata_terms: dict[str, Any] = {"retrievable": [True]}
        if metadata_terms_extra:
            metadata_terms.update(metadata_terms_extra)

        sf = SearchFilter(tag_ids=sorted(library_tags_ids) if library_tags_ids else library_tags_ids, metadata_terms=metadata_terms, metadata_any=metadata_any)

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
        return ann_hits

    async def _strict(
        self,
        question: str,
        user: KeycloakUser | AssertedUser,
        k: int,
        library_tags_ids: List[str] | None,
        metadata_terms_extra: Optional[dict[str, Any]] = None,
        metadata_any: tuple[dict[str, list[str]], ...] = (),
    ) -> Sequence[BaseVectorHit]:
        """
        Perform a strict search using BM25 (Best Matching 25).
        This strategy is only available when using OpenSearch as the vector store.

        Args:
            question (str): The query string to search for.
            user (KeycloakUser): The user performing the search.
            k (int): The number of top results to return.
            library_tags_ids (List[str]): List of tag IDs to filter the search results by.

        Returns:
            Sequence[BaseVectorHit]: Raw candidates; search authorizes them before enrichment.

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
                metadata_any=metadata_any,
            )
        full_text_store = cast(SupportsFullTextSearch, self.vector_store)

        metadata_terms: dict[str, Any] = {"retrievable": [True]}
        if metadata_terms_extra:
            metadata_terms.update(metadata_terms_extra)
        search_filter = SearchFilter(tag_ids=sorted(library_tags_ids) if library_tags_ids else library_tags_ids, metadata_terms=metadata_terms, metadata_any=metadata_any)

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

        return hits

    async def _hybrid(
        self,
        question: str,
        user: KeycloakUser | AssertedUser,
        k: int,
        library_tags_ids: List[str] | None,
        metadata_terms_extra: Optional[dict[str, Any]] = None,
        metadata_any: tuple[dict[str, list[str]], ...] = (),
    ) -> Sequence[BaseVectorHit]:
        """
        Hybrid search strategy that combines vector similarity and keyword matching.
        This strategy is only available when using OpenSearch as the vector store.

        Args:
            question (str): The search query.
            user (KeycloakUser): The user performing the search.
            k (int): The number of top results to retrieve.
            library_tags_ids (List[str]): The list of tag IDs to scope the search.

        Returns:
            Sequence[BaseVectorHit]: Raw candidates; search authorizes them before enrichment.

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
                metadata_any=metadata_any,
            )
        hybrid_store = cast(SupportsHybridSearch, self.vector_store)

        metadata_terms: dict[str, Any] = {"retrievable": [True]}
        if metadata_terms_extra:
            metadata_terms.update(metadata_terms_extra)
        search_filter = SearchFilter(tag_ids=sorted(library_tags_ids) if library_tags_ids else library_tags_ids, metadata_terms=metadata_terms, metadata_any=metadata_any)

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

        return hits

    # ---------- unified public API -------------------------------------------

    async def search(
        self,
        *,
        question: str,
        user: AssertedUser,
        top_k: int,
        policy_name: Optional[SearchPolicyName],
        context: DocumentAccessContext,
        authorized_space_ids: tuple[UUID, ...],
    ) -> List[VectorSearchHit]:
        """Search one Weaver space and its ancestors; the caller checked the space read.

        The index only proposes candidates. A chunk is returned only if the Control
        Plane facts keep it: live document in scope, retrievable, published generation.
        """
        await self._require_corpus_ready()
        engine = ApplicationContext.get_instance().get_pg_async_engine()
        async with engine.connect() as conn:
            scope = await resolve_scope(conn, context, user_id=user.uid, authorized_space_ids=authorized_space_ids)
        if (not scope.space_ids or scope.document_scope.is_empty) and not scope.attachment_ids:
            return []
        policy_key = policy_name or SearchPolicyName.hybrid
        strategy = {
            SearchPolicyName.strict: self._strict,
            SearchPolicyName.hybrid: self._hybrid,
            SearchPolicyName.semantic: self._semantic,
        }.get(policy_key, self._hybrid)
        sources = []
        if scope.space_ids and not scope.document_scope.is_empty:
            sources.append(
                (
                    {"space_id": [str(value) for value in scope.space_ids], "session_id": [""]},
                    scope.selection_terms,
                )
            )
        if scope.attachment_ids:
            sources.append(
                (
                    {"space_id": [str(context.space_id)], "session_id": [str(scope.conversation_id)], "document_uid": [str(value) for value in scope.attachment_ids]},
                    (),
                )
            )
        # Store interfaces embed per call: two active sources may embed twice.
        rankings = await asyncio.gather(
            *(
                strategy(
                    question=question,
                    user=user,
                    k=top_k,
                    library_tags_ids=None,
                    metadata_terms_extra=terms,
                    metadata_any=selection,
                )
                for terms, selection in sources
            )
        )
        documents = [(hit.document, hit.score) for hit in rankings[0]] if len(rankings) == 1 else _merge_rankings(rankings)
        # Verify the whole bounded union before applying the global limit.
        hits = (await self._visible_hits(scope, documents, user))[:top_k]
        stats_policy = policy_key
        if (policy_key == SearchPolicyName.strict and not isinstance(self.vector_store, SupportsFullTextSearch)) or (
            policy_key == SearchPolicyName.hybrid and not isinstance(self.vector_store, SupportsHybridSearch)
        ):
            stats_policy = SearchPolicyName.semantic
        self._record_search_stats(base_dims=self._kpi_search_dims(policy=stats_policy.value), hits_count=len(hits), top_k=top_k, user=user)
        return hits

    async def _visible_hits(
        self,
        scope: SearchScope,
        documents: Sequence[tuple[Document, float]],
        user: AssertedUser,
    ) -> List[VectorSearchHit]:
        """Keep, in order, the chunks the Control Plane facts still publish in `scope`."""
        pairs = [(Candidate(document_uid=str(md.get("document_uid") or ""), chunk_uid=str(md.get("chunk_uid") or "")), doc, score) for doc, score in documents if (md := doc.metadata or {})]
        engine = ApplicationContext.get_instance().get_pg_async_engine()
        async with engine.connect() as conn:
            visible = set(await verify_candidates(conn, scope, [candidate for candidate, _, _ in pairs]))
        kept = [(doc, score) for candidate, doc, score in pairs if candidate in visible]
        return [await self._to_hit(doc, score, rank, user) for rank, (doc, score) in enumerate(kept, 1)]

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

    async def get_document_chunks_ordered(
        self,
        *,
        user: AssertedUser,
        document_uid: str,
        context: DocumentAccessContext,
        authorized_space_ids: tuple[UUID, ...],
        limit: int,
    ) -> List[VectorSearchHit]:
        """Return a document's published chunks in chunk_index order, capped at `limit`.

        A direct store fetch, not a search: similarity ranking cannot guarantee that
        every row of a large table comes back. The caller checked the space read;
        staged or retired chunks are dropped before the limit applies.
        """
        await self._require_corpus_ready()
        try:
            raw_chunks = await asyncio.to_thread(self.vector_store.get_chunks_for_document, document_uid)
        except NotImplementedError:
            logger.warning("[VECTOR][DOC_CHUNKS] store %s cannot fetch chunks by document", type(self.vector_store).__name__)
            return []
        if not raw_chunks:
            return []

        def _order(chunk: dict) -> tuple[bool, int]:
            # None last: an unindexed chunk degrades to the end rather than ahead of chunk 0.
            index = _coerce_chunk_index((chunk.get("metadata") or {}).get("chunk_index"))
            return (index is None, index or 0)

        raw_chunks.sort(key=_order)
        engine = ApplicationContext.get_instance().get_pg_async_engine()
        async with engine.connect() as conn:
            scope = await resolve_scope(conn, context, user_id=user.uid, authorized_space_ids=authorized_space_ids)
        documents = [
            (Document(page_content=entry.get("text") or "", metadata=entry.get("metadata") or {}), 0.0)
            for entry in raw_chunks
            if str((entry.get("metadata") or {}).get("document_uid")) == document_uid
        ]
        hits = await self._visible_hits(scope, documents, user)
        logger.info(
            "[VECTOR][DOC_CHUNKS] document_uid=%s published=%d of %d truncated=%s",
            document_uid,
            len(hits),
            len(raw_chunks),
            len(hits) > limit,
        )
        return hits[:limit]
