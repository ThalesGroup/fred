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

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Dict, List, Optional

import httpx
from fred_core.documents.transport import DOCUMENT_CONTEXT_HEADER, DocumentAccessContext
from fred_core.store.vector_search import VectorSearchHit
from pydantic import TypeAdapter

from fred_runtime.common.kf_base_client import KfBaseClient, KnowledgeFlowAgentContext

logger = logging.getLogger(__name__)

_HITS = TypeAdapter(List[VectorSearchHit])

#: Bounded retry for the similarity-search path only: nothing above it retries,
#: so one dropped connection failed a whole comparison run. Scoped here so
#: ordinary searches keep their behaviour.
_TRANSIENT_RETRIES = 2
_RETRY_BASE_DELAY_S = 0.5

#: Work may still be in flight, so re-issuing multiplies load on an already-slow
#: backend instead of recovering. A POOL timeout is deliberately absent: it means
#: no connection was acquired, so nothing was sent.
_NON_RETRYABLE_TIMEOUTS = (httpx.ReadTimeout, httpx.WriteTimeout)

#: Only "this instance could not serve you". Not a plain 500: KF wraps every
#: unexpected exception in one, so retrying a deterministic fault costs three
#: pool-and-rerank round trips before failing anyway.
_RETRYABLE_STATUS_CODES = frozenset({502, 503, 504})


async def _with_transient_retry(request):
    attempt = 0
    while True:
        try:
            return await request()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            retryable_status = (
                isinstance(exc, httpx.HTTPStatusError)
                and exc.response.status_code in _RETRYABLE_STATUS_CODES
            )
            retryable = retryable_status or (
                isinstance(exc, httpx.TransportError)
                and not isinstance(exc, _NON_RETRYABLE_TIMEOUTS)
            )
            if not retryable or attempt >= _TRANSIENT_RETRIES:
                raise
            delay = (
                _RETRY_BASE_DELAY_S * (2**attempt) + random.random() * 0.25  # nosec B311
            )
            logger.warning(
                "attempt=%d/%d after %r, retrying in %.2fs",
                attempt + 1,
                _TRANSIENT_RETRIES,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
            attempt += 1


class VectorSearchClient(KfBaseClient):
    """
    Minimal authenticated client for Knowledge Flow's vector search.

    This client is designed for end-user identity propagation and requires an
    access_token for all requests. Inherits session and retry logic from KfBaseClient.
    """

    def __init__(self, agent: KnowledgeFlowAgentContext):
        super().__init__(
            agent=agent,
            allowed_methods=frozenset({"GET", "POST"}),
        )

    async def search(
        self,
        *,
        question: str,
        document_context: DocumentAccessContext,
        top_k: int = 10,
        search_policy: Optional[str] = None,
        rerank: bool = False,
        min_score: float | None = None,
        read_timeout: float | None = None,
        transient_retry: bool = False,
    ) -> List[VectorSearchHit]:
        """Corpus search in the turn's Weaver space and its ancestors.

        Wire format (matches controller): POST /documents/search with
        {"question", "top_k", "search_policy"?, "rerank"?, "min_score"?} and the JSON document-context header.
        The scope is an intersection of unions, resolved against Weaver placement
        by Knowledge Flow; attachment IDs are an independent server-bound source.
        """
        # Similarity opts into its own timeout/retry policy; ordinary search does not.
        payload: Dict[str, Any] = {
            "question": question,
            "top_k": top_k,
        }
        if rerank:
            payload["rerank"] = rerank
        if min_score is not None:
            payload["min_score"] = min_score
        if search_policy:
            payload["search_policy"] = search_policy
        logger.info(
            "space_id=%s top_k=%d search_policy=%s",
            document_context.space_id,
            top_k,
            search_policy,
        )

        async def _do_request() -> httpx.Response:
            return await self._request_with_token_refresh(
                method="POST",
                path="/documents/search",
                phase_name="kf_vector_similarity_search"
                if transient_retry
                else "kf_vector_search",
                headers={DOCUMENT_CONTEXT_HEADER: document_context.model_dump_json()},
                json=payload,
                read_timeout=read_timeout,
            )

        r = (
            await _with_transient_retry(_do_request)
            if transient_retry
            else await _do_request()
        )
        r.raise_for_status()

        raw = r.json()
        if not isinstance(raw, list):
            logger.warning("Unexpected vector search payload type: %s", type(raw))
            return []
        return _HITS.validate_python(raw)

    async def get_document_chunks(
        self,
        *,
        document_uid: str,
        document_context: DocumentAccessContext,
        limit: int,
    ) -> List[VectorSearchHit]:
        """Fetch a document's chunks in chunk_index order, capped at `limit`.

        Bypasses similarity ranking, so a table that spans more chunks than the
        search top_k comes back whole.
        """
        r = await self._request_with_token_refresh(
            method="GET",
            path=f"/documents/{document_uid}/chunks",
            phase_name="kf_vector_document_chunks",
            headers={DOCUMENT_CONTEXT_HEADER: document_context.model_dump_json()},
            params={
                "limit": limit,
            },
        )
        r.raise_for_status()

        raw = r.json()
        if not isinstance(raw, list):
            logger.warning("Unexpected document-chunks payload type: %s", type(raw))
            return []
        return _HITS.validate_python(raw)
