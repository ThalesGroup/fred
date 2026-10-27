# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Weaver corpus reads using pod-owned clients and short SQL checkouts."""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Callable, Mapping
from time import perf_counter
from typing import Any, cast
from uuid import UUID

from fred_core.common import (
    ModelConfiguration,
    OpenSearchIndexConfig,
    OpenSearchStoreConfig,
)
from fred_core.documents.access import (
    Candidate,
    SearchScope,
    resolve_scope,
    verify_candidates,
)
from fred_core.model.factory import get_embeddings
from fred_core.store.vector_search import VectorSearchHit
from fred_sdk.contracts.models import SearchPolicyName
from fred_sdk.contracts.runtime import DocumentSearchResult, unwrap_run_stop_error
from opensearchpy import AsyncOpenSearch
from sqlalchemy.ext.asyncio import AsyncEngine

from .opensearch_queries import build_search, mandatory_filters, read_response
from .table_hits import TABLE_EXPANSION_MAX_CHUNKS, repair_table_hits

logger = logging.getLogger(__name__)


class CorpusSearch:
    """One client set per pod; callers supply an already-authorized space."""

    def __init__(
        self,
        *,
        engine: AsyncEngine,
        opensearch: OpenSearchStoreConfig,
        index: OpenSearchIndexConfig,
        embedding: ModelConfiguration,
        timeout: float,
    ) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Corpus search requires a finite positive timeout")
        if not index.index.strip() or any(c in index.index for c in "*,? "):
            raise ValueError("Corpus search requires one concrete vector index")
        self._engine = engine
        self._index = index.index
        self._timeout = timeout
        self._embedding_name = embedding.name
        self._embedding_provider = embedding.provider
        # The same factory/settings as ingestion, independent of the turn's chat model.
        self._embeddings = get_embeddings(embedding)
        self._client = AsyncOpenSearch(
            hosts=[opensearch.host],
            http_auth=(opensearch.username, opensearch.password),
            use_ssl=opensearch.secure,
            verify_certs=opensearch.verify_certs,
            timeout=timeout,
            max_retries=0,
            retry_on_timeout=False,
        )

    async def close(self) -> None:
        await self._client.close()

    async def _read(
        self,
        body: dict[str, Any],
        params: dict[str, str],
        check_active: Callable[[], None],
    ) -> Mapping[str, Any]:
        check_active()
        started = perf_counter()
        logger.info(
            "[VECTOR][OPENSEARCH] started",
            extra={
                "event_name": "vector_opensearch_started",
                "vector_index": self._index,
                "requested_hits": body.get("size"),
                "search_pipeline": params.get("search_pipeline"),
                "timeout_s": self._timeout,
            },
        )
        async with asyncio.timeout(self._timeout):
            response = await self._client.search(
                index=self._index,
                body=body,
                params={**params, "allow_partial_search_results": "false"},
            )
        check_active()
        if (
            not isinstance(response, Mapping)
            or response.get("timed_out")
            or response.get("_shards", {}).get("failed", 0)
            or not isinstance(response.get("hits"), Mapping)
            or not isinstance(response["hits"].get("hits"), list)
        ):
            logger.error(
                "[VECTOR][OPENSEARCH] incomplete response",
                extra={
                    "event_name": "vector_opensearch_incomplete",
                    "vector_index": self._index,
                    "reason": "incomplete_response",
                },
            )
            raise RuntimeError("Incomplete OpenSearch corpus response")
        logger.info(
            "[VECTOR][OPENSEARCH] completed",
            extra={
                "event_name": "vector_opensearch_completed",
                "vector_index": self._index,
                "raw_hits": len(response["hits"]["hits"]),
                "opensearch_took_ms": response.get("took"),
                "duration_ms": (perf_counter() - started) * 1000,
            },
        )
        return response

    async def _verified(
        self,
        scope: SearchScope,
        pairs: list[tuple[Candidate, VectorSearchHit]],
        check_active: Callable[[], None],
    ) -> list[VectorSearchHit]:
        check_active()
        started = perf_counter()
        logger.info(
            "[VECTOR][VERIFY] started",
            extra={
                "event_name": "vector_verification_started",
                "candidates": len(pairs),
            },
        )
        async with self._engine.connect() as conn:
            visible = set(await verify_candidates(conn, scope, [c for c, _ in pairs]))
        check_active()
        hits = [hit for candidate, hit in pairs if candidate in visible]
        logger.info(
            "[VECTOR][VERIFY] completed",
            extra={
                "event_name": "vector_verification_completed",
                "candidates": len(pairs),
                "kept_hits": len(hits),
                "rejected_hits": len(pairs) - len(hits),
                "duration_ms": (perf_counter() - started) * 1000,
            },
        )
        return hits

    async def search(
        self,
        query: str,
        *,
        space_id: UUID,
        top_k: int,
        policy: str | None,
        check_active: Callable[[], None],
    ) -> DocumentSearchResult:
        started = perf_counter()
        logger.info(
            "[VECTOR][SEARCH] started",
            extra={
                "event_name": "vector_search_started",
                "space_id": str(space_id),
                "vector_index": self._index,
                "search_policy": policy or "hybrid",
                "top_k": top_k,
                "query_chars": len(query),
            },
        )
        phase = "validate"
        try:
            if policy not in (None, "semantic", "strict", "hybrid"):
                raise ValueError("Unsupported corpus search policy")
            phase = "resolve_scope"
            check_active()
            async with self._engine.connect() as conn:
                scope = await resolve_scope(conn, space_id)
            check_active()
            logger.info(
                "[VECTOR][SCOPE] resolved",
                extra={
                    "event_name": "vector_scope_resolved",
                    "space_id": str(space_id),
                    "scope_space_ids": [str(value) for value in scope.space_ids],
                    "duration_ms": (perf_counter() - started) * 1000,
                    "retrievable_only": True,
                },
            )
            vector = None
            if policy != "strict":
                phase = "embedding"
                embedding_started = perf_counter()
                logger.info(
                    "[VECTOR][EMBED] started",
                    extra={
                        "event_name": "vector_embedding_started",
                        "embedding_model": self._embedding_name,
                        "embedding_provider": self._embedding_provider,
                    },
                )
                async with asyncio.timeout(self._timeout):
                    vector = await self._embeddings.aembed_query(query)
                check_active()
                logger.info(
                    "[VECTOR][EMBED] completed",
                    extra={
                        "event_name": "vector_embedding_completed",
                        "embedding_dimensions": len(vector),
                        "duration_ms": (perf_counter() - embedding_started) * 1000,
                    },
                )
            phase = "build_query"
            body, params = build_search(
                cast(SearchPolicyName | None, policy),
                question=query,
                vector=vector,
                top_k=top_k,
                space_ids=scope.space_ids,
            )
            phase = "opensearch"
            response = await self._read(body, params, check_active)
            phase = "parse"
            pairs = read_response(response)
            phase = "verify_candidates"
            hits = await self._verified(scope, pairs, check_active)
            document_ids = {hit.uid for hit in hits}

            async def chunks(*, document_uid: str, limit: int) -> list[VectorSearchHit]:
                if document_uid not in document_ids:
                    raise ValueError(
                        "Table expansion must originate from verified hits"
                    )
                limit = min(limit, TABLE_EXPANSION_MAX_CHUNKS)
                response = await self._read(
                    {
                        "size": limit,
                        "query": {
                            "bool": {
                                "filter": [
                                    *mandatory_filters(scope.space_ids),
                                    {"term": {"metadata.document_uid": document_uid}},
                                ]
                            }
                        },
                        "sort": [
                            {
                                "metadata.chunk_index": {
                                    "order": "asc",
                                    "unmapped_type": "long",
                                }
                            }
                        ],
                    },
                    {},
                    check_active,
                )
                # Evaluate the cap before filtering unpublished chunks: a truncated
                # read must never look like a complete document after SQL filtering.
                if len(response["hits"]["hits"]) >= limit:
                    logger.info(
                        "[VECTOR][TABLE] expansion skipped",
                        extra={
                            "event_name": "vector_table_expansion_skipped",
                            "chunk_limit": limit,
                            "reason": "chunk_cap",
                        },
                    )
                    return []
                pairs = [
                    pair
                    for pair in read_response(response)
                    if pair[0].document_uid == document_uid
                ]
                return await self._verified(scope, pairs, check_active)

            phase = "table_repair"
            verified_count = len(hits)
            hits = await repair_table_hits(hits, chunks, propagate_errors=True)
            check_active()
            logger.info(
                "[VECTOR][SEARCH] completed",
                extra={
                    "event_name": "vector_search_completed",
                    "space_id": str(space_id),
                    "raw_hits": len(response["hits"]["hits"]),
                    "verified_hits": verified_count,
                    "final_hits": len(hits),
                    "matched_documents": len({hit.uid for hit in hits}),
                    "top_score": max((hit.score for hit in hits), default=None),
                    "duration_ms": (perf_counter() - started) * 1000,
                    "outcome": "succeeded",
                    "empty_reason": (
                        "no_index_hits"
                        if not response["hits"]["hits"]
                        else "no_valid_candidates"
                        if not pairs
                        else "no_visible_candidates"
                        if not verified_count
                        else "table_repair_empty"
                    )
                    if not hits
                    else None,
                },
            )
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "[VECTOR][SEARCH] verified result sample",
                    extra={
                        "event_name": "vector_search_sample",
                        "hit_sample": [
                            {
                                "document_uid": hit.uid,
                                "score": hit.score,
                                "rank": hit.rank,
                            }
                            for hit in hits[:5]
                        ],
                        "sample_truncated": len(hits) > 5,
                    },
                )
            return DocumentSearchResult(hits=tuple(hits))
        except asyncio.CancelledError:
            logger.info(
                "[VECTOR][SEARCH] cancelled",
                extra={
                    "event_name": "vector_search_completed",
                    "outcome": "cancelled",
                    "phase": phase,
                    "duration_ms": (perf_counter() - started) * 1000,
                },
            )
            raise
        except Exception as exc:
            stopped = unwrap_run_stop_error(exc)
            logger.log(
                logging.INFO if stopped is not None else logging.ERROR,
                "[VECTOR][SEARCH] stopped"
                if stopped is not None
                else "[VECTOR][SEARCH] failed",
                extra={
                    "event_name": "vector_search_completed",
                    "outcome": "stopped" if stopped is not None else "failed",
                    "phase": phase,
                    "error_type": type(exc).__name__,
                    "timed_out": isinstance(exc, TimeoutError),
                    "duration_ms": (perf_counter() - started) * 1000,
                },
            )
            raise
