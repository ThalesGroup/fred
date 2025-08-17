# app/common/vectorization_utils.py

from pathlib import Path
from langchain.schema.document import Document
from typing import Dict, Any, List, Tuple, Optional
import logging

from app.common.document_structures import DocumentMetadata
logger = logging.getLogger(__name__)


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
        "acl": md.access.acl,
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

# Only allow a controlled subset of keys to survive chunk-level metadata.
# WHY: splitters produce lots of noisy, tool-specific metadata that we don’t want
# to leak into the index (bounding boxes, parser internals, temp paths).
_ALLOWED_CHUNK_KEYS = {
    "page", "page_start", "page_end",
    "char_start", "char_end",
    "viewer_fragment",
    "original_doc_length", "chunk_id",
    "section",
}

# Splitters may emit hierarchical headers (like "Header 1" … "Header 6").
# We collapse these into a single `section` field for easier retrieval/filtering.
_HEADER_KEYS = ("Header 1", "Header 2", "Header 3", "Header 4", "Header 5", "Header 6")


def _as_int(v) -> Optional[int]:
    # WHY: ensure all positional markers (page, char offsets) are numeric
    # so OpenSearch mappings stay consistent (int not string).
    try:
        if v is None: return None
        if isinstance(v, bool): return int(v)  # avoid True/False creeping in
        return int(str(v).strip())
    except Exception:
        return None


def sanitize_chunk_metadata(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    WHY WE SANITIZE:
      - Splitters (pdf, html, unstructured) generate many ad-hoc fields.
      - If we index them blindly, the vector index schema becomes unstable,
        queries slow down, and confidential/internal info may leak.
      - By whitelisting, coercing, and dropping, we guarantee that every
        chunk looks the same in the index.

    STEPS:
      1. Compute a synthetic `section` name from headers if available.
         (WHY: makes retrieval explanations human-friendly: “Section: Intro / Methods”)
      2. Keep only keys we explicitly allow (`_ALLOWED_CHUNK_KEYS`).
      3. Inject computed `section` if it exists.
      4. Coerce positional fields to integers (WHY: avoid mapping conflicts).
      5. Drop None/empty fields (WHY: keep index lean).
      6. Return (cleaned_metadata, dropped_keys) so developers can monitor
         what was discarded — important for debugging and schema hygiene.

    EXAMPLE:

        >>> raw = {
        ...     "page": "12",
        ...     "Header 1": "Introduction",
        ...     "Header 2": "Motivation",
        ...     "bbox": [0, 0, 400, 200],  # noisy field from PDF parser
        ...     "char_start": "340",
        ...     "char_end": "520",
        ...     "tmp_path": "/tmp/parser/foo",  # sensitive internal field
        ... }

        >>> clean, dropped = sanitize_chunk_metadata(raw)
        >>> clean
        {
            "page": 12,
            "char_start": 340,
            "char_end": 520,
            "section": "Introduction / Motivation"
        }
        >>> dropped
        ["bbox", "tmp_path"]

         
    RESULT:
      - Stable, predictable chunk metadata ready for storage in vector DB.
      - Dropped keys list provides visibility into unexpected splitter behavior.
    """
    dropped: List[str] = []

    # 1) build section from headers if available
    headers = [str(raw.get(k)) for k in _HEADER_KEYS if raw.get(k) is not None]
    section = " / ".join(headers) if headers else (raw.get("section") or None)

    # 2) project allowed keys
    proj: Dict[str, Any] = {}
    for k in list(raw.keys()):
        if k not in _ALLOWED_CHUNK_KEYS:
            dropped.append(k)
            continue
        proj[k] = raw.get(k)

    # 3) inject computed section if not set or empty
    if section:
        proj["section"] = section

    # 4) type coercion
    for k in ("page", "page_start", "page_end", "char_start", "char_end", "original_doc_length"):
        if k in proj:
            iv = _as_int(proj[k])
            if iv is None:
                dropped.append(k)  # bad type, drop field to avoid mapping issues
                proj.pop(k, None)
            else:
                proj[k] = iv

    # 5) drop None/empty
    proj = {k: v for k, v in proj.items() if v not in (None, "", [])}

    return proj, dropped
