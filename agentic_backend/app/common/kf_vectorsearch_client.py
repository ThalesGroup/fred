# agentic/.../vector_client.py

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from fred_core import VectorSearchHit
from pydantic import TypeAdapter

# NOTE: Updated import path based on the previous context (renamed from app.core.http)
from app.common.kf_base_client import KfBaseClient

logger = logging.getLogger(__name__)

_HITS = TypeAdapter(List[VectorSearchHit])


class VectorSearchClient(KfBaseClient):
    """
    Minimal authenticated client for Knowledge Flow's vector search.

    This client is designed for end-user identity propagation and requires an
    access_token for all requests. Inherits session and retry logic from KfBaseClient.
    """

    def __init__(self):
        # The VectorSearchClient only needs to support POST for its 'search' method.
        super().__init__(allowed_methods=frozenset({"POST"}))

    def search(
        self,
        *,
        question: str,
        top_k: int = 10,
        document_library_tags_ids: Optional[Sequence[str]] = None,
        search_policy: Optional[str] = None,
        # --- NEW: MUST require access_token for user identity propagation ---
        access_token: str,
        # ------------------------------------------------------------------
    ) -> List[VectorSearchHit]:
        """
        Wire format (matches controller):
          POST /vector/search
          {
            "question": str,
            "top_k": int,
            "library_tags_ids": [str]?,
            "search_policy": str?
          }
        """
        if not access_token:
            raise ValueError(
                "The 'access_token' is required for user-authenticated vector search."
            )

        payload: Dict[str, Any] = {"question": question, "top_k": top_k}
        if document_library_tags_ids:
            payload["document_library_tags_ids"] = list(document_library_tags_ids)
        if search_policy:
            payload["search_policy"] = search_policy

        # Use the base class's request method, passing the required access_token.
        r = self._request_with_auth_retry(
            method="POST",
            path="/vector/search",
            access_token=access_token,  # Pass the required user token
            json=payload,
        )
        r.raise_for_status()

        raw = r.json()
        if not isinstance(raw, list):
            logger.warning("Unexpected vector search payload type: %s", type(raw))
            return []
        return _HITS.validate_python(raw)
