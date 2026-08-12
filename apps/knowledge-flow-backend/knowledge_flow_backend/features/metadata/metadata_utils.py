from datetime import datetime, timezone
from pathlib import Path

from fred_core.documents.document_structures import (
    DocumentMetadata,
    FileInfo,
    FileType,
    Identity,
    SourceInfo,
    SourceType,
)

from knowledge_flow_backend.core.stores.catalog.base_catalog_store import PullFileEntry


def _ext_to_filetype(name: str) -> FileType:
    ext = Path(name).suffix.lower().lstrip(".")
    return {
        "pdf": FileType.PDF,
        "docx": FileType.DOCX,
        "pptx": FileType.PPTX,
        "xlsx": FileType.XLSX,
        "csv": FileType.CSV,
        "md": FileType.MD,
        "markdown": FileType.MD,
        "html": FileType.HTML,
        "htm": FileType.HTML,
        "txt": FileType.TXT,
    }.get(ext, FileType.OTHER)


def file_entry_to_metadata(entry: PullFileEntry, source_tag: str) -> DocumentMetadata:
    """
    Build minimal, valid DocumentMetadata (v2) for a file discovered in a pull catalog.
    Only facts we truly know are set; everything else keeps defaults.
    """
    name = Path(entry.path).name
    uid = f"pull-{source_tag}-{entry.hash}"
    ts = datetime.fromtimestamp(entry.modified_time, tz=timezone.utc)

    identity = Identity(
        document_uid=uid,
        document_name=name,
        title=Path(name).stem,  # safe default for UI
        modified=ts,  # created unknown -> leave None
    )

    source = SourceInfo(
        source_type=SourceType.PULL,
        source_tag=source_tag,
        pull_location=entry.path,  # relative path within the source
        retrievable=False,  # keep behavior consistent with your previous code
        date_added_to_kb=ts,  # first time we saw it in catalog
    )

    file = FileInfo(
        file_type=_ext_to_filetype(name),
        file_size_bytes=entry.size,
        # other fields (mime, sha256, language, page/row counts) unknown here
    )

    return DocumentMetadata(
        identity=identity,
        source=source,
        file=file,
        # tags/access/processing remain defaults
    )


# === Business labels (descriptive, no access-control meaning) ===
#
# Pure normalization for label values. Kept pure so the contract (dedupe,
# trimming) is unit-testable without the metadata store or ApplicationContext.
# Assignment itself (add/remove) is no longer a Python list transform — it's
# a row insert/delete against `document_labels`, idempotent via the table's
# own primary key (see MetadataService.mutate_document_labels).


def normalize_labels(labels: list[str]) -> list[str]:
    """Trim, drop empties, and de-duplicate labels while preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in labels:
        label = (raw or "").strip()
        if label and label not in seen:
            seen.add(label)
            out.append(label)
    return out
