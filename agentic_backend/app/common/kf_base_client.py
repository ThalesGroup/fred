# app/core/http/knowledge_flow_client.py

from __future__ import annotations

import logging
from typing import Any, Dict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.application_context import get_app_context

logger = logging.getLogger(__name__)


def _session_with_retries(allowed_methods: frozenset) -> requests.Session:
    """Creates a requests session configured with retries for transient errors."""
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


class KfBaseClient:
    """
    Base client providing secured, retrying access to any Fred/Knowledge Flow backend service.

    This client is designed for **end-user identity propagation** and requires an
    `access_token` to be explicitly passed for all requests. M2M authentication is removed.
    """

    def __init__(self, allowed_methods: frozenset):
        ctx = get_app_context()

        # Base URL: ensure no trailing slash so path concatenation is safe
        self.base_url = ctx.get_knowledge_flow_base_url().rstrip("/")

        tcfg = ctx.configuration.ai.timeout
        connect_t = float(tcfg.connect or 5)
        read_t = float(tcfg.read or 30)  # Defaulting to a longer read for streams
        self.timeout: float | tuple[float, float] = (connect_t, read_t)

        # Session setup uses the specific methods required by the derived class.
        # Note: session.auth is NOT set, as we rely solely on the request-time header.
        self.session = _session_with_retries(allowed_methods)

        # M2M token refresh logic is removed, as we don't use M2M tokens.
        # self._on_auth_refresh = None # (or just don't define it)

    def _request_once(
        self, method: str, path: str, access_token: str, **kwargs: Any
    ) -> requests.Response:
        """
        Executes a single authenticated request. Requires `access_token`.
        """
        if not access_token:
            raise ValueError(
                "Cannot make an authenticated request: 'access_token' must be provided to KfBaseClient."
            )

        url = f"{self.base_url}{path}"

        headers: Dict[str, str] = kwargs.pop("headers", {})

        # Set the Bearer header with the required user token.
        headers["Authorization"] = f"Bearer {access_token}"

        return self.session.request(
            method, url, timeout=self.timeout, headers=headers, **kwargs
        )

    def _request_with_auth_retry(
        self, method: str, path: str, access_token: str, **kwargs: Any
    ) -> requests.Response:
        """
        Executes a request. No token refresh logic is needed here as user tokens
        cannot be refreshed by the backend service.
        """
        # We only need one attempt, as the retry logic in `_session_with_retries`
        # handles transient network/server errors (5xx, 429), and we don't handle
        # a 401 (expired token) with a refresh.
        r = self._request_once(method, path, access_token=access_token, **kwargs)

        # If the user token is expired, the caller will handle the resulting 401
        # or the request will fail with `r.raise_for_status()` if called later.

        return r
