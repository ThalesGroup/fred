# app/common/vectorization_utils.py

from pathlib import Path
from langchain.schema.document import Document

from app.common.document_structures import DocumentMetadata

def _flat_metadata_from(md: DocumentMetadata) -> dict:
    """
    Minimal, flat projection from DocumentMetadata to the fields
    your index expects under `metadata.*`. No new features, just mapping.
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
        "repository": md.source.source_tag,         # previously source_tag
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

        # --- tags / folders (if present; harmless if empty) ---
        "tag_ids": md.tags.tag_ids,
        "tag_names": md.tags.tag_names,
        "library_path": md.tags.library_path,
        "library_folder": md.tags.library_folder,

        # --- access (optional fields preserved) ---
        "license": md.access.license,
        "confidential": md.access.confidential,
        "acl": md.access.acl,
    }

def load_langchain_doc_from_metadata(file_path: str, metadata: DocumentMetadata) -> Document:
    """
    EXACT same behavior as before for content (read the file as text),
    but projects DocumentMetadata v2 -> flat dict for OpenSearch.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File {file_path} not found.")

    # Keep your original behavior: read the file as UTF‑8 text
    content = path.read_text(encoding="utf-8")

    # NEW: use flat metadata instead of nested model_dump
    flat_md = _flat_metadata_from(metadata)

    return Document(page_content=content, metadata=flat_md)
