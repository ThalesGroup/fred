import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class GraphSearchClient:
    """
    Simple HTTP client for Graph Search microservice.
    """

    def __init__(
        self,
        *,
        base_url: str,
        timeout: float = 10.0,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        if headers:
            self.session.headers.update(headers)

    def search(
        self,
        *,
        question: str,
        top_k: int = 10,
        center_uid: Optional[str] = None,
    ) -> List[Any]:
        payload: Dict[str, Any] = {
            "query": question,
            "top_k": top_k,
        }
        if isinstance(center_uid, str) and center_uid.strip():
            payload["center_uid"] = center_uid.strip()

        url = f"{self.base_url}/graph/search"

        logger.debug("POST %s payload=%s", url, payload)

        r = self.session.post(
            url,
            json=payload,
            timeout=self.timeout,
        )

        r.raise_for_status()

        data = r.json()
        if not isinstance(data, list):
            logger.warning("Unexpected graph search response type: %s", type(data))
            return []

        return data
