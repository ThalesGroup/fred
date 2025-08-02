import logging

from app.common.document_structures import SourceType
from app.common.structures import DocumentSourceConfig

logger = logging.getLogger(__name__)
class UnknownSourceTagError(ValueError):
    """Raised when a source_tag is not configured in the system."""

def resolve_source_type(source_tag: str) -> SourceType:
    from app.application_context import ApplicationContext

    config = ApplicationContext.get_instance().get_config()
    try:
        source_config: DocumentSourceConfig = config.document_sources[source_tag]
    except KeyError:
        logger.error(f"[resolve_source_type] Unknown source tag: {source_tag}")
        raise UnknownSourceTagError(f"Unknown source tag: '{source_tag}'")
 
    if source_config.type == "push":
        return SourceType.PUSH
    elif source_config.type == "pull":
        return SourceType.PULL
    else:
        raise ValueError(f"Invalid source type for tag '{source_tag}': {source_config.type}")


