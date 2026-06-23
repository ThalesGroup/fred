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

import logging
from dataclasses import dataclass
from typing import Any, Collection, Dict, List, Optional, Sequence

from fred_core.common import OwnerFilter
from fred_core.store import VectorSearchHit
from pydantic import BaseModel, TypeAdapter

from agentic_backend.common.kf_base_client import (
    KfBaseClient,
    KnowledgeFlowAgentContext,
)
from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.integrations.kf_vector_search.kf_vector_search_params import (
    KF_VECTOR_SEARCH_PROVIDER,
    KfVectorSearchParams,
)

logger = logging.getLogger(__name__)

_HITS = TypeAdapter(List[VectorSearchHit])


@dataclass(frozen=True)
class PreviewArtifactBlob:
    bytes: bytes
    content_type: str
    filename: str
    size: int


class SummarizeDocumentResult(BaseModel):
    document_uid: str
    summary: str
    shrunk_for_budget: bool
    keywords: List[str] = []


class DocumentTreeResult(BaseModel):
    tree: str
    truncated: bool


class KfDocumentClient(KfBaseClient):
    """
    Authenticated client for Knowledge Flow's document access surface: vector
    search, on-demand summarization, and the recursive folder/document tree.

    This client is designed for end-user identity propagation and requires an
    access_token for all requests. Inherits session and retry logic from KfBaseClient.
    """

    def __init__(self, agent: KnowledgeFlowAgentContext):
        super().__init__(
            agent=agent,
            allowed_methods=frozenset({"GET", "POST"}),
        )

    # ------------------------------------------------------------------
    # Vector search
    # ------------------------------------------------------------------

    async def agent_search(
        self,
        *,
        agent_settings: AgentSettings,
        runtime_context: RuntimeContext,
        question: str,
        top_k: int,
        document_library_tags_ids: Optional[Collection[str]] = None,
        document_uids: Optional[Collection[str]] = None,
    ) -> List[VectorSearchHit]:
        """Simplified search method for use within agent tools, which infers auth
        and other parameters from the agent settings and runtime context.

        Library scope rules (in priority order):
          1. Hard binding  — if document_library_tags_ids is set on the agent at creation
                             time, it wins unconditionally; user and LLM selections are ignored.
          2. Runtime scope — otherwise, intersect user selection with the LLM's own scope.
        """
        kf_params = _get_kf_vector_search_params(agent_settings)
        final_document_library_tags_ids = resolve_library_scope(
            kf_params, runtime_context, document_library_tags_ids
        )
        final_document_uids = _intersect_or_fallback(
            document_uids, runtime_context.selected_document_uids
        )

        effective_search_policy = (
            runtime_context.search_policy or kf_params.search_policy
        )
        effective_top_k = kf_params.top_k if kf_params.top_k is not None else top_k
        logger.info(
            "[OBS][SEARCH] session=%s q=%r policy=%s libs=%s top_k=%d",
            runtime_context.session_id,
            question[:100],
            effective_search_policy,
            final_document_library_tags_ids,
            effective_top_k,
        )
        logger.info(
            "[OBS][SEARCH][DETAIL] agent=%s policy=runtime:%r|params:%r|effective:%r doc_uids=%s top_k_agent=%s",
            agent_settings.id,
            runtime_context.search_policy,
            kf_params.search_policy,
            effective_search_policy,
            final_document_uids,
            kf_params.top_k,
        )
        hits = await self.search(
            question=question,
            top_k=effective_top_k,
            document_library_tags_ids=final_document_library_tags_ids,
            document_uids=final_document_uids,
            # Inferred from agent settings and runtime context:
            search_policy=effective_search_policy,
            owner_filter=OwnerFilter.TEAM
            if agent_settings.team_id
            else OwnerFilter.PERSONAL,
            team_id=agent_settings.team_id,
            session_id=runtime_context.session_id,
            include_session_scope=runtime_context.include_session_scope or True,
            include_corpus_scope=runtime_context.include_corpus_scope or True,
        )
        logger.info(
            "[OBS][SEARCH] session=%s count=%d top=%s",
            runtime_context.session_id,
            len(hits),
            [(h.title, round(h.score, 4), h.tag_names) for h in hits],
        )
        return hits

    async def search(
        self,
        *,
        question: str,
        top_k: int = 10,
        document_library_tags_ids: Optional[Collection[str]] = None,
        document_uids: Optional[Collection[str]] = None,
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
        if document_library_tags_ids is not None:
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
        logger.debug(
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

    async def fetch_preview_artifact(
        self,
        *,
        document_uid: str,
        artifact_path: str,
    ) -> PreviewArtifactBlob:
        r = await self._request_with_token_refresh(
            method="GET",
            path=f"/markdown/{document_uid}/artifact/{artifact_path}",
            phase_name="kf_preview_artifact_fetch",
        )
        r.raise_for_status()

        content = r.content
        content_type = r.headers.get("Content-Type", "application/octet-stream")
        filename = artifact_path.split("/")[-1] or "artifact.bin"

        return PreviewArtifactBlob(
            bytes=content,
            content_type=content_type,
            filename=filename,
            size=len(content),
        )

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

    # ------------------------------------------------------------------
    # On-demand summarization
    # ------------------------------------------------------------------

    async def agent_summarize(
        self,
        *,
        agent_settings: AgentSettings,
        document_uid: str,
        instruction: Optional[str] = None,
        max_chars: Optional[int] = None,
    ) -> SummarizeDocumentResult:
        """
        Summarize a document the agent already has the uid for.

        No scope resolution here: the agent already knows this uid (from a prior
        search hit or tree listing), and Knowledge Flow's own per-document RBAC is
        the real authorization gate — there's no "scope" to intersect against.

        The summary length is resolved against the configured `summarize_max_chars`
        knob (per-agent KfVectorSearchParams first, then the global
        ai.summarize_max_chars): it is the default when the caller (the LLM) does
        not request a length, and a hard cap on what the caller may request.
        """
        kf_params = _get_kf_vector_search_params(agent_settings)
        effective_max_chars = resolve_summarize_max_chars(
            kf_params, max_chars, self._summarize_max_chars_default
        )
        return await self.summarize(
            document_uid=document_uid,
            instruction=instruction,
            max_chars=effective_max_chars,
        )

    async def summarize(
        self,
        *,
        document_uid: str,
        instruction: Optional[str] = None,
        max_chars: int = 2000,
    ) -> SummarizeDocumentResult:
        """
        Wire format (matches controller):
          POST /documents/{document_uid}/summarize
          {
            "instruction": str?,
            "max_chars": int
          }
        """
        payload: Dict[str, Any] = {"max_chars": max_chars}
        if instruction:
            payload["instruction"] = instruction

        # Summarization runs map-reduce LLM passes over the whole document on the
        # Knowledge Flow side and routinely exceeds the default read timeout for
        # large PDFs. Override the read timeout for this request only.
        r = await self._request_with_token_refresh(
            method="POST",
            path=f"/documents/{document_uid}/summarize",
            phase_name="kf_document_summarize",
            json=payload,
            read_timeout=self._summarize_read_timeout,
        )
        r.raise_for_status()
        return SummarizeDocumentResult.model_validate(r.json())

    # ------------------------------------------------------------------
    # Folder/document tree
    # ------------------------------------------------------------------

    async def agent_tree(
        self,
        *,
        agent_settings: AgentSettings,
        runtime_context: RuntimeContext,
        working_directory: Optional[str] = None,
        max_chars: int = 6000,
    ) -> DocumentTreeResult:
        """
        Browse the agent's document scope as a folder/document tree.

        Only the library scope is resolved here (hard binding, else runtime user
        scope) — there is no per-call document_uids concept for browsing: an agent
        that already knows a uid has no reason to ask for it back via a listing.
        """
        kf_params = _get_kf_vector_search_params(agent_settings)
        tag_ids = resolve_library_scope(kf_params, runtime_context, None)
        return await self.tree(
            working_directory=working_directory,
            tag_ids=list(tag_ids) if tag_ids else None,
            max_chars=max_chars,
        )

    async def tree(
        self,
        *,
        working_directory: Optional[str] = None,
        tag_ids: Optional[Collection[str]] = None,
        max_chars: int = 6000,
    ) -> DocumentTreeResult:
        """
        Wire format (matches controller):
          POST /documents/tree
          {
            "working_directory": str?,
            "tag_ids": [str]?,
            "max_chars": int
          }
        """
        payload: Dict[str, Any] = {"max_chars": max_chars}
        if working_directory:
            payload["working_directory"] = working_directory
        if tag_ids:
            payload["tag_ids"] = list(tag_ids)

        r = await self._request_with_token_refresh(
            method="POST",
            path="/documents/tree",
            phase_name="kf_document_tree",
            json=payload,
        )
        r.raise_for_status()
        return DocumentTreeResult.model_validate(r.json())


# Built-in default summary length when neither the caller nor the agent config
# specifies one. Matches the prior summarize_document tool default.
DEFAULT_SUMMARIZE_MAX_CHARS = 5000


def resolve_summarize_max_chars(
    kf_params: KfVectorSearchParams,
    requested: Optional[int],
    global_default: Optional[int] = None,
) -> int:
    """Resolve the effective summary length from the configured cap and the caller's
    request.

    Precedence for the cap (default + hard upper bound):
    - per-agent KfVectorSearchParams.summarize_max_chars wins when set;
    - otherwise the global ai.summarize_max_chars (`global_default`);
    - otherwise the built-in default, with the caller's request honored verbatim.

    The cap is both the default (when the caller asks for nothing) and a hard upper
    bound on whatever the caller requests.
    """
    cap = (
        kf_params.summarize_max_chars
        if kf_params.summarize_max_chars is not None
        else global_default
    )
    default = cap if cap is not None else DEFAULT_SUMMARIZE_MAX_CHARS
    effective = requested if requested is not None else default
    if cap is not None:
        effective = min(effective, cap)
    return effective


def resolve_library_scope(
    kf_params: KfVectorSearchParams,
    runtime_context: RuntimeContext,
    llm_library_ids: Optional[Collection[str]],
) -> Optional[Collection[str]]:
    """
    Shared library-scope priority rule, used by every document-access tool
    (search, summarize, tree):
      1. Hard binding  — if document_library_tags_ids is set on the agent at
                         creation time, it wins unconditionally; user and LLM
                         selections are ignored.
      2. Runtime scope — otherwise, intersect user selection with the LLM's own
                         scope (whichever side is non-empty restricts; both
                         non-empty intersect; neither restricts).
    """
    if kf_params.document_library_tags_ids:
        return list(kf_params.document_library_tags_ids)
    return _intersect_or_fallback(
        runtime_context.selected_document_libraries_ids, llm_library_ids
    )


def _intersect_or_fallback(
    a: Optional[Collection[str]], b: Optional[Collection[str]]
) -> Optional[Collection[str]]:
    """Return the intersection when both sides carry an explicit non-empty list,
    otherwise whichever side is non-empty (or None if neither restricts).

    Semantics:
    - None and [] both mean "no restriction at this level" and are treated identically.
    - A non-empty list means "restrict to exactly these libraries".
    - When both sides are non-empty: return their intersection (may be empty → deny all).
    - When only one side is non-empty: return that side unchanged.
    - When neither side is non-empty: return None (no restriction).
    """
    effective_a = a if a else None
    effective_b = b if b else None
    if effective_a is None and effective_b is None:
        return None
    if effective_a is None:
        return effective_b
    if effective_b is None:
        return effective_a
    return set(effective_a) & set(effective_b)


def _get_kf_vector_search_params(agent_settings: AgentSettings) -> KfVectorSearchParams:
    """
    Extract KfVectorSearchParams from the agent's tuning refs.

    Scans mcp_servers refs for one whose params are KfVectorSearchParams
    (identified by provider == KF_VECTOR_SEARCH_PROVIDER). Returns default
    (no scope restriction) if not found, so callers never need a None check.
    """
    if agent_settings.tuning:
        for ref in agent_settings.tuning.mcp_servers:
            if (
                ref.params is not None
                and ref.params.provider == KF_VECTOR_SEARCH_PROVIDER
            ):
                return ref.params
    return KfVectorSearchParams()
