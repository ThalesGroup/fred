# app/common/vectorization_utils.py

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

from langchain.schema.document import Document

from knowledge_flow_backend.common.document_structures import DocumentMetadata

logger = logging.getLogger(__name__)


def _stable_id16_from_str(key: str) -> str:
    """
    Return a stable 16-hex-character identifier derived from `key`.
    Not used for any security decision. We use SHA-1 with
    `usedforsecurity=False` when available to satisfy Bandit/FIPS.
    """
    try:
        # Some builds (e.g., FIPS-enabled) support `usedforsecurity`.
        h = hashlib.new("sha1", usedforsecurity=False)  # type: ignore[call-arg]
    except TypeError:
        # `usedforsecurity` not supported on this Python/OpenSSL build.
        # This usage is non-security; suppress Bandit warning.
        h = hashlib.new("sha1")  # nosec B324
    h.update(key.encode("utf-8"))
    return h.hexdigest()[:16]


def flat_metadata_from(md: DocumentMetadata) -> dict:
    """
    WHY:
      - Our metadata model (DocumentMetadata) is nested and rich, but the
        vector store (OpenSearch) should only contain a FLAT and STABLE
        projection of fields.
      - This keeps the index schema predictable, queryable, and prevents
        index bloat from storing deeply nested or fast-changing structures.
      - Think of this as the "business card" of a document: only the
        essentials you need for retrieval and filtering.

    WHAT WE KEEP:
      - Identity (uid, name, title, author, timestamps)
      - Provenance (repository, pull location, when added)
      - File attributes (type, size, language, sha256, page count)
      - Tags / folders (so we can group/filter by library or topic)
      - Access info (license, confidentiality flags, ACL)

    WHY NOT KEEP EVERYTHING:
      - Storing too much in the vector index makes queries slower, mappings
        fragile, and risks leaking sensitive details. The full metadata is
        still preserved in the metadata store for richer inspection.
    """
    return {
        # --- identity ---
        "document_uid": md.identity.document_uid,
        "document_name": md.identity.document_name,
        "title": md.identity.title or md.identity.stem,
        "author": md.identity.author,
        "created": md.identity.created,
        "modified": md.identity.modified,
        "last_modified_by": md.identity.last_modified_by,
        # --- source ---
        "repository": md.source.source_tag,
        "pull_location": md.source.pull_location,
        "date_added_to_kb": md.source.date_added_to_kb,
        # — provenance for repo_url
        "repository_web": md.source.repository_web,
        "repo_ref": md.source.repo_ref,
        "file_path": md.source.file_path,
        # --- file ---
        "type": (md.file.file_type.value if md.file.file_type else None),
        "mime_type": md.file.mime_type,
        "file_size_bytes": md.file.file_size_bytes,
        "page_count": md.file.page_count,
        "row_count": md.file.row_count,
        "sha256": md.file.sha256,
        "language": md.file.language,
        # --- tags / folders ---
        "tag_ids": md.tags.tag_ids,
        # --- access control ---
        "license": md.access.license,
        "confidential": md.access.confidential,
        "acl": md.access.acl,  # keep if you actively filter on it in search
    }


def load_langchain_doc_from_metadata(file_path: str, metadata: DocumentMetadata) -> Document:
    """
    WHY:
      - LangChain expects a Document with `page_content` (text) and `metadata` (dict).
      - We use this to "wrap" our raw file + curated metadata into a consistent
        input for splitting, embedding, and storage.

    DESIGN CHOICE:
      - Always read the raw file as UTF-8 text for now (works for most textual inputs).
      - Metadata passed along is FLAT (via flat_metadata_from), not the full nested object.
        This avoids polluting the vector index with unstable fields.

    RESULT:
      - A clean LangChain Document with content + retrievable metadata.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File {file_path} not found.")

    content = path.read_text(encoding="utf-8")
    flat_md = flat_metadata_from(metadata)

    return Document(page_content=content, metadata=flat_md)


# --- Chunk-level metadata hygiene ---

# --- keep only what we index ---
_ALLOWED_CHUNK_KEYS = {
    "chunk_index",
    "chunk_uid",
    "char_start",
    "char_end",
    "heading_slug",
    "viewer_fragment",
    "original_doc_length",
    "section",
}

_INT_KEYS = {"chunk_index", "char_start", "char_end", "original_doc_length"}

_HEADER_KEYS = ("Header 1", "Header 2", "Header 3", "Header 4", "Header 5", "Header 6")


def _as_int(v):
    try:
        if v is None:
            return None
        if isinstance(v, bool):
            return int(v)
        return int(str(v).strip())
    except Exception:
        return None


def _build_viewer_fragment(proj):
    if proj.get("viewer_fragment"):
        return proj["viewer_fragment"]
    slug = proj.get("heading_slug")
    if slug:
        return f"h={slug}"
    cs, ce = proj.get("char_start"), proj.get("char_end")
    if cs is not None and ce is not None:
        return f"sel={cs}-{ce}"
    return None


def make_chunk_uid(document_uid: str, anchors: dict) -> str:
    """
    Stable id from doc uid + key anchors.
    If char offsets are present, they dominate; otherwise fall back to index+slug.
    """
    uid = document_uid or "unknown"
    parts = [
        uid,
        f"cs={anchors.get('char_start')}",
        f"ce={anchors.get('char_end')}",
        f"idx={anchors.get('chunk_index')}",
        f"hs={anchors.get('heading_slug')}",
    ]
    return _stable_id16_from_str("|".join(map(str, parts)))


def sanitize_chunk_metadata(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    dropped: List[str] = []

    # section from headers (nice for UX)
    headers = [str(raw.get(k)) for k in _HEADER_KEYS if raw.get(k) is not None]
    section = " / ".join(headers) if headers else (raw.get("section") or None)

    proj: Dict[str, Any] = {}
    for k in list(raw.keys()):
        if k not in _ALLOWED_CHUNK_KEYS:
            dropped.append(k)
            continue
        proj[k] = raw.get(k)

    if section:
        proj["section"] = section

    for k in _INT_KEYS:
        if k in proj:
            iv = _as_int(proj[k])
            if iv is None:
                dropped.append(k)
                proj.pop(k, None)
            else:
                proj[k] = iv

    frag = _build_viewer_fragment(proj)
    if frag:
        proj["viewer_fragment"] = frag

    proj = {k: v for k, v in proj.items() if v not in (None, "", [])}
    return proj, dropped


def make_stable_chunk_id(base_flat: Dict[str, Any], proj: Dict[str, Any]) -> str:
    """Stable id based on uid + anchors; avoids changing when chunk indices shift."""
    uid = base_flat.get("document_uid") or "unknown"
    # Use only anchor-ish fields so re-chunking with same spans keeps the id
    parts = [
        uid,
        f"p={proj.get('page')}",
        f"cs={proj.get('char_start')}",
        f"ce={proj.get('char_end')}",
        f"ls={proj.get('line_start')}",
        f"le={proj.get('line_end')}",
        f"hs={proj.get('heading_slug')}",
    ]
    key = "|".join(str(x) for x in parts)
    return _stable_id16_from_str(key)
