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
from typing import Any, Callable, Dict, Optional, Protocol

import httpx
from fred_core.kpi.kpi_writer_structures import KPIActor
from fred_sdk.contracts.context import RuntimeContext as AgentRuntimeContext

from fred_runtime.common.kf_http_client import get_shared_kf_async_client
from fred_runtime.common.structures import AgentSettingsLike
from fred_runtime.runtime_context import get_runtime_context

logger = logging.getLogger(__name__)


class KnowledgeFlowAgentContext(Protocol):
    runtime_context: AgentRuntimeContext
    agent_settings: AgentSettingsLike

    def refresh_user_access_token(self) -> str:
        raise NotImplementedError()


TokenRefreshCallback = Callable[[], str]


class KfBaseClient:
    """
    Base client for secure, retrying access to Knowledge Flow (and related Fred backends).
    """

    def __init__(
        self,
        allowed_methods: frozenset,
        *,
        agent: Optional[KnowledgeFlowAgentContext] = None,
        access_token: Optional[str] = None,
        refresh_user_access_token: Optional[Callable[[], str]] = None,
    ):
        """
        Why: centralize KF client setup so all callers share the same transport and KPI wiring.
        How: resolve config from the fred-runtime context, then build a shared httpx client.
        Example:
            >>> client = KfBaseClient(allowed_methods=frozenset({"GET"}), access_token="token")
        """
        runtime_ctx = get_runtime_context()
        self.base_url = runtime_ctx.get_knowledge_flow_base_url().rstrip("/")
        self._kpi = runtime_ctx.get_kpi_writer()

        timeout_cfg = runtime_ctx.config.timeouts.as_httpx_timeout_config()
        limits_cfg = runtime_ctx.get_http_client_limits()
        limits_dict = dict(limits_cfg) if limits_cfg is not None else None
        tuning, client = get_shared_kf_async_client(
            timeout_cfg=timeout_cfg, limits_cfg=limits_dict
        )
        self._tuning = tuning
        self.client = client

        self._agent = agent
        self._static_access_token = access_token
        self._refresh_cb = refresh_user_access_token

        if not self._agent and not self._static_access_token:
            raise ValueError("KfBaseClient requires either `agent` or `access_token`.")

    def _kpi_actor(self) -> KPIActor:
        return KPIActor(type="system")

    def _kpi_dims(self, *, method: str, path: str) -> Dict[str, Optional[str]]:
        dims: Dict[str, Optional[str]] = {
            "client": "knowledge_flow",
            "method": method,
            "path": path,
        }
        if self._agent:
            agent_settings = getattr(self._agent, "agent_settings", None)
            agent_label = None
            if agent_settings is not None:
                agent_label = getattr(agent_settings, "id", None)
            dims["agent_id"] = agent_label or type(self._agent).__name__
            runtime_context = getattr(self._agent, "runtime_context", None)
            session_id = getattr(runtime_context, "session_id", None)
            if session_id:
                dims["session_id"] = str(session_id)
            user_id = getattr(runtime_context, "user_id", None)
            if user_id:
                dims["user_id"] = str(user_id)
            team_id = getattr(runtime_context, "team_id", None)
            if team_id:
                dims["team_id"] = str(team_id)
            agent_instance_id = getattr(runtime_context, "agent_instance_id", None)
            if agent_instance_id:
                dims["agent_instance_id"] = str(agent_instance_id)
            template_agent_id = getattr(runtime_context, "template_agent_id", None)
            if template_agent_id:
                dims["template_agent_id"] = str(template_agent_id)
            checkpoint_id = getattr(runtime_context, "checkpoint_id", None)
            if checkpoint_id:
                dims["checkpoint_id"] = str(checkpoint_id)
            trace_id = getattr(runtime_context, "trace_id", None)
            if trace_id:
                dims["trace_id"] = str(trace_id)
            correlation_id = getattr(runtime_context, "correlation_id", None)
            if correlation_id:
                dims["correlation_id"] = str(correlation_id)
            execution_action = getattr(runtime_context, "execution_action", None)
            if execution_action:
                dims["execution_action"] = str(execution_action)
        return dims

    # ---------------------------
    # Internal helpers
    # ---------------------------

    def _current_access_token(self) -> str:
        """Uniform accessor for the access token regardless of mode.

        Why: avoid duplicating token access logic across client call sites.
        How: read the agent/runtime token first, then fall back to refresh hooks.
        Example:
            >>> token = self._current_access_token()
        """
        if self._agent:
            token = getattr(self._agent.runtime_context, "access_token", None)
            if token:
                return token
            # Centralized fallback: if token is missing, attempt a refresh once.
            if self._try_refresh_token():
                refreshed = getattr(self._agent.runtime_context, "access_token", None)
                if refreshed:
                    return refreshed
            raise ValueError(
                "Agent runtime_context has no access_token and refresh failed."
            )

        if not self._static_access_token and self._refresh_cb:
            if self._try_refresh_token() and self._static_access_token:
                return self._static_access_token
        if not self._static_access_token:
            raise ValueError(
                "No access_token provided for session-scoped client and refresh failed."
            )
        return self._static_access_token

    def _try_refresh_token(self) -> bool:
        """Try to refresh token in either mode."""
        if self._agent and getattr(self._agent, "refresh_user_access_token", None):
            try:
                self._agent.refresh_user_access_token()
                logger.info("Agent-led user token refresh succeeded.")
                return True
            except Exception as e:
                logger.error("Agent-led token refresh failed: %s", e)
                return False

        if self._refresh_cb:
            try:
                new_token = self._refresh_cb()
                if not new_token:
                    logger.error("Session refresh callback returned empty token.")
                    return False
                self._static_access_token = new_token
                logger.info("Session-led user token refresh succeeded.")
                return True
            except Exception as e:
                logger.error("Session-led token refresh failed: %s", e)
                return False

        return False

    # ---------------------------
    # Request execution
    # ---------------------------

    async def _execute_authenticated_request(
        self, method: str, path: str, **kwargs: Any
    ) -> httpx.Response:
        """
        Executes an HTTP request with Bearer authentication.
        If an explicit 'access_token' kwarg is provided, it overrides the default one.
        """
        url = f"{self.base_url}{path}"

        # Support explicit override of the token
        token = kwargs.pop("access_token", None) or self._current_access_token()

        headers: Dict[str, str] = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"

        # httpx>=0.28 path: build a Request then send it with explicit stream mode.
        stream = bool(kwargs.pop("stream", False))
        follow_redirects = kwargs.pop("follow_redirects", httpx.USE_CLIENT_DEFAULT)
        auth = kwargs.pop("auth", httpx.USE_CLIENT_DEFAULT)
        request = self.client.build_request(
            method,
            url,
            headers=headers,
            **kwargs,
        )
        return await self.client.send(
            request,
            stream=stream,
            auth=auth,
            follow_redirects=follow_redirects,
        )

    async def _request_with_token_refresh(
        self, method: str, path: str, *, phase_name: str, **kwargs: Any
    ) -> httpx.Response:
        """
        Executes a request, handling user-token expiration (401) via refresh and retry.
        """
        with self._kpi.timer(
            "app.phase_latency_ms",
            dims={**self._kpi_dims(method=method, path=path), "phase": phase_name},
            actor=self._kpi_actor(),
        ):
            r = await self._execute_authenticated_request(
                method=method, path=path, **kwargs
            )
            if r.status_code != 401:
                r.raise_for_status()
                return r

            await r.aclose()

            logger.warning(
                "401 Unauthorized on %s %s. Attempting token refresh...",
                method,
                path,
            )
            if self._try_refresh_token():
                # Drop the stale explicit token so _execute_authenticated_request
                # falls back to _current_access_token() and picks up the refreshed one.
                retry_kwargs = {k: v for k, v in kwargs.items() if k != "access_token"}
                r = await self._execute_authenticated_request(
                    method=method, path=path, **retry_kwargs
                )

            r.raise_for_status()
            return r
