from datetime import datetime, timezone
from pathlib import Path

from app.common.document_structures import DocumentMetadata, SourceType
from app.core.stores.catalog.base_catalog_store import PullFileEntry


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
        keywords=None,
    )
