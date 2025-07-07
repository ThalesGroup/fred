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

from abc import ABC, abstractmethod


class BaseMetadataStore(ABC):
    @abstractmethod
    def get_all_metadata(self, filters: dict) -> list:
        pass

    @abstractmethod
    def get_metadata_by_uid(self, document_uid: str) -> dict:
        pass

    @abstractmethod
    def update_metadata_field(self, document_uid: str, field: str, value) -> dict:
        pass

    @abstractmethod
    def save_metadata(self, metadata: dict) -> None:
        """
        Add or replace a full metadata entry in the store.

        - If an entry with the same UID exists, it is overwritten.
        - If not, the metadata is added as a new entry.

        :param metadata: The full metadata dictionary.
        :raises ValueError: If 'document_uid' is missing.
        """
        pass

    @abstractmethod
    def delete_metadata(self, metadata: dict) -> None:
        pass
