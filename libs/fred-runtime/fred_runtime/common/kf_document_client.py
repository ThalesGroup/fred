# Copyright Thales 2026
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
from typing import Any, Dict, Optional, Sequence

from fred_core.common import OwnerFilter
from pydantic import BaseModel

from fred_runtime.common.kf_base_client import KfBaseClient, KnowledgeFlowAgentContext
from fred_runtime.runtime_context import get_runtime_context

logger = logging.getLogger(__name__)


class SummarizeDocumentResult(BaseModel):
    document_uid: str
    summary: str
    shrunk_for_budget: bool
    keywords: list[str] = []


class DocumentTreeResult(BaseModel):
    tree: str
    truncated: bool


class KfDocumentClient(KfBaseClient):
    """
    Authenticated client for Knowledge Flow's document access surface beyond
    vector search: on-demand summarization and the recursive folder/document
    tree.

    This client is designed for end-user identity propagation and requires an
    access_token for all requests. Inherits session and retry logic from
    KfBaseClient. Scope resolution (library binding, session narrowing) is NOT
    done here — the v2 adapters own it; this client is wire-format only.
    """

    def __init__(self, agent: KnowledgeFlowAgentContext):
        super().__init__(
            agent=agent,
            allowed_methods=frozenset({"POST"}),
        )
        self._summarize_read_timeout = float(
            get_runtime_context().config.timeouts.summarize_read
        )

    async def tree(
        self,
        *,
        working_directory: Optional[str] = None,
        tag_ids: Optional[Sequence[str]] = None,
        max_chars: int = 6000,
        owner_filter: Optional[OwnerFilter] = None,
        team_id: Optional[str] = None,
    ) -> DocumentTreeResult:
        """
        Wire format (matches controller):
          POST /documents/tree
          {
            "working_directory": str?,
            "tag_ids": [str]?,
            "max_chars": int,
            "owner_filter": str?,
            "team_id": str?
          }
        """
        payload: Dict[str, Any] = {"max_chars": max_chars}
        if working_directory:
            payload["working_directory"] = working_directory
        if tag_ids:
            payload["tag_ids"] = list(tag_ids)
        if owner_filter:
            payload["owner_filter"] = owner_filter.value
        if team_id:
            payload["team_id"] = team_id

        r = await self._request_with_token_refresh(
            method="POST",
            path="/documents/tree",
            phase_name="kf_document_tree",
            json=payload,
        )
        r.raise_for_status()
        return DocumentTreeResult.model_validate(r.json())

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
