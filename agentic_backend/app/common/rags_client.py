# app/core/rag/rag_client.py
import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence
from pydantic import TypeAdapter
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from fred_core import VectorSearchHit  # your shared model

logger = logging.getLogger(__name__)

_HITS_ADAPTER = TypeAdapter(List[VectorSearchHit])

def _new_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.3,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET","POST"]),
        raise_on_status=False,
    )
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s

class VectorSearchClient:
    def __init__(self, base_url: str, timeout_s: int = 10, session: Optional[requests.Session] = None):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.session = session or _new_session()

    def search(
        self,
        query: str,
        *,
        top_k: int = 3,
        tags: Optional[Sequence[str]] = None,
        payload_overrides: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchHit]:
        data: Dict[str, Any] = {"query": query, "top_k": top_k}
        if tags:
            data["tags"] = list(tags)
        if payload_overrides:
            data.update(payload_overrides)

        url = f"{self.base_url}/vector/search"
        resp = self.session.post(url, json=data, timeout=self.timeout_s)
        resp.raise_for_status()
        raw = resp.json()
        if not isinstance(raw, Iterable):
            logger.warning("Vector search returned non-iterable JSON: %s", type(raw))
            return []
        try:
            hits = _HITS_ADAPTER.validate_python(raw)
        except Exception:
            logger.exception("Failed to parse VectorSearchHit list.")
            return []
        return hits
