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
from typing import Any, Callable, Dict, List, Optional, Sequence

import requests
from fred_core import VectorSearchHit
from pydantic import TypeAdapter
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from agentic_backend.application_context import get_app_context

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
        question: str,
        top_k: int = 10,
        document_library_tags_ids: Optional[Sequence[str]] = None,
        search_policy: Optional[str] = None,
        session_id: Optional[str] = None,
        include_session_scope: bool = True,
        include_corpus_scope: bool = True,
    ) -> List[VectorSearchHit]:
        """
        Wire format (matches controller):
          POST /vector/search
          {
            "question": str,
            "top_k": int,
            "library_tags_ids": [str]?,
            "search_policy": str?,
            "session_id": str?,
            "include_session_scope": bool,
            "include_corpus_scope": bool,
          }
        """
        payload: Dict[str, Any] = {"question": question, "top_k": top_k}
        if document_library_tags_ids:
            payload["document_library_tags_ids"] = list(document_library_tags_ids)
        if search_policy:
            payload["search_policy"] = search_policy
        if session_id:
            payload["session_id"] = session_id
            payload["include_session_scope"] = include_session_scope
        payload["include_corpus_scope"] = include_corpus_scope

        r = self._post_with_auth_retry("/vector/search", payload)
        r.raise_for_status()

        raw = r.json()
        if not isinstance(raw, list):
            logger.warning("Unexpected vector search payload type: %s", type(raw))
            return []
        return _HITS.validate_python(raw)
