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
from typing import Any, Dict, List, Optional, Sequence

from fred_core import VectorSearchHit
from pydantic import TypeAdapter

from app.common.kf_base_client import KfBaseClient
from app.core.agents.agent_flow import AgentFlow

logger = logging.getLogger(__name__)

_HITS = TypeAdapter(List[VectorSearchHit])


class VectorSearchClient(KfBaseClient):
    """
    Minimal authenticated client for Knowledge Flow's vector search.

    This client is designed for end-user identity propagation and requires an
    access_token for all requests. Inherits session and retry logic from KfBaseClient.
    """

    def __init__(self, agent: AgentFlow):
        super().__init__(
            agent=agent,
            allowed_methods=frozenset({"POST"}),
        )

    def search(
        self,
        *,
        question: str,
        top_k: int = 10,
        document_library_tags_ids: Optional[Sequence[str]] = None,
        search_policy: Optional[str] = None,
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
            "search_policy": str?
          }
        """
        payload: Dict[str, Any] = {"question": question, "top_k": top_k}
        if document_library_tags_ids:
            payload["document_library_tags_ids"] = list(document_library_tags_ids)
        if search_policy:
            payload["search_policy"] = search_policy

        # Use the base class's request method, passing the required access_token.
        # This will handle token refresh if needed. The required refresh token
        # is obtained via the refresh_callback provided at initialization. And the actual
        # token used is part of the runtime configuration passed to the agent.
        r = self._request_with_token_refresh(
            method="POST",
            path="/vector/search",
            json=payload,
        )
        r.raise_for_status()

        raw = r.json()
        if not isinstance(raw, list):
            logger.warning("Unexpected vector search payload type: %s", type(raw))
            return []
        return _HITS.validate_python(raw)
