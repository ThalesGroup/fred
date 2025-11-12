# Copyright Thales 2025
# Apache-2.0

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from agentic_backend.application_context import get_app_context

logger = logging.getLogger(__name__)


def _session_with_retries(allowed_methods: frozenset) -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.3,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=allowed_methods,
        raise_on_status=False,
    )
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


if TYPE_CHECKING:
    from agentic_backend.core.agents.agent_flow import AgentFlow

TokenRefreshCallback = Callable[[], str]


class KfBaseClient:
    """
    Base client for secure, retrying access to Knowledge Flow (and related Fred backends).

    Fred rationale:
    - *Identity propagation* is the invariant. The source of identity may be:
      (a) an AgentFlow (agent runtime context), or
      (b) a conversation/session controller that holds a user access_token.
    - This client therefore accepts EITHER `agent=...` OR `access_token=...`.
      Optional `refresh_user_access_token` can be provided in session mode.
    """

    def __init__(
        self,
        allowed_methods: frozenset,
        *,
        agent: Optional["AgentFlow"] = None,
        access_token: Optional[str] = None,
        refresh_user_access_token: Optional[Callable[[], str]] = None,
    ):
        ctx = get_app_context()
        self.base_url = ctx.get_knowledge_flow_base_url().rstrip("/")

        tcfg = ctx.configuration.ai.timeout
        connect_t = float(tcfg.connect or 5)
        read_t = float(tcfg.read or 30)
        self.timeout: float | tuple[float, float] = (connect_t, read_t)

        self.session = _session_with_retries(allowed_methods)

        # --- Identity providers (exactly one mode should be used) ---
        self._agent = agent
        self._static_access_token = access_token
        self._refresh_cb = refresh_user_access_token

        # Sanity: allow either agent-mode OR session-mode
        if not self._agent and not self._static_access_token:
            raise ValueError("KfBaseClient requires either `agent` or `access_token`.")

    # ---------------------------
    # Internal helpers
    # ---------------------------

    def _current_access_token(self) -> str:
        """Uniform accessor for the access token regardless of mode."""
        if self._agent:
            token = getattr(self._agent.runtime_context, "access_token", None)
            if not token:
                raise ValueError("AgentFlow runtime_context has no access_token.")
            return token
        # session-mode
        if not self._static_access_token:
            raise ValueError("No access_token provided for session-scoped client.")
        return self._static_access_token

    def _try_refresh_token(self) -> bool:
        """
        Try to refresh token in either mode.
        Returns True if a refresh happened and token should be retried.
        """
        # Agent mode: delegate to agent if available
        if self._agent and getattr(self._agent, "refresh_user_access_token", None):
            try:
                self._agent.refresh_user_access_token()
                logger.info("Agent-led user token refresh succeeded.")
                return True
            except Exception as e:
                logger.error("Agent-led token refresh failed: %s", e)
                return False

        # Session mode: use provided callback if any
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

    def _execute_authenticated_request(
        self, method: str, path: str, **kwargs: Any
    ) -> requests.Response:
        url = f"{self.base_url}{path}"
        headers: Dict[str, str] = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._current_access_token()}"
        return self.session.request(
            method, url, timeout=self.timeout, headers=headers, **kwargs
        )

    def _request_with_token_refresh(
        self, method: str, path: str, **kwargs: Any
    ) -> requests.Response:
        """
        Executes a request, handling user-token expiration (401) via refresh and retry.
        Works identically in agent-mode and session-mode.
        """
        # attempt 0
        r = self._execute_authenticated_request(method=method, path=path, **kwargs)
        if r.status_code != 401:
            r.raise_for_status()
            return r

        logger.warning(
            "401 Unauthorized on %s %s. Attempting token refresh...", method, path
        )
        if self._try_refresh_token():
            # attempt 1
            r = self._execute_authenticated_request(method=method, path=path, **kwargs)

        r.raise_for_status()
        return r
