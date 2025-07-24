from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import List

from app.application_context import ApplicationContext
from app.common.document_structures import DocumentMetadata, SourceType
from app.common.structures import (
    DocumentSourceConfig,
)
from app.core.stores.metadata.base_catalog_store import PullFileEntry


def _scan_local_path(base_path: Path, source_tag: str) -> List[PullFileEntry]:
    entries = []
    base = base_path.expanduser().resolve()
    for path in base.rglob("*"):
        if path.is_file():
            relative = str(path.relative_to(base))
            stat = path.stat()
            entries.append(PullFileEntry(
                path=relative,
                size=stat.st_size,
                modified_time=stat.st_mtime,
                hash=hashlib.sha256(str(path).encode()).hexdigest()
            ))
    return entries


def scan_pull_source(source_tag: str) -> List[PullFileEntry]:
    config = ApplicationContext.get_instance().get_config()
    source: DocumentSourceConfig = config.document_sources.get(source_tag)

    if not source or source.type != "pull":
        raise ValueError(f"Invalid or unknown pull source: {source_tag}")

    return _scan_local_path(Path(source.base_path), source_tag)


def file_entry_to_metadata(entry: PullFileEntry, source_tag: str) -> DocumentMetadata:
    return DocumentMetadata(
        document_name=Path(entry.path).name,
        document_uid=f"pull-{source_tag}-{entry.hash}",
        date_added_to_kb=datetime.fromtimestamp(entry.modified_time, tz=timezone.utc),
        retrievable=False,
        source_tag=source_tag,
        pull_location=entry.path,
        source_type=SourceType.PULL,  # could be made dynamic in future
        processing_stages={},
        title=None,
        author=None,
        created=None,
        modified=datetime.fromtimestamp(entry.modified_time, tz=timezone.utc),
        last_modified_by=None,
        category=None,
        subject=None,
        keywords=None
    )
