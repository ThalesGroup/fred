from typing import List, NamedTuple

from fred_core import Action, KeycloakUser, Resource, authorize

from app.application_context import ApplicationContext
from app.common.structures import DocumentSourceConfig
from app.core.stores.catalog.base_catalog_store import PullFileEntry


class PullSourceNotFoundError(ValueError):
    def __init__(self, source_tag: str):
        super().__init__(f"Unknown source_tag: {source_tag}")
        self.source_tag = source_tag


class CatalogDiff(NamedTuple):
    added: List[PullFileEntry]
    modified: List[tuple[PullFileEntry, PullFileEntry]]  # (old, new)
    deleted: List[PullFileEntry]


class CatalogService:
    def __init__(self):
        self.config = ApplicationContext.get_instance().get_config()
        self.store = ApplicationContext.get_instance().get_catalog_store()

    @authorize(Action.READ, Resource.DOCUMENTS)
    def list_files(self, user: KeycloakUser, source_tag: str, offset: int = 0, limit: int = 100) -> List[PullFileEntry]:
        if not self.config.document_sources or source_tag not in self.config.document_sources:
            raise PullSourceNotFoundError(source_tag)
        return self.store.list_entries(source_tag)[offset : offset + limit]

    @authorize(Action.UPDATE, Resource.DOCUMENTS_SOURCES)
    def rescan_source(self, user: KeycloakUser, source_tag: str) -> CatalogDiff:
        if not self.config.document_sources or source_tag not in self.config.document_sources:
            raise PullSourceNotFoundError(source_tag)
        source_config = self.config.document_sources[source_tag]
        if source_config.type != "pull":
            raise NotImplementedError(f"Rescan not supported for source type: {source_config.type}")

        self.loader = ApplicationContext.get_instance().get_content_loader(source_tag)
        old_entries = self.store.list_entries(source_tag)
        new_entries = self.loader.scan()

        diff = self._compute_diff(old_entries, new_entries)

        if diff.added:
            self.store.add_entries(source_tag, diff.added)

        if diff.modified:
            mod = [x[1] for x in diff.modified]
            self.store.add_entries(source_tag, mod)

        if diff.deleted:
            self.store.delete_entries(source_tag, diff.deleted)

        return diff

    @authorize(Action.READ, Resource.DOCUMENTS_SOURCES)
    def get_document_sources(
        self,
        user: KeycloakUser,
    ) -> dict[str, DocumentSourceConfig]:
        return self.config.document_sources or {}

    def _compute_diff(self, old_entries: List[PullFileEntry], new_entries: List[PullFileEntry]) -> CatalogDiff:
        old_map = {e.path: e for e in old_entries}
        new_map = {e.path: e for e in new_entries}

        added = [e for path, e in new_map.items() if path not in old_map]
        deleted = [e for path, e in old_map.items() if path not in new_map]

        modified = []
        for path, new_e in new_map.items():
            old_e = old_map.get(path)
            if old_e and not self._entries_equal(old_e, new_e):
                modified.append((old_e, new_e))

        return CatalogDiff(added=added, modified=modified, deleted=deleted)

    def _entries_equal(self, a: PullFileEntry, b: PullFileEntry) -> bool:
        return a.hash == b.hash and a.size == b.size and a.modified_time == b.modified_time
