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

"""Knowledge Flow document client for the v2 runtime.

Covers the document surface beyond vector search:

- raw-content fetch (#1903): a document's ORIGINAL uploaded bytes by uid — the
  PPT-filler image support embeds a picked image into the deck
- on-demand summarization and the recursive folder/document tree (#1906)

Search and rerank stay on their existing Swift clients; do not grow this one
beyond these surfaces without checking there first. Scope resolution (library
binding, session narrowing) is NOT done here — the v2 adapters own it; this
client is wire-format only.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence

from fred_core.common import OwnerFilter
from pydantic import BaseModel

from fred_runtime.common.kf_base_client import (
    KfBaseClient,
    KnowledgeFlowAgentContext,
)
from fred_runtime.runtime_context import get_runtime_context

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RawContentBlob:
    bytes: bytes
    content_type: str
    filename: str
    size: int


def _filename_from_content_disposition(header: Optional[str], fallback: str) -> str:
    """Extract a filename from a Content-Disposition header, else the fallback.

    Knowledge Flow's raw-content endpoint sends
    `attachment; filename="name.ext"` (with an optional RFC 5987 `filename*=`).
    We only need the simple `filename="..."` value; prefer it when present and
    non-empty, otherwise fall back to the caller-provided name (the document uid).
    """
    if not header:
        return fallback
    match = re.search(r'filename="([^"]+)"', header)
    if match and match.group(1).strip():
        return match.group(1)
    return fallback


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
    Authenticated client for Knowledge Flow's document surface: raw-content
    fetch (#1903), on-demand summarization and the recursive folder/document
    tree (#1906).

    Propagates the end-user identity like the other KF clients; constructed
    from an agent context (`agent=...`) or a bare token (`access_token=...`).
    Inherits session and retry logic from KfBaseClient.
    """

    def __init__(
        self,
        *,
        agent: Optional[KnowledgeFlowAgentContext] = None,
        access_token: Optional[str] = None,
        refresh_user_access_token: Optional[Callable[[], str]] = None,
    ):
        super().__init__(
            allowed_methods=frozenset({"GET", "POST"}),
            agent=agent,
            access_token=access_token,
            refresh_user_access_token=refresh_user_access_token,
        )
        self._summarize_read_timeout = float(
            get_runtime_context().config.timeouts.summarize_read
        )

    async def fetch_raw_content(
        self,
        *,
        document_uid: str,
    ) -> RawContentBlob:
        """Fetch a document's ORIGINAL uploaded bytes by uid.

        Wire format (matches controller):
          GET /raw_content/{document_uid}
          -> streaming file bytes with Content-Type and
             Content-Disposition: attachment; filename="..."
        """
        r = await self._request_with_token_refresh(
            method="GET",
            path=f"/raw_content/{document_uid}",
            phase_name="kf_raw_content_fetch",
        )
        r.raise_for_status()

        content = r.content
        content_type = r.headers.get("Content-Type", "application/octet-stream")
        filename = _filename_from_content_disposition(
            r.headers.get("Content-Disposition"), fallback=document_uid
        )

        return RawContentBlob(
            bytes=content,
            content_type=content_type,
            filename=filename,
            size=len(content),
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
