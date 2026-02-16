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
from typing import Callable, Optional

from fred_core import LogQuery, LogQueryResult
from pydantic import TypeAdapter

from agentic_backend.common.kf_base_client import KfBaseClient
from agentic_backend.core.agents.agent_flow import AgentFlow

logger = logging.getLogger(__name__)

_LOG_QUERY_RESULT = TypeAdapter(LogQueryResult)


class KfLogsClient(KfBaseClient):
    """
    Minimal authenticated client for Knowledge Flow's /logs/query endpoint.

    Designed for end-user identity propagation. Uses the KfBaseClient retry
    + token refresh logic and keeps payload shape identical to LogQuery.
    """

    def __init__(
        self,
        agent: Optional[AgentFlow] = None,
        *,
        access_token: Optional[str] = None,
        refresh_user_access_token: Optional[Callable[[], str]] = None,
    ):
        super().__init__(
            allowed_methods=frozenset({"POST"}),
            agent=agent,
            access_token=access_token,
            refresh_user_access_token=refresh_user_access_token,
        )

    async def query(self, log_query: LogQuery) -> LogQueryResult:
        payload = (
            log_query.model_dump()
            if hasattr(log_query, "model_dump")
            else log_query.dict()
        )
        logger.info(
            "[KF][LOGS] query: since=%s until=%s limit=%s order=%s",
            log_query.since,
            log_query.until,
            log_query.limit,
            log_query.order,
        )
        r = await self._request_with_token_refresh(
            method="POST",
            path="/logs/query",
            phase_name="kf_logs_query",
            json=payload,
        )
        r.raise_for_status()
        return _LOG_QUERY_RESULT.validate_python(r.json())
