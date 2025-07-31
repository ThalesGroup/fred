from app.application_context import ApplicationContext
from app.common.structures import DocumentSourceConfig
from app.core.stores.metadata.base_catalog_store import PullFileEntry
from typing import List


class PullSourceNotFoundError(ValueError):
    def __init__(self, source_tag: str):
        super().__init__(f"Unknown source_tag: {source_tag}")
        self.source_tag = source_tag


class CatalogService:
    def __init__(self):
        self.config = ApplicationContext.get_instance().get_config()
        self.store = ApplicationContext.get_instance().get_catalog_store()
        self.loader = ApplicationContext.get_instance().get_langchain_document_loader()

    def list_files(self, source_tag: str, offset: int = 0, limit: int = 100) -> List[PullFileEntry]:
        if not self.config.document_sources or source_tag not in self.config.document_sources:
            raise PullSourceNotFoundError(source_tag)
        return self.store.list_entries(source_tag)[offset : offset + limit]

    def rescan_source(self, source_tag: str) -> int:
        if not self.config.document_sources or source_tag not in self.config.document_sources:
            raise PullSourceNotFoundError(source_tag)
        entries = self.loader.scan_pull_source(source_tag)
        self.store.save_entries(source_tag, entries)
        return len(entries)

    def get_document_sources(self) -> dict[str, DocumentSourceConfig]:
        return self.config.document_sources or {}
