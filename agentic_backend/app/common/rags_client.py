# app/core/rag/rag_client.py
import requests
from typing import Any, Dict, List, Optional, Sequence, Iterable
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pydantic import TypeAdapter
from fred_core import VectorSearchHit

_HITS = TypeAdapter(List[VectorSearchHit])

def _session_with_retries() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.3,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s

class VectorSearchClient:
    def __init__(self, base_url: str, timeout_s: int = 10, session: Optional[requests.Session] = None):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.session = session or _session_with_retries()

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

        r = self.session.post(f"{self.base_url}/vector/search", json=payload, timeout=self.timeout_s)
        r.raise_for_status()
        raw = r.json()
        if not isinstance(raw, Iterable):
            return []
        return _HITS.validate_python(raw)
