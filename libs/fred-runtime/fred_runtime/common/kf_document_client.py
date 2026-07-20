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

"""Minimal Knowledge Flow document client for the v2 runtime (#1903).

Ports only the raw-content fetch from Kea's `KfDocumentClient`: the PPT-filler
image support needs a document's ORIGINAL uploaded bytes by uid (to embed a
picked image into the deck). Search and rerank stay on their existing Swift
clients; do not grow this one beyond content fetch without checking there
first.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, Optional

from fred_runtime.common.kf_base_client import (
    KfBaseClient,
    KnowledgeFlowAgentContext,
)

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


class KfDocumentClient(KfBaseClient):
    """
    Authenticated client for Knowledge Flow's document-content surface.

    Propagates the end-user identity like the other KF clients; constructed
    from an agent context (`agent=...`) or a bare token (`access_token=...`).
    """

    def __init__(
        self,
        *,
        agent: Optional[KnowledgeFlowAgentContext] = None,
        access_token: Optional[str] = None,
        refresh_user_access_token: Optional[Callable[[], str]] = None,
    ):
        super().__init__(
            allowed_methods=frozenset({"GET"}),
            agent=agent,
            access_token=access_token,
            refresh_user_access_token=refresh_user_access_token,
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
