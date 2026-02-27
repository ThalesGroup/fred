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

from typing import TYPE_CHECKING

from agentic_backend.common.kf_base_client import KfBaseClient

if TYPE_CHECKING:
    from agentic_backend.core.agents.agent_flow import AgentFlow


class KfMarkdownMediaClient(KfBaseClient):
    """Client for fetching embedded media assets from processed markdown documents."""

    def __init__(self, agent: "AgentFlow"):
        super().__init__(agent=agent, allowed_methods=frozenset({"GET"}))

    async def fetch_media(self, document_uid: str, media_id: str) -> bytes:
        """Fetch an embedded media asset (e.g. image) from a processed document.

        Args:
            document_uid: The unique identifier of the document.
            media_id: The media asset filename/identifier within the document.

        Returns:
            Raw bytes of the media asset.
        """
        path = f"/markdown/{document_uid}/media/{media_id}"
        resp = await self._request_with_token_refresh(
            "GET", path, phase_name="kf_markdown_media_fetch"
        )
        return resp.content
