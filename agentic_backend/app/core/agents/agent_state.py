from __future__ import annotations
from dataclasses import dataclass, field
import logging
from typing import List, Optional, Dict, Any
import requests
from app.core.agents.runtime_context import (
    RuntimeContext,
    get_document_libraries_ids,
    get_prompt_libraries_ids,
)

logger = logging.getLogger(__name__)


@dataclass
class Prepared:
    # RAG scoping (always a list)
    doc_tag_ids: List[str] = field(default_factory=list)
    # Concatenated prompt(s) body text ("" when none)
    prompt_text: str = ""


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


def _fetch_body(kf_base: str, rid: str, timeout: float = 8.0) -> Optional[str]:
    """Return body text for a resource id, or None if not found/invalid."""
    try:
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
    # 1) Document libraries for RAG scoping
    doc_tags = list(get_document_libraries_ids(ctx) or [])

    # 2) Prompts: loop each id, append body when resolvable; ignore failures
    bodies: List[str] = []
    for pid in get_prompt_libraries_ids(ctx) or []:
        body = _fetch_body(kf_base, pid)
        if body:
            bodies.append(body)

    prompt_text = "\n\n".join(bodies) if bodies else ""
    return Prepared(doc_tag_ids=doc_tags, prompt_text=prompt_text)
