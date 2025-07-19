# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from abc import abstractmethod
from typing import List

from app.common.structures import DocumentMetadata
from app.core.stores.metadata.base_catalog_store import BaseCatalogStore


class BaseMetadataStore(BaseCatalogStore):
    @abstractmethod
    def get_all_metadata(self, filters: dict) -> List[DocumentMetadata]:
        pass

    @abstractmethod
    def list_by_source_tag(self, source_tag: str) -> List[DocumentMetadata]:
        """
        Return all metadata entries ingested from a specific pull source.
        """
        pass
    
    @abstractmethod
    def get_metadata_by_uid(self, document_uid: str) -> DocumentMetadata:
        pass

    @abstractmethod
    def update_metadata_field(self, document_uid: str, field: str, value) -> DocumentMetadata:
        pass

    @abstractmethod
    def save_metadata(self, metadata: DocumentMetadata) -> None:
        """
        Add or replace a full metadata entry in the store.

        - If an entry with the same UID exists, it is overwritten.
        - If not, the metadata is added as a new entry.

        :param metadata: The full metadata instance.
        :raises ValueError: If 'document_uid' is missing.
        """
        pass

    @abstractmethod
    def delete_metadata(self, metadata: DocumentMetadata) -> None:
        pass

    @abstractmethod
    def clear(self) -> None:
        """Remove every record in the store (test-only helper)."""
        pass
