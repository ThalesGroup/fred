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
from typing import Any, Dict, List, Optional, Sequence

import httpx
from fred_core.common import OwnerFilter
from fred_core.store.vector_search import VectorSearchHit
from pydantic import TypeAdapter

from fred_runtime.common.kf_base_client import KfBaseClient, KnowledgeFlowAgentContext
from fred_runtime.runtime_context import get_runtime_context

logger = logging.getLogger(__name__)

_HITS = TypeAdapter(List[VectorSearchHit])

#: Bounded retry for the similarity-search path only: nothing above it retries,
#: so one dropped connection failed a whole comparison run. Scoped here so
#: `search`/`rerank` keep their behaviour (RUNTIME-EXECUTION-CONTRACT.md §8.60).
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
                "[VECTOR][RETRY] attempt=%d/%d after %r, retrying in %.2fs",
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
        top_k: int = 10,
        document_library_tags_ids: Optional[Sequence[str]] = None,
        document_uids: Optional[Sequence[str]] = None,
        search_policy: Optional[str] = None,
        owner_filter: Optional[OwnerFilter] = None,
        team_id: Optional[str] = None,
        session_id: Optional[str] = None,
        include_session_scope: bool = True,
        include_corpus_scope: bool = True,
    ) -> List[VectorSearchHit]:
        """
        Perform a vector search against the Knowledge Flow backend. This method
        requires an access_token for user-authenticated requests. It will trigger
        token refresh via the provided agent callback if the token is expired.
        Wire format (matches controller):
          POST /vector/search
          {
            "question": str,
            "top_k": int,
            "library_tags_ids": [str]?,
            "document_uids": [str]?,
            "search_policy": str?,
            "owner_filter": str?,
            "team_id": str?,
            "session_id": str?,
            "include_session_scope": bool,
            "include_corpus_scope": bool
          }
        """
        payload: Dict[str, Any] = {"question": question, "top_k": top_k}
        if document_library_tags_ids:
            payload["document_library_tags_ids"] = list(document_library_tags_ids)
        if document_uids:
            payload["document_uids"] = list(document_uids)
        if search_policy:
            payload["search_policy"] = search_policy
        if owner_filter:
            payload["owner_filter"] = owner_filter.value
        if team_id:
            payload["team_id"] = team_id
        if session_id:
            payload["session_id"] = session_id
            payload["include_session_scope"] = include_session_scope
        payload["include_corpus_scope"] = include_corpus_scope
        logger.info(
            "[VECTOR][CLIENT] team_id=%s session_id=%s include_session_scope=%s include_corpus_scope=%s top_k=%d search_policy=%s document_library_tags_ids=%s document_uids=%s",
            team_id,
            session_id,
            include_session_scope,
            include_corpus_scope,
            top_k,
            search_policy,
            payload.get("document_library_tags_ids"),
            payload.get("document_uids"),
        )

        # Use the base class's request method, passing the required access_token.
        # This will handle token refresh if needed. The required refresh token
        # is obtained via the refresh_callback provided at initialization. And the actual
        # token used is part of the runtime configuration passed to the agent.
        r = await self._request_with_token_refresh(
            method="POST",
            path="/vector/search",
            phase_name="kf_vector_search",
            json=payload,
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
        limit: int,
    ) -> List[VectorSearchHit]:
        """Fetch a document's chunks in chunk_index order, capped at `limit`.

        Bypasses similarity ranking, so a table that spans more chunks than the
        search top_k comes back whole.
        """
        r = await self._request_with_token_refresh(
            method="GET",
            path="/vector/document-chunks",
            phase_name="kf_vector_document_chunks",
            params={"document_uid": document_uid, "limit": limit},
        )
        r.raise_for_status()

        raw = r.json()
        if not isinstance(raw, list):
            logger.warning("Unexpected document-chunks payload type: %s", type(raw))
            return []
        return _HITS.validate_python(raw)

    async def similarity_search(
        self,
        *,
        anchor: str,
        document_uids: Sequence[str],
        top_k: int = 10,
        rerank: bool = True,
        min_score: Optional[float] = None,
    ) -> List[VectorSearchHit]:
        """
        Targeted document-to-document comparison search.

        Unlike `search`, targeting is required: this ranks the passages most
        similar to `anchor`, restricted to `document_uids`. Retries transient
        connection/5xx failures (bounded, jittered) - this path has no upstream
        retry otherwise.

        Wire format (matches controller):
          POST /vector/similarity-search
          {
            "anchor": str,
            "document_uids": [str],
            "top_k": int,
            "rerank": bool,
            "min_score": float?
          }
        """
        if not document_uids:
            raise ValueError("similarity_search requires at least one document uid")

        payload: Dict[str, Any] = {
            "anchor": anchor,
            "document_uids": list(document_uids),
            "top_k": top_k,
            "rerank": rerank,
        }
        if min_score is not None:
            payload["min_score"] = min_score

        read_timeout = float(get_runtime_context().config.timeouts.similarity_read)

        async def _do_request() -> httpx.Response:
            return await self._request_with_token_refresh(
                method="POST",
                path="/vector/similarity-search",
                phase_name="kf_vector_similarity_search",
                json=payload,
                read_timeout=read_timeout,
            )

        r = await _with_transient_retry(_do_request)
        r.raise_for_status()

        raw = r.json()
        if not isinstance(raw, list):
            logger.warning("Unexpected similarity search payload type: %s", type(raw))
            return []
        return _HITS.validate_python(raw)

    async def rerank(
        self,
        *,
        question: str,
        documents: Sequence[VectorSearchHit],
        top_r: int = 6,
    ) -> List[VectorSearchHit]:
        """
        Rerank an existing list of VectorSearchHit items using the cross-encoder.
        Wire format (matches controller):
          POST /vector/rerank
          {
            "question": str,
            "top_r": int,
            "documents": [VectorSearchHit]
          }
        """
        payload: Dict[str, Any] = {
            "question": question,
            "top_r": top_r,
            "documents": [
                d.model_dump() if hasattr(d, "model_dump") else d for d in documents
            ],
        }

        r = await self._request_with_token_refresh(
            method="POST",
            path="/vector/rerank",
            phase_name="kf_vector_rerank",
            json=payload,
        )
        r.raise_for_status()

        raw = r.json()
        if not isinstance(raw, list):
            logger.warning("Unexpected vector rerank payload type: %s", type(raw))
            return []
        return _HITS.validate_python(raw)
