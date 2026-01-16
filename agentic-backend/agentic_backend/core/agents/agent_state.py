from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

from agentic_backend.common.kf_base_client import KfBaseClient
from agentic_backend.core.agents.runtime_context import (
    RuntimeContext,
    get_access_token,
    get_chat_context_libraries_ids,
    get_document_library_tags_ids,
)

logger = logging.getLogger(__name__)


@dataclass
class Prepared:
    # RAG scoping (always a list)
    doc_tag_ids: List[str] = field(default_factory=list)
    # Concatenated profile prompt(s) body text ("" when none)
    prompt_chat_context_text: str = ""


def _split_front_matter(text: str) -> str:
    """Return body (no header). Supports both '---\\nheader\\n---\\nbody' and 'header\\n---\\nbody'."""
    s = (text or "").replace("\r\n", "\n")
    if s.startswith("---\n"):
        try:
            _, body = s.split("\n---\n", 1)
            return body
        except ValueError:
            return s
    if "\n---\n" in s:
        try:
            _, body = s.split("\n---\n", 1)
            return body
        except ValueError:
            return s
    return s


def _fetch_body(
    kf_base: str,
    rid: str,
    *,
    access_token: Optional[str] = None,
    timeout: float = 8.0,
) -> Optional[str]:
    """Return body text for a resource id, or None if not found/invalid."""
    try:
        if access_token:
            client = KfBaseClient(
                allowed_methods=frozenset({"GET"}),
                access_token=access_token,
            )
            client.base_url = kf_base.rstrip("/")
            client.timeout = (timeout, timeout)
            resp = client._request_with_token_refresh("GET", f"/resources/{rid}")
        else:
            logger.warning(
                "No access token available for knowledge-flow resource fetch (rid=%s).",
                rid,
            )
            resp = requests.get(f"{kf_base}/resources/{rid}", timeout=timeout)
        if resp.status_code != 200:
            logger.warning(
                f"Failed to fetch body for resource {rid}: {resp.status_code}"
            )
            return None
        data: Dict[str, Any] = resp.json()
        content = data.get("content")
        if not isinstance(content, str):
            return None
        return _split_front_matter(content)
    except Exception:
        return None


def resolve_prepared(ctx: RuntimeContext, kf_base: str) -> Prepared:
    """
    Resolve and return the prepared data for the given runtime context.
    This includes:
        1) Document library tags for RAG scoping.
        2) Concatenated profile prompt bodies.
    """
    # 1) Document libraries for RAG scoping
    doc_tags = list(get_document_library_tags_ids(ctx) or [])

    # 2) Prompts: loop each id, append body when resolvable; ignore failures
    bodies: List[str] = []
    access_token = get_access_token(ctx)
    for pid in get_chat_context_libraries_ids(ctx) or []:
        body = _fetch_body(kf_base, pid, access_token=access_token)
        if body:
            bodies.append(body)

    prompt_profile_text = "\n\n".join(bodies) if bodies else ""
    return Prepared(doc_tag_ids=doc_tags, prompt_chat_context_text=prompt_profile_text)
