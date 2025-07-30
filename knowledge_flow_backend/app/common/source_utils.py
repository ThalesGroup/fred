from pathlib import Path

from app.common.document_structures import SourceType
from app.common.structures import DocumentSourceConfig


def resolve_source_type(source_tag: str) -> SourceType:
    from app.application_context import ApplicationContext

    config = ApplicationContext.get_instance().get_config()
    source_config: DocumentSourceConfig = config.document_sources.get(source_tag)

    if not source_config:
        raise ValueError(f"Unknown source tag: {source_tag}")

    if source_config.type == "push":
        return SourceType.PUSH
    elif source_config.type == "pull":
        return SourceType.PULL
    else:
        raise ValueError(f"Invalid source type for tag '{source_tag}': {source_config.type}")


def get_pull_base_path(source_tag: str) -> Path:
    from app.application_context import ApplicationContext

    config = ApplicationContext.get_instance().get_config()
    source_config: DocumentSourceConfig = config.document_sources.get(source_tag)

    if not source_config:
        raise ValueError(f"Unknown source tag: {source_tag}")
    if source_config.type != "pull":
        raise ValueError(f"Source tag '{source_tag}' is not a pull source")

    return Path(source_config.base_path).expanduser().resolve()
