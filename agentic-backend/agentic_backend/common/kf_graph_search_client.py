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

from agentic_backend.common.kf_base_client import KfBaseClient
from agentic_backend.core.agents.agent_flow import AgentFlow

logger = logging.getLogger(__name__)

_HITS = TypeAdapter(List[Any])


class GraphSearchClient(KfBaseClient):
    """
    Minimal authenticated client for Knowledge Flow's graph search.

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
        center_uid: Optional[Sequence[str]] = None,
    ) -> List[Any]:
        """
        Perform a graph search against the Knowledge Flow backend. This method
        requires an access_token for user-authenticated requests. It will trigger
        token refresh via the provided agent callback if the token is expired.
        Wire format (matches controller):
          POST /graph/search
          {
            "query": str,
            "center_uid": str,
            "top_k": int,
          }
        """
        payload: Dict[str, Any] = {"query": question, "top_k": top_k}
        if center_uid:
            payload["center_uid"] = center_uid

        # Use the base class's request method, passing the required access_token.
        # This will handle token refresh if needed. The required refresh token
        # is obtained via the refresh_callback provided at initialization. And the actual
        # token used is part of the runtime configuration passed to the agent.
        r = self._request_with_token_refresh(
            method="POST",
            path="/graph/search",
            json=payload,
        )
        r.raise_for_status()

        raw = r.json()
        if not isinstance(raw, list):
            logger.warning("Unexpected graph search payload type: %s", type(raw))
            return []
        return raw
