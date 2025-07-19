from datetime import datetime
import hashlib
from pathlib import Path
from typing import List
from app.application_context import ApplicationContext
from app.common.structures import DocumentIngestionType, DocumentMetadata, DocumentProcessingStatus, PullSourceType
from app.core.stores.metadata.base_catalog_store import PullFileEntry

def scan_local_path(base_path: Path, source_tag: str) -> List[PullFileEntry]:
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
    source = config.pull_sources.get(source_tag)
    if not source:
        raise ValueError(f"Unknown source_tag: {source_tag}")
    if source.type != PullSourceType.LOCAL_PATH:
        raise NotImplementedError(f"Pull source type not supported: {source.type}")

    return scan_local_path(Path(source.base_path), source_tag)

def file_entry_to_metadata(entry: PullFileEntry, source_tag: str) -> DocumentMetadata:
    return DocumentMetadata(
        document_name=entry.path.split("/")[-1],
        document_uid=f"pull-{source_tag}-{entry.hash}",
        date_added_to_kb=datetime.fromtimestamp(entry.modified_time),
        retrievable=False,
        processing_status=DocumentProcessingStatus.UPLOADED,
        ingestion_type=DocumentIngestionType.PULL,
        source_tag=source_tag,
        pull_location=entry.path,
        pull_source_type=PullSourceType.LOCAL_PATH,
        title=None,
        author=None,
        created=None,
        modified=datetime.fromtimestamp(entry.modified_time),
        last_modified_by=None,
        category=None,
        subject=None,
        keywords=None
    )