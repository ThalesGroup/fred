from typing import List, Tuple

from fred_core import Action, KeycloakUser, Resource, authorize

from knowledge_flow_backend.application_context import ApplicationContext
from fred_core.processors import DocumentMetadata
from knowledge_flow_backend.core.stores.catalog.base_catalog_store import PullFileEntry
from knowledge_flow_backend.features.metadata.metadata_utils import file_entry_to_metadata


class SourceNotFoundError(ValueError):
    def __init__(self, source_tag: str):
        super().__init__(f"Unknown source_tag: {source_tag}")
        self.source_tag = source_tag


class PullDocumentService:
    def __init__(self):
        self.config = ApplicationContext.get_instance().get_config()
        self.catalog_store = ApplicationContext.get_instance().get_catalog_store()
        self.metadata_store = ApplicationContext.get_instance().get_metadata_store()

    @authorize(action=Action.READ, resource=Resource.DOCUMENTS)
    def list_pull_documents(self, user: KeycloakUser, source_tag: str, offset: int = 0, limit: int = 50) -> Tuple[List[DocumentMetadata], int]:
        source = self.config.document_sources.get(source_tag)
        if not source or source.type != "pull":
            raise SourceNotFoundError(source_tag)

        # Step 1: List and count all catalog entries
        all_entries: List[PullFileEntry] = self.catalog_store.list_entries(source_tag)
        total_count = len(all_entries)

        # Step 2: Paginate
        paginated_entries = all_entries[offset : offset + limit]

        # Step 3: Map known metadata
        known_docs: List[DocumentMetadata] = self.metadata_store.list_by_source_tag(source_tag)
        docs_by_path = {doc.pull_location: doc for doc in known_docs if doc.pull_location}

        # Step 4: Construct result
        result: List[DocumentMetadata] = []
        for entry in paginated_entries:
            if entry.path in docs_by_path:
                result.append(docs_by_path[entry.path])
            else:
                result.append(file_entry_to_metadata(entry, source_tag))

        return result, total_count
