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

from knowledge_flow_backend.core.stores.tabular_dataset_registry.structures import (
    TabularDatasetRecord,
)


class BaseTabularDatasetRegistryStore(ABC):
    @abstractmethod
    async def get_by_document_uid(self, document_uid: str) -> TabularDatasetRecord | None:
        pass

    @abstractmethod
    async def get_by_query_alias(self, query_alias: str) -> TabularDatasetRecord | None:
        pass

    @abstractmethod
    async def list_by_document_uids(self, document_uids: list[str]) -> list[TabularDatasetRecord]:
        pass

    @abstractmethod
    async def list_all(self) -> list[TabularDatasetRecord]:
        pass

    @abstractmethod
    async def upsert(self, dataset: TabularDatasetRecord) -> TabularDatasetRecord:
        pass

    @abstractmethod
    async def delete_by_document_uid(self, document_uid: str) -> None:
        pass
