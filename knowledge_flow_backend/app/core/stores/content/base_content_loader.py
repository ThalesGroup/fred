from abc import ABC, abstractmethod
from pathlib import Path
from app.common.document_structures import DocumentMetadata
from app.common.structures import DocumentSourceConfig
from app.core.stores.metadata.base_catalog_store import PullFileEntry
from typing import List

class BaseContentLoader(ABC):
    def __init__(self, source: DocumentSourceConfig, source_tag: str):
        self.source = source
        self.source_tag = source_tag

    @abstractmethod
    def scan(self) -> List[PullFileEntry]:
        """List remote files from a pull source."""
        pass

    @abstractmethod
    def fetch_from_pull_entry(self, entry: PullFileEntry, destination_dir: Path) -> Path:
        """
        Fetch a file (or folder) from the remote source and store it locally.

        Returns the path to the downloaded file or folder.
        """
        pass

    @abstractmethod
    def fetch_from_metadata(self, metadata: DocumentMetadata, destination_dir: Path) -> Path:
        """
        Fetch a file based on metadata and store it locally.

        Returns the path to the downloaded file.
        """
        pass