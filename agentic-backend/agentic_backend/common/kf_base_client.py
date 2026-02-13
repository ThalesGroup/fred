# Copyright Thales 2025
# Apache-2.0

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

import requests
from fred_core.kpi import KPIActor
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


def _session_without_retries() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=0,
        backoff_factor=0,
        status_forcelist=(),
        allowed_methods=frozenset(),
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
        self._kpi = ctx.get_kpi_writer()

        tcfg = ctx.configuration.ai.timeout
        connect_t = float(tcfg.connect or 5)
        read_t = float(tcfg.read or 30)
        self.timeout: float | tuple[float, float] = (connect_t, read_t)

        self.session = _session_with_retries(allowed_methods)
        self.session_no_retry = _session_without_retries()

        self._agent = agent
        self._static_access_token = access_token
        self._refresh_cb = refresh_user_access_token

        if not self._agent and not self._static_access_token:
            raise ValueError("KfBaseClient requires either `agent` or `access_token`.")

    def _kpi_actor(self) -> KPIActor:
        groups = None
        if self._agent:
            groups = getattr(self._agent.runtime_context, "user_groups", None)
        return KPIActor(type="system", groups=groups)

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
            session_id = getattr(
                getattr(self._agent, "runtime_context", None), "session_id", None
            )
            if session_id:
                dims["session_id"] = str(session_id)
            user_id = getattr(
                getattr(self._agent, "runtime_context", None), "user_id", None
            )
            if user_id:
                dims["user_id"] = str(user_id)
        return dims

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
        if not self._static_access_token:
            raise ValueError("No access_token provided for session-scoped client.")
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

    def _execute_authenticated_request(
        self, method: str, path: str, **kwargs: Any
    ) -> requests.Response:
        """
        Executes an HTTP request with Bearer authentication.
        If an explicit 'access_token' kwarg is provided, it overrides the default one.
        """
        url = f"{self.base_url}{path}"

        # Support explicit override of the token
        token = kwargs.pop("access_token", None) or self._current_access_token()

        headers: Dict[str, str] = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"

        use_no_retry = "files" in kwargs and kwargs.get("files") is not None
        session = self.session_no_retry if use_no_retry else self.session
        return session.request(
            method, url, timeout=self.timeout, headers=headers, **kwargs
        )

    def _request_with_token_refresh(
        self, method: str, path: str, **kwargs: Any
    ) -> requests.Response:
        """
        Executes a request, handling user-token expiration (401) via refresh and retry.
        """
        dims = self._kpi_dims(method=method, path=path)
        with self._kpi.timer(
            "kf.request_latency_ms",
            dims=dims,
            actor=self._kpi_actor(),
        ) as kpi_dims:
            r = self._execute_authenticated_request(method=method, path=path, **kwargs)
            kpi_dims["http_status"] = str(r.status_code)
            if r.status_code != 401:
                r.raise_for_status()
                return r

            logger.warning(
                "401 Unauthorized on %s %s. Attempting token refresh...", method, path
            )
            if self._try_refresh_token():
                r = self._execute_authenticated_request(
                    method=method, path=path, **kwargs
                )
                kpi_dims["http_status"] = str(r.status_code)

            r.raise_for_status()
            return r
