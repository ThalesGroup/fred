# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from typing import Any, Dict, List

from fred_core import Action, DocumentPermission, KeycloakUser, OwnerFilter, Resource, authorize
from fred_core.store.structures import StoreInfo

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.document_structures import DocumentMetadata, ProcessingStage, ProcessingStatus
from knowledge_flow_backend.core.stores.tabular_dataset_registry.structures import (
    TabularDatasetRecord,
)
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.tag.tag_service import TagService
from knowledge_flow_backend.features.tabular.query_utils import (
    extract_query_table_references,
    rewrite_query_table_names,
)
from knowledge_flow_backend.features.tabular.registry_service import TabularRegistryService
from knowledge_flow_backend.features.tabular.structures import (
    DTypes,
    GetSchemaResponse,
    ListTablesResponse,
    RawSQLResponse,
    TabularColumnSchema,
    TabularDatasetInfo,
)
from knowledge_flow_backend.features.tabular.utils import check_read_query, check_write_query

logger = logging.getLogger(__name__)


class TabularService:
    def __init__(
        self,
        stores_info: Dict[str, StoreInfo],
        metadata_service: MetadataService | None = None,
        registry_service: TabularRegistryService | None = None,
        tag_service: TagService | None = None,
    ):
        self.stores_info = stores_info
        context = ApplicationContext.get_instance()
        self.metadata_service = metadata_service or MetadataService()
        self.tag_service = tag_service or TagService()
        self.registry_service = registry_service or TabularRegistryService(
            registry_store=context.get_tabular_dataset_registry_store(),
            stores_info=stores_info,
            metadata_store=context.get_metadata_store(),
        )
        self.rebac = context.get_rebac_engine()

    def _check_write_allowed(self, db_name: str) -> None:
        store_info = self.stores_info.get(db_name)
        if store_info is None:
            raise ValueError(f"Unknown database '{db_name}'")
        if store_info.mode != "read_and_write":
            raise PermissionError(f"Write operations are not allowed on database '{db_name}'")

    def _get_store(self, db_name: str):
        try:
            return self.stores_info[db_name].store
        except KeyError as exc:
            raise ValueError(f"Unknown database '{db_name}'") from exc

    def _map_sql_type_to_literal(self, duckdb_type: str) -> DTypes:
        duckdb_type = duckdb_type.lower()
        if any(x in duckdb_type for x in ["varchar", "string", "text"]):
            return "string"
        if "boolean" in duckdb_type:
            return "boolean"
        if any(x in duckdb_type for x in ["timestamp", "date", "time"]):
            return "datetime"
        if any(x in duckdb_type for x in ["double", "real", "float"]):
            return "float"
        if "int" in duckdb_type:
            return "integer"
        return "unknown"

    @staticmethod
    def _dataset_info(dataset: TabularDatasetRecord) -> TabularDatasetInfo:
        return TabularDatasetInfo(
            document_uid=dataset.document_uid,
            dataset_alias=dataset.query_alias,
            display_name=dataset.display_name,
            db_name=dataset.db_name,
            row_count=dataset.row_count,
        )

    async def _resolve_scope_tag_ids(
        self,
        user: KeycloakUser,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> set[str] | None:
        if owner_filter is None and not document_library_tags_ids:
            return None

        authorized_tag_ids = await self.tag_service.list_authorized_tags_ids(user, owner_filter, team_id)
        if document_library_tags_ids:
            authorized_tag_ids = set(document_library_tags_ids) & authorized_tag_ids
        return authorized_tag_ids

    @staticmethod
    def _document_matches_scope(metadata: DocumentMetadata, scope_tag_ids: set[str] | None) -> bool:
        if scope_tag_ids is None:
            return True
        doc_tag_ids = set((metadata.tags.tag_ids if metadata.tags else []) or [])
        return bool(doc_tag_ids & scope_tag_ids)

    async def _visible_sql_documents(
        self,
        user: KeycloakUser,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> list[DocumentMetadata]:
        docs = await self.metadata_service.get_documents_metadata(user, {})
        scope_tag_ids = await self._resolve_scope_tag_ids(
            user,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )
        return [
            doc
            for doc in docs
            if doc.processing.stages.get(ProcessingStage.SQL_INDEXED) == ProcessingStatus.DONE
            and self._document_matches_scope(doc, scope_tag_ids)
        ]

    async def _visible_datasets(
        self,
        user: KeycloakUser,
        db_name: str | None = None,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> list[TabularDatasetRecord]:
        docs = await self._visible_sql_documents(
            user,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )
        datasets: list[TabularDatasetRecord] = []
        for metadata in docs:
            dataset = await self.registry_service.ensure_registered_for_metadata(metadata)
            if dataset is None:
                continue
            if db_name and dataset.db_name != db_name:
                continue
            datasets.append(dataset)
        datasets.sort(key=lambda dataset: dataset.query_alias)
        return datasets

    async def _visible_alias_map(
        self,
        user: KeycloakUser,
        db_name: str,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> dict[str, TabularDatasetRecord]:
        datasets = await self._visible_datasets(
            user,
            db_name,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )
        return {dataset.query_alias: dataset for dataset in datasets}

    async def _all_physical_table_names(self) -> set[str]:
        datasets = await self.registry_service.list_all()
        return {dataset.physical_table_name for dataset in datasets}

    async def _resolve_dataset_for_user(
        self,
        user: KeycloakUser,
        db_name: str,
        query_alias: str,
        permission: DocumentPermission,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> TabularDatasetRecord:
        alias_map = await self._visible_alias_map(
            user,
            db_name,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )
        dataset = alias_map.get(query_alias)
        if dataset is None:
            raise ValueError(f"Invalid or unauthorized table name: {query_alias}")
        await self.rebac.check_user_permission_or_raise(user, permission, dataset.document_uid)
        return dataset

    @staticmethod
    def _reject_unknown_or_physical_tables(
        refs,
        alias_map: dict[str, TabularDatasetRecord],
        physical_names: set[str],
    ) -> None:
        if refs.qualified_tables:
            raise ValueError("Schema-qualified table names are not allowed")

        physical_refs = refs.all_tables & physical_names
        if physical_refs:
            raise ValueError("Physical table names are not allowed in tabular queries")

        unknown = refs.all_tables - set(alias_map.keys())
        if unknown:
            invalid = ", ".join(sorted(unknown))
            raise ValueError(f"Invalid or unauthorized table name: {invalid}")

    def _schema_response(self, dataset: TabularDatasetRecord, schema: list[tuple[str, str]]) -> GetSchemaResponse:
        columns = [TabularColumnSchema(name=col, dtype=self._map_sql_type_to_literal(dtype)) for col, dtype in schema]
        return GetSchemaResponse(
            db_name=dataset.db_name,
            table_name=dataset.query_alias,
            document_uid=dataset.document_uid,
            display_name=dataset.display_name,
            columns=columns,
            row_count=dataset.row_count,
        )

    @authorize(action=Action.READ, resource=Resource.TABLES_DATABASES)
    async def list_databases(
        self,
        user: KeycloakUser,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> List[str]:
        datasets = await self._visible_datasets(
            user,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )
        return sorted({dataset.db_name for dataset in datasets})

    @authorize(action=Action.READ, resource=Resource.TABLES)
    async def describe_table(
        self,
        user: KeycloakUser,
        db_name: str,
        table_name: str,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> GetSchemaResponse:
        dataset = await self._resolve_dataset_for_user(
            user,
            db_name,
            table_name,
            DocumentPermission.READ,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )
        store = self._get_store(db_name)
        schema = store.get_table_schema(dataset.physical_table_name)
        refreshed = await self.registry_service.refresh_row_count(dataset.document_uid) or dataset
        return self._schema_response(refreshed, schema)

    @authorize(action=Action.READ, resource=Resource.TABLES)
    async def list_tables(
        self,
        user: KeycloakUser,
        db_name: str,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> ListTablesResponse:
        datasets = await self._visible_datasets(
            user,
            db_name,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )
        return ListTablesResponse(
            db_name=db_name,
            tables=[dataset.query_alias for dataset in datasets],
            datasets=[self._dataset_info(dataset) for dataset in datasets],
        )

    @authorize(action=Action.READ, resource=Resource.TABLES)
    async def list_tables_with_schema(
        self,
        user: KeycloakUser,
        db_name: str,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> List[GetSchemaResponse]:
        store = self._get_store(db_name)
        responses: list[GetSchemaResponse] = []
        for dataset in await self._visible_datasets(
            user,
            db_name,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        ):
            try:
                schema_info = store.get_table_schema(dataset.physical_table_name)
                refreshed = await self.registry_service.refresh_row_count(dataset.document_uid) or dataset
                responses.append(self._schema_response(refreshed, schema_info))
            except Exception as e:
                logger.warning("[%s] Failed to load schema for alias=%s: %s", db_name, dataset.query_alias, e)
        return responses

    async def get_context(
        self,
        user: KeycloakUser,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> Dict[str, Any]:
        context: Dict[str, list[dict[str, Any]]] = {}
        for dataset in await self._visible_datasets(
            user,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        ):
            try:
                schema = await self.describe_table(
                    user,
                    dataset.db_name,
                    dataset.query_alias,
                    document_library_tags_ids=document_library_tags_ids,
                    owner_filter=owner_filter,
                    team_id=team_id,
                )
            except Exception as e:
                logger.warning("Failed to get context for dataset alias=%s: %s", dataset.query_alias, e)
                continue
            context.setdefault(dataset.db_name, []).append(
                {
                    "table_name": schema.table_name,
                    "display_name": schema.display_name,
                    "document_uid": schema.document_uid,
                    "columns": [{"name": col.name, "dtype": col.dtype} for col in schema.columns],
                    "row_count": schema.row_count,
                }
            )
        return context

    @authorize(action=Action.READ, resource=Resource.TABLES)
    async def query_read(
        self,
        user: KeycloakUser,
        db_name: str,
        query: str,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> RawSQLResponse:
        sql = query.strip()
        if not sql:
            raise ValueError("Empty SQL string provided")
        check_read_query(sql.lower())

        alias_map = await self._visible_alias_map(
            user,
            db_name,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )
        refs = extract_query_table_references(sql)
        self._reject_unknown_or_physical_tables(
            refs,
            alias_map,
            await self._all_physical_table_names(),
        )

        mapping = {name: alias_map[name].physical_table_name for name in refs.all_tables}
        store = self._get_store(db_name)
        rewritten_sql = rewrite_query_table_names(sql, mapping) if mapping else sql
        df = store.execute_sql_query(rewritten_sql)

        return RawSQLResponse(
            db_name=db_name,
            sql_query=query,
            rows=df.to_dict(orient="records"),
            error=None,
        )

    @authorize(action=Action.UPDATE, resource=Resource.TABLES)
    @authorize(action=Action.CREATE, resource=Resource.TABLES)
    @authorize(action=Action.DELETE, resource=Resource.TABLES)
    async def query_write(
        self,
        user: KeycloakUser,
        db_name: str,
        query: str,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> RawSQLResponse:
        sql = query.strip()
        if not sql:
            raise ValueError("Empty SQL string provided")

        self._check_write_allowed(db_name)
        check_write_query(sql)

        refs = extract_query_table_references(sql)
        if not refs.write_targets:
            raise ValueError("Write queries must target at least one registered dataset")

        alias_map = await self._visible_alias_map(
            user,
            db_name,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )
        self._reject_unknown_or_physical_tables(
            refs,
            alias_map,
            await self._all_physical_table_names(),
        )

        for target_alias in refs.write_targets:
            await self.rebac.check_user_permission_or_raise(user, DocumentPermission.UPDATE, alias_map[target_alias].document_uid)

        for source_alias in refs.read_sources - refs.write_targets:
            await self.rebac.check_user_permission_or_raise(user, DocumentPermission.READ, alias_map[source_alias].document_uid)

        mapping = {name: alias_map[name].physical_table_name for name in refs.all_tables}
        rewritten_sql = rewrite_query_table_names(sql, mapping)

        store = self._get_store(db_name)
        store.execute_update_query(rewritten_sql)

        for target_alias in refs.write_targets:
            await self.registry_service.refresh_row_count(alias_map[target_alias].document_uid)

        return RawSQLResponse(db_name=db_name, sql_query=query, rows=[], error=None)

    @authorize(action=Action.DELETE, resource=Resource.TABLES)
    async def delete_table(
        self,
        user: KeycloakUser,
        db_name: str,
        table_name: str,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> None:
        self._check_write_allowed(db_name)
        dataset = await self._resolve_dataset_for_user(
            user,
            db_name,
            table_name,
            DocumentPermission.DELETE,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )
        store = self._get_store(db_name)
        store.delete_table(dataset.physical_table_name)
        await self.registry_service.delete_registered_dataset(dataset.document_uid)
        logger.info("Table alias '%s' deleted from database '%s'", table_name, db_name)
