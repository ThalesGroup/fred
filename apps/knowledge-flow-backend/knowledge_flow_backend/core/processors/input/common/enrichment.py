# app/core/processors/input/common/enrichment.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from knowledge_flow_backend.common.document_structures import FileType

# Strings that should be treated as “unknown”
_UNKNOWN = {"", "unknown", "non disponible", "none", "-", "n/a"}


def _clean_str(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return None if s.lower() in _UNKNOWN else s


def _parse_dt(v: Any) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v))
    except Exception:
        return None


def _coerce_ft(v: Any) -> Optional[FileType]:
    if v is None:
        return None
    if isinstance(v, FileType):
        return v
    try:
        return FileType(str(v).lower())
    except Exception:
        return None


def normalize_enrichment(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Accept a dict from any processor and return a clean dict limited to our contract.
    Unknowns => None. Synonyms mapped. Unknown keys dropped.
    """
    raw = dict(raw or {})

    # map common synonyms
    if "num_pages" in raw and "page_count" not in raw:
        raw["page_count"] = raw.pop("num_pages")

    out: Dict[str, Any] = {
        # identity
        "title": _clean_str(raw.get("title")),
        "author": _clean_str(raw.get("author")),
        "created": _parse_dt(raw.get("created")),
        "modified": _parse_dt(raw.get("modified")),
        "last_modified_by": _clean_str(raw.get("last_modified_by")),
        # file
        "mime_type": _clean_str(raw.get("mime_type")),
        "file_size_bytes": raw.get("file_size_bytes") if isinstance(raw.get("file_size_bytes"), int) else None,
        "page_count": raw.get("page_count") if isinstance(raw.get("page_count"), int) else None,
        "row_count": raw.get("row_count") if isinstance(raw.get("row_count"), int) else None,
        "sha256": _clean_str(raw.get("sha256")),
        "language": _clean_str(raw.get("language")),
        "file_type": _coerce_ft(raw.get("file_type")),
        # source (rare at this stage)
        "pull_location": _clean_str(raw.get("pull_location")),
        # tags / folders
        "tag_ids": raw.get("tag_ids") if isinstance(raw.get("tag_ids"), list) else None,
        # access
        "license": _clean_str(raw.get("license")),
        "confidential": bool(raw["confidential"]) if "confidential" in raw and raw["confidential"] is not None else None,
        "acl": list(raw.get("acl") or []) if isinstance(raw.get("acl"), (list, tuple)) else None,
    }
    return out
