import logging
from pathlib import Path

from app.common.document_structures import SourceType
from app.common.structures import DocumentSourceConfig, FileSystemPullSource

logger = logging.getLogger(__name__)

def resolve_source_type(source_tag: str) -> SourceType:
    from app.application_context import ApplicationContext

    config = ApplicationContext.get_instance().get_config()
    source_config: DocumentSourceConfig = config.document_sources[source_tag]

    if not source_config:
        logger.error(f"[MetadataStore] Unknown source tag encountered: {source_tag}")
        raise ValueError(f"Unknown source tag: {source_tag}")

    if source_config.type == "push":
        return SourceType.PUSH
    elif source_config.type == "pull":
        return SourceType.PULL
    else:
        raise ValueError(f"Invalid source type for tag '{source_tag}': {source_config.type}")


