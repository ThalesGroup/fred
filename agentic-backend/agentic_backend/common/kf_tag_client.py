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
from typing import Any, Callable, Dict, List, Optional

from fred_core.common import OwnerFilter

from agentic_backend.common.kf_base_client import (
    KfBaseClient,
    KnowledgeFlowAgentContext,
)

logger = logging.getLogger(__name__)

# The Knowledge Flow `TagType` enum serializes DOCUMENT as the literal string
# "document" (see knowledge_flow_backend.features.tag.structure.TagType). This is
# the value the `/tags?type=...` endpoint expects.
_DOCUMENT_TAG_TYPE = "document"


@dataclass(frozen=True)
class ResolvedTag:
    """A document tag reduced to what the folder→tag resolution needs."""

    tag_id: str
    full_path: str


def _normalize_folder(folder: str) -> str:
    """Normalize a folder/full-path string for case-sensitive comparison.

    Strips surrounding whitespace, normalizes backslashes to forward slashes,
    collapses repeated slashes, and drops empty leading/trailing segments. This
    mirrors how Knowledge Flow normalizes tag paths (see `_normalize_path` in the
    KF tag structures) so both sides compare equal.
    """
    cleaned = folder.strip().replace("\\", "/")
    parts = [seg.strip() for seg in cleaned.split("/") if seg.strip()]
    return "/".join(parts)


class KfTagClient(KfBaseClient):
    """
    Authenticated client for Knowledge Flow's tag surface.

    Used to resolve an author-provided folder string to the DOCUMENT tag id that
    scopes image lookups (PPT filler image support). Like the other KF clients it
    propagates the end-user identity; it can be constructed either from an agent
    context (`agent=...`) or from a bare access token (`access_token=...`), the
    latter for callers such as the analyze endpoint and the save processor which
    only hold a token. Inherits session and retry logic from KfBaseClient.
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

    async def list_document_tags(
        self,
        *,
        owner_filter: OwnerFilter,
        team_id: Optional[str] = None,
        path_prefix: Optional[str] = None,
    ) -> List[ResolvedTag]:
        """List DOCUMENT tags visible in the given space (personal or team).

        Wire format (matches controller):
          GET /tags?type=document&owner_filter=<personal|team>
                   [&team_id=<id>][&path_prefix=<prefix>]
        """
        params: Dict[str, Any] = {
            "type": _DOCUMENT_TAG_TYPE,
            "owner_filter": owner_filter.value,
        }
        if team_id:
            params["team_id"] = team_id
        if path_prefix:
            params["path_prefix"] = path_prefix

        r = await self._request_with_token_refresh(
            method="GET",
            path="/tags",
            phase_name="kf_list_tags",
            params=params,
        )
        r.raise_for_status()

        raw = r.json()
        if not isinstance(raw, list):
            logger.warning("Unexpected /tags payload type: %s", type(raw))
            return []

        out: List[ResolvedTag] = []
        for entry in raw:
            tag_id = entry.get("id")
            name = entry.get("name")
            if not tag_id or not name:
                continue
            path = entry.get("path")
            full_path = f"{path}/{name}" if path else name
            out.append(ResolvedTag(tag_id=tag_id, full_path=full_path))
        return out

    async def resolve_folder(
        self,
        folder: str,
        *,
        owner_filter: OwnerFilter,
        team_id: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve a folder string to its DOCUMENT tag id, else None.

        Compares the normalized folder against each tag's normalized full path.
        Comparison is case-sensitive (Knowledge Flow does not fold case on tag
        paths).
        """
        target = _normalize_folder(folder)
        if not target:
            return None
        tags = await self.list_document_tags(owner_filter=owner_filter, team_id=team_id)
        for tag in tags:
            if _normalize_folder(tag.full_path) == target:
                return tag.tag_id
        return None
