# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Weaver corpus reads using pod-owned clients and short SQL checkouts."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Mapping
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
from fred_sdk.contracts.runtime import DocumentSearchResult
from opensearchpy import AsyncOpenSearch
from sqlalchemy.ext.asyncio import AsyncEngine

from .opensearch_queries import build_search, mandatory_filters, read_response
from .table_hits import TABLE_EXPANSION_MAX_CHUNKS, repair_table_hits


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
            raise RuntimeError("Incomplete OpenSearch corpus response")
        return response

    async def _verified(
        self,
        scope: SearchScope,
        pairs: list[tuple[Candidate, VectorSearchHit]],
        check_active: Callable[[], None],
    ) -> list[VectorSearchHit]:
        check_active()
        async with self._engine.connect() as conn:
            visible = set(await verify_candidates(conn, scope, [c for c, _ in pairs]))
        check_active()
        return [hit for candidate, hit in pairs if candidate in visible]

    async def search(
        self,
        query: str,
        *,
        space_id: UUID,
        top_k: int,
        policy: str | None,
        check_active: Callable[[], None],
    ) -> DocumentSearchResult:
        if policy not in (None, "semantic", "strict", "hybrid"):
            raise ValueError("Unsupported corpus search policy")
        check_active()
        async with self._engine.connect() as conn:
            scope = await resolve_scope(conn, space_id)
        check_active()
        vector = None
        if policy != "strict":
            async with asyncio.timeout(self._timeout):
                vector = await self._embeddings.aembed_query(query)
            check_active()
        body, params = build_search(
            cast(SearchPolicyName | None, policy),
            question=query,
            vector=vector,
            top_k=top_k,
            space_ids=scope.space_ids,
        )
        response = await self._read(body, params, check_active)
        hits = await self._verified(scope, read_response(response), check_active)
        document_ids = {hit.uid for hit in hits}

        async def chunks(*, document_uid: str, limit: int) -> list[VectorSearchHit]:
            if document_uid not in document_ids:
                raise ValueError("Table expansion must originate from verified hits")
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
                return []
            pairs = [
                pair
                for pair in read_response(response)
                if pair[0].document_uid == document_uid
            ]
            return await self._verified(scope, pairs, check_active)

        hits = await repair_table_hits(hits, chunks, propagate_errors=True)
        check_active()
        return DocumentSearchResult(hits=tuple(hits))
