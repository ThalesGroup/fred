# app/core/http/knowledge_flow_client.py

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

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
    Handles authentication token refresh automatically on 401.
    """

    def __init__(self, allowed_methods: frozenset):
        ctx = get_app_context()
        oa = ctx.get_outbound_auth()

        # Base URL: ensure no trailing slash so path concatenation is safe
        # NOTE: Using the API base URL, as the Asset Controller is an API endpoint.
        self.base_url = ctx.get_knowledge_flow_base_url().rstrip("/")

        tcfg = ctx.configuration.ai.timeout
        connect_t = float(tcfg.connect or 5)
        read_t = float(tcfg.read or 30)  # Defaulting to a longer read for streams
        self.timeout: float | tuple[float, float] = (connect_t, read_t)

        # Session setup uses the specific methods required by the derived class
        self.session = _session_with_retries(allowed_methods)
        self.session.auth = oa.auth
        self._on_auth_refresh: Optional[Callable[[], None]] = oa.refresh

    def _request_once(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        """Executes a single authenticated request."""
        url = f"{self.base_url}{path}"
        return self.session.request(method, url, timeout=self.timeout, **kwargs)

    def _request_with_auth_retry(
        self, method: str, path: str, **kwargs: Any
    ) -> requests.Response:
        """Executes a request, retrying once if a 401 is received."""
        r = self._request_once(method, path, **kwargs)
        if r.status_code == 401 and self._on_auth_refresh is not None:
            try:
                logger.info(
                    "401 from Knowledge Flow — refreshing token and retrying once."
                )
                self._on_auth_refresh()
            except Exception as e:
                logger.warning("Token refresh failed; returning original 401: %s", e)
                return r
            r = self._request_once(method, path, **kwargs)
        return r
