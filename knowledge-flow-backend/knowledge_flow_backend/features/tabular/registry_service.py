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

from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path

from fred_core import SQLTableStore, StoreInfo

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.document_structures import DocumentMetadata, ProcessingStage, ProcessingStatus
from knowledge_flow_backend.common.utils import sanitize_sql_name
from knowledge_flow_backend.core.stores.metadata.base_metadata_store import BaseMetadataStore
from knowledge_flow_backend.core.stores.tabular_dataset_registry import (
    BaseTabularDatasetRegistryStore,
    TabularDatasetRecord,
)

logger = logging.getLogger(__name__)

_MAX_TABLE_NAME_LEN = 63


def _clamp_sql_name(name: str, max_len: int = _MAX_TABLE_NAME_LEN) -> str:
    return name[:max_len].rstrip("_")


def build_physical_table_name(document_uid: str) -> str:
    return _clamp_sql_name(f"tbl_{sanitize_sql_name(document_uid)}")


def build_query_alias(display_name: str, document_uid: str) -> str:
    base_name = sanitize_sql_name(Path(display_name).stem) or "dataset"
    suffix = sanitize_sql_name(document_uid)[:8] or "dataset"
    max_base_len = max(1, _MAX_TABLE_NAME_LEN - len(suffix) - 2)
    base_name = base_name[:max_base_len].rstrip("_") or "dataset"
    return f"{base_name}__{suffix}"


class TabularRegistryService:
    def __init__(
        self,
        registry_store: BaseTabularDatasetRegistryStore | None = None,
        stores_info: dict[str, StoreInfo] | None = None,
        metadata_store: BaseMetadataStore | None = None,
    ) -> None:
        context = ApplicationContext.get_instance()
        self.registry_store = registry_store or context.get_tabular_dataset_registry_store()
        self.stores_info = stores_info or context.get_tabular_stores()
        self.metadata_store = metadata_store or context.get_metadata_store()
        self.context = context

    @staticmethod
    def _display_name_for_metadata(metadata: DocumentMetadata) -> str:
        return metadata.identity.canonical_name or metadata.identity.document_name

    def _get_store(self, db_name: str) -> SQLTableStore:
        try:
            return self.stores_info[db_name].store
        except KeyError as exc:
            raise ValueError(f"Unknown tabular database '{db_name}'") from exc

    def _default_writable_store(self) -> tuple[str, SQLTableStore]:
        return self.context.get_csv_input_store_info()

    def _count_rows(self, store: SQLTableStore, table_name: str) -> int | None:
        try:
            df = store.execute_sql_query(f'SELECT COUNT(*) AS n FROM "{table_name}"')
        except Exception:
            logger.warning("[TABULAR_REGISTRY] Failed to count rows for table '%s'", table_name, exc_info=True)
            return None
        if df.empty or "n" not in df.columns:
            return None
        return int(df["n"].iloc[0])

    async def get_by_document_uid(self, document_uid: str) -> TabularDatasetRecord | None:
        return await self.registry_store.get_by_document_uid(document_uid)

    async def get_by_query_alias(self, query_alias: str) -> TabularDatasetRecord | None:
        return await self.registry_store.get_by_query_alias(query_alias)

    async def list_by_document_uids(self, document_uids: list[str]) -> list[TabularDatasetRecord]:
        return await self.registry_store.list_by_document_uids(document_uids)

    async def list_all(self) -> list[TabularDatasetRecord]:
        return await self.registry_store.list_all()

    async def upsert_for_metadata(
        self,
        metadata: DocumentMetadata,
        *,
        db_name: str | None = None,
        row_count: int | None = None,
    ) -> TabularDatasetRecord:
        now = datetime.now(timezone.utc)
        existing = await self.registry_store.get_by_document_uid(metadata.document_uid)
        display_name = self._display_name_for_metadata(metadata)
        chosen_db_name = db_name or (existing.db_name if existing else self._default_writable_store()[0])
        physical_table_name = existing.physical_table_name if existing else build_physical_table_name(metadata.document_uid)
        query_alias = existing.query_alias if existing else build_query_alias(display_name, metadata.document_uid)

        dataset = TabularDatasetRecord(
            document_uid=metadata.document_uid,
            db_name=chosen_db_name,
            physical_table_name=physical_table_name,
            query_alias=query_alias,
            display_name=display_name,
            row_count=row_count if row_count is not None else existing.row_count if existing else None,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        return await self.registry_store.upsert(dataset)

    async def refresh_row_count(self, document_uid: str) -> TabularDatasetRecord | None:
        dataset = await self.registry_store.get_by_document_uid(document_uid)
        if dataset is None:
            return None
        store = self._get_store(dataset.db_name)
        if dataset.physical_table_name not in set(store.list_tables()):
            return None
        updated = dataset.model_copy(update={"row_count": self._count_rows(store, dataset.physical_table_name), "updated_at": datetime.now(timezone.utc)})
        return await self.registry_store.upsert(updated)

    async def delete_registered_dataset(self, document_uid: str) -> None:
        await self.registry_store.delete_by_document_uid(document_uid)

    async def drop_dataset_table_for_metadata(self, metadata: DocumentMetadata) -> bool:
        dataset = await self.ensure_registered_for_metadata(metadata)
        if dataset is None:
            return False
        self._get_store(dataset.db_name).delete_table(dataset.physical_table_name)
        await self.registry_store.delete_by_document_uid(metadata.document_uid)
        return True

    async def ensure_registered_for_metadata(self, metadata: DocumentMetadata) -> TabularDatasetRecord | None:
        existing = await self.registry_store.get_by_document_uid(metadata.document_uid)
        if existing is not None:
            return existing

        if metadata.processing.stages.get(ProcessingStage.SQL_INDEXED) != ProcessingStatus.DONE:
            return None

        db_name, store = self._default_writable_store()
        physical_table_name = build_physical_table_name(metadata.document_uid)
        current_tables = set(store.list_tables())

        if physical_table_name in current_tables:
            return await self.upsert_for_metadata(
                metadata,
                db_name=db_name,
                row_count=self._count_rows(store, physical_table_name),
            )

        legacy_table_name = sanitize_sql_name(Path(metadata.document_name).stem)
        if not legacy_table_name or legacy_table_name not in current_tables:
            return None

        all_docs = await self.metadata_store.get_all_metadata({})
        same_legacy_name = [
            doc
            for doc in all_docs
            if doc.processing.stages.get(ProcessingStage.SQL_INDEXED) == ProcessingStatus.DONE
            and sanitize_sql_name(Path(doc.document_name).stem) == legacy_table_name
        ]
        if len(same_legacy_name) != 1 or same_legacy_name[0].document_uid != metadata.document_uid:
            logger.warning(
                "[TABULAR_REGISTRY] Refusing ambiguous legacy backfill for document_uid=%s legacy_table=%s matches=%d",
                metadata.document_uid,
                legacy_table_name,
                len(same_legacy_name),
            )
            return None

        try:
            store.execute_update_query(f'ALTER TABLE "{legacy_table_name}" RENAME TO "{physical_table_name}"')
        except Exception:
            logger.warning(
                "[TABULAR_REGISTRY] Failed to rename legacy table '%s' -> '%s'",
                legacy_table_name,
                physical_table_name,
                exc_info=True,
            )
            return None

        return await self.upsert_for_metadata(
            metadata,
            db_name=db_name,
            row_count=self._count_rows(store, physical_table_name),
        )
