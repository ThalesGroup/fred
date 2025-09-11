# agentic/.../vector_client.py

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Iterable, Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pydantic import TypeAdapter

from fred_core import VectorSearchHit
from app.application_context import get_app_context

logger = logging.getLogger(__name__)

_HITS = TypeAdapter(List[VectorSearchHit])


def _session_with_retries() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.3,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        raise_on_status=False,
    )
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


class VectorSearchClient:
    """
    Minimal authenticated client for Knowledge Flow's vector search.

    - Auth is provided by ApplicationContext.get_outbound_auth():
      * When security is enabled & secret present -> Bearer token automatically added
      * When disabled or secret missing -> NoAuth (no header), callers unchanged
    - On 401, forces a token refresh once and retries the request.
    """

    def __init__(self):
        ctx = get_app_context()
        oa = ctx.get_outbound_auth()

        # Base URL: ensure no trailing slash so path concatenation is safe
        self.base_url = ctx.get_knowledge_flow_base_url().rstrip("/")

        tcfg = ctx.configuration.ai.timeout
        connect_t = float(tcfg.connect or 5)
        read_t = float(tcfg.read or 15)
        self.timeout: float | tuple[float, float]
        self.timeout = (connect_t, read_t)
        self.session = _session_with_retries()
        self.session.auth = oa.auth
        self._on_auth_refresh: Optional[Callable[[], None]] = oa.refresh

    def _post_once(self, path: str, payload: Dict[str, Any]) -> requests.Response:
        url = f"{self.base_url}{path}"
        return self.session.post(url, json=payload, timeout=self.timeout)

    def _post_with_auth_retry(
        self, path: str, payload: Dict[str, Any]
    ) -> requests.Response:
        r = self._post_once(path, payload)
        if r.status_code == 401 and self._on_auth_refresh is not None:
            # Force-refresh and retry once
            try:
                logger.info(
                    "401 from Knowledge Flow — refreshing token and retrying once."
                )
                self._on_auth_refresh()
            except Exception as e:
                logger.warning("Token refresh failed; returning original 401: %s", e)
                return r
            r = self._post_once(path, payload)
        return r

    def search(
        self,
        *,
        query: str,
        top_k: int,
        tags: Optional[Sequence[str]] = None,
        payload_overrides: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchHit]:
        payload: Dict[str, Any] = {"query": query, "top_k": top_k}
        if tags:
            payload["tags"] = list(tags)
        if payload_overrides:
            payload.update(payload_overrides)

        r = self._post_with_auth_retry("/vector/search", payload)
        r.raise_for_status()

        try:
            raw = r.json()
        except ValueError as e:
            logger.error("Vector search returned non-JSON response: %s", e)
            raise

        if not isinstance(raw, Iterable):
            return []
        return _HITS.validate_python(raw)
