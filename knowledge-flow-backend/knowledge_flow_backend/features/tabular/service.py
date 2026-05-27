# Copyright Thales 2026
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

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import timedelta

import duckdb
import pandas as pd
from fred_core import Action, DocumentPermission, KeycloakUser, RebacDisabledResult, Resource, authorize
from fred_core.common import OwnerFilter

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.document_structures import DocumentMetadata
from knowledge_flow_backend.core.stores.content.filesystem_content_store import FileSystemContentStore
from knowledge_flow_backend.features.tabular.artifacts import (
    TabularArtifactV1,
    build_default_query_alias,
    read_tabular_artifact,
)
from knowledge_flow_backend.features.tabular.structures import (
    RawSQLResponse,
    TabularDatasetResponse,
    TabularDatasetSchemaResponse,
    TabularQueryRequest,
)
from knowledge_flow_backend.features.tabular.utils import validate_read_query
from knowledge_flow_backend.features.tag.tag_service import TagService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedDataset:
    """
    Authorized dataset ready to be exposed or mounted in DuckDB.

    Why this exists:
    - The service needs one internal structure carrying the metadata record, the
      stored tabular artifact, and the stable SQL alias at the same time.

    How to use:
    - Build these with `_resolve_authorized_datasets(...)`.
    - Convert them to API payloads or mount them in DuckDB for one query.
    """

    metadata: DocumentMetadata
    artifact: TabularArtifactV1
    query_alias: str


class TabularService:
    """
    Dataset-centric tabular service backed by document metadata and content storage.

    Why this exists:
    - Read-only SQL access must now follow document-level ReBAC rather than
      exposing every ingested table globally.

    How to use:
    - The controller calls `list_datasets`, `describe_dataset`, `read_dataset_frame`,
      and `query_read`.
    - Every method filters datasets through document-level permissions before
      exposing schema or data.
    """

    def __init__(self):
        """
        Wire the shared stores needed by the dataset-centric tabular runtime.

        Why this exists:
        - Tabular listing and querying now depend on metadata, ReBAC, content
          storage, and runtime query configuration at the same time.

        How to use:
        - Instantiate once inside `TabularController`.
        """

        context = ApplicationContext.get_instance()
        self.metadata_store = context.get_metadata_store()
        self.content_store = context.get_content_store()
        self.rebac = context.get_rebac_engine()
        self.tag_service: TagService | None = None
        self.tabular_config = context.get_config().storage.tabular_store

    @authorize(action=Action.READ, resource=Resource.DOCUMENTS)
    async def list_datasets(
        self,
        user: KeycloakUser,
        *,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> list[TabularDatasetResponse]:
        """
        List every tabular dataset the current user is allowed to read.

        Why this exists:
        - The SQL agent and the API both need one document-scoped inventory of
          queryable datasets.
        - Team/personal area scoping must stay aligned with the rest of the
          corpus features, not only with raw document readability.

        How to use:
        - Call from `GET /tabular/datasets`.
        - Optionally pass `owner_filter`, `team_id`, and
          `document_library_tags_ids` to stay inside one active area/library
          scope.
        """

        datasets = await self._resolve_authorized_datasets(
            user,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )
        return [self._dataset_to_response(dataset) for dataset in datasets]

    @authorize(action=Action.READ, resource=Resource.DOCUMENTS)
    async def describe_dataset(
        self,
        user: KeycloakUser,
        document_uid: str,
        *,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> TabularDatasetSchemaResponse:
        """
        Return the schema of one authorized dataset.

        Why this exists:
        - Dataset schema exposure must follow the same document-level access
          checks as query execution.
        - Team/personal scope selection must hide datasets outside the active
          area even when the user can read them elsewhere.

        How to use:
        - Call from `GET /tabular/datasets/{document_uid}/schema`.
        """

        dataset = await self._get_dataset_or_raise(
            user=user,
            document_uid=document_uid,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )
        return TabularDatasetSchemaResponse(
            document_uid=dataset.metadata.document_uid,
            document_name=dataset.metadata.document_name,
            query_alias=dataset.query_alias,
            columns=dataset.artifact.columns,
            row_count=dataset.artifact.row_count,
            source_tag=dataset.metadata.source_tag,
            generated_at=dataset.artifact.generated_at,
        )

    @authorize(action=Action.READ, resource=Resource.DOCUMENTS)
    async def read_dataset_frame(
        self,
        user: KeycloakUser,
        document_uid: str,
        *,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> pd.DataFrame:
        """
        Load one authorized dataset into a pandas DataFrame.

        Why this exists:
        - The statistic feature still operates on in-memory pandas DataFrames.
        - Reusing the dataset-centric resolver keeps those reads aligned with
          the same document-level permissions as SQL queries.
        - Team/personal scoping must also apply to these DataFrame reads.

        How to use:
        - Pass the current user and the dataset `document_uid` selected from
          `list_datasets`.
        - Optionally pass `owner_filter`, `team_id`, and selected library tag
          ids when the caller is bound to one active area.
        """

        dataset = await self._get_dataset_or_raise(
            user=user,
            document_uid=document_uid,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )
        return self._load_dataset_frame(dataset=dataset)

    @authorize(action=Action.READ, resource=Resource.DOCUMENTS)
    async def read_dataset_preview_frame(
        self,
        user: KeycloakUser,
        document_uid: str,
        *,
        max_rows: int = 200,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> pd.DataFrame:
        """
        Load only the first rows of one authorized dataset into pandas.

        Why this exists:
        - Document previews should reuse the indexed Parquet artifact instead
          of persisting a duplicate `table.csv` copy in content storage.
        - Preview endpoints need a bounded read that stays cheap for large
          datasets.

        How to use:
        - Pass the current user and target dataset uid.
        - Tune `max_rows` when a caller needs a smaller or larger tabular
          preview window.
        """
        if max_rows < 1:
            raise ValueError("max_rows must be greater than 0")

        dataset = await self._get_dataset_or_raise(
            user=user,
            document_uid=document_uid,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )
        return self._load_dataset_frame(dataset=dataset, max_rows=max_rows)

    @authorize(action=Action.READ, resource=Resource.DOCUMENTS)
    async def query_read(
        self,
        user: KeycloakUser,
        *,
        request: TabularQueryRequest,
    ) -> RawSQLResponse:
        """
        Execute one read-only SQL query against authorized datasets only.

        Why this exists:
        - The runtime must mount only the caller's readable datasets in a fresh
          DuckDB session and keep every query read-only.
        - Team/personal area scoping must flow through SQL execution exactly as
          it does for corpus retrieval.

        How to use:
        - Provide a validated `TabularQueryRequest`.
        - Set `owner_filter`, `team_id`, and `document_library_tags_ids` in the
          request when the caller is bound to one active area/library scope.
        """

        available_datasets = await self._resolve_authorized_datasets(
            user,
            document_library_tags_ids=request.document_library_tags_ids,
            owner_filter=request.owner_filter,
            team_id=request.team_id,
        )
        selected_datasets = await self._select_query_datasets(
            user=user,
            request=request,
            available_datasets=available_datasets,
        )
        if not selected_datasets:
            raise ValueError("No authorized tabular datasets are available for this query")

        allowed_aliases = {dataset.query_alias for dataset in selected_datasets}
        sql_query = validate_read_query(request.sql_text, allowed_relations=allowed_aliases)
        tabular_config = self.tabular_config

        started_at = time.perf_counter()
        sql_hash = hashlib.sha256(sql_query.encode("utf-8")).hexdigest()
        effective_max_rows = min(
            request.max_rows or tabular_config.query.default_max_rows,
            tabular_config.query.max_rows,
        )

        connection = duckdb.connect(database=":memory:")
        try:
            await self._mount_datasets(connection=connection, datasets=selected_datasets)
            limited_query = f"SELECT * FROM ({sql_query}) AS fred_result LIMIT {effective_max_rows}"
            rows_df = connection.execute(limited_query).df()
            rows = rows_df.to_dict(orient="records")
        finally:
            connection.close()

        duration_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "[TABULAR] user=%s datasets=%s aliases=%s sql_sha256=%s rows=%s duration_ms=%.2f",
            user.uid,
            [dataset.metadata.document_uid for dataset in selected_datasets],
            [dataset.query_alias for dataset in selected_datasets],
            sql_hash,
            len(rows),
            duration_ms,
        )

        return RawSQLResponse(
            sql_query=sql_query,
            rows=rows,
            error=None,
            dataset_uids=[dataset.metadata.document_uid for dataset in selected_datasets],
            query_aliases=[dataset.query_alias for dataset in selected_datasets],
        )

    async def _resolve_authorized_datasets(
        self,
        user: KeycloakUser,
        *,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> list[ResolvedDataset]:
        """
        Resolve every readable document that has a tabular artifact.

        Why this exists:
        - Dataset listing, schema lookup, and query execution all need the same
          filtered, alias-stable view of authorized tabular documents.
        - Active team/personal/library scope must be applied before aliases are
          exposed or mounted in DuckDB.

        How to use:
        - Call once per request and reuse the resulting list for downstream
          selection or API formatting.
        - When ReBAC is enabled, the service resolves only the authorized
          document uids instead of scanning the whole metadata catalog.
        """

        authorized_document_ref = await self.rebac.lookup_user_resources(user, DocumentPermission.READ)
        scoped_tag_ids = await self._resolve_scope_tag_ids(
            user,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )

        if isinstance(authorized_document_ref, RebacDisabledResult):
            visible_documents = await self.metadata_store.get_all_metadata({})
        else:
            authorized_ids = [document.id for document in authorized_document_ref]
            if not authorized_ids:
                return []
            visible_documents = await self.metadata_store.get_metadata_by_uids(authorized_ids)

        resolved_datasets: list[ResolvedDataset] = []
        used_aliases: set[str] = set()
        for metadata in visible_documents:
            if scoped_tag_ids is not None and not (set(metadata.tags.tag_ids or []) & scoped_tag_ids):
                continue
            artifact = read_tabular_artifact(metadata)
            if artifact is None:
                continue

            base_alias = build_default_query_alias(metadata.document_uid, metadata.document_name)
            query_alias = base_alias
            suffix = 2
            while query_alias in used_aliases:
                query_alias = f"{base_alias}_{suffix}"
                suffix += 1
            used_aliases.add(query_alias)

            resolved_datasets.append(
                ResolvedDataset(
                    metadata=metadata,
                    artifact=artifact,
                    query_alias=query_alias,
                )
            )

        return resolved_datasets

    async def _get_dataset_or_raise(
        self,
        *,
        user: KeycloakUser,
        document_uid: str,
        document_library_tags_ids: list[str] | None = None,
        owner_filter: OwnerFilter | None = None,
        team_id: str | None = None,
    ) -> ResolvedDataset:
        """
        Return one authorized dataset or raise the appropriate access/not-found error.

        Why this exists:
        - Schema lookup and explicit query scoping need one clear path that does
          not leak unauthorized datasets.
        - Active team/personal/library scope must be enforced consistently for
          direct dataset access.

        How to use:
        - Pass the current user and target document uid.
        """

        datasets = await self._resolve_authorized_datasets(
            user,
            document_library_tags_ids=document_library_tags_ids,
            owner_filter=owner_filter,
            team_id=team_id,
        )
        dataset_by_uid = {dataset.metadata.document_uid: dataset for dataset in datasets}
        if document_uid in dataset_by_uid:
            return dataset_by_uid[document_uid]

        if not await self.rebac.has_user_permission(user, DocumentPermission.READ, document_uid):
            raise PermissionError(f"Not authorized to read dataset '{document_uid}'")
        raise FileNotFoundError(f"Tabular dataset '{document_uid}' was not found")

    async def _select_query_datasets(
        self,
        *,
        user: KeycloakUser,
        request: TabularQueryRequest,
        available_datasets: list[ResolvedDataset],
    ) -> list[ResolvedDataset]:
        """
        Resolve the dataset subset requested for one SQL query.

        Why this exists:
        - Query callers may scope execution to a subset of readable datasets.
        - Explicitly requested datasets must return `403` when the user is not
          allowed to read them.

        How to use:
        - Pass the full readable dataset list from `_resolve_authorized_datasets`.
        """

        if not request.dataset_uids:
            return available_datasets

        requested_uids = list(dict.fromkeys(request.dataset_uids))
        dataset_by_uid = {dataset.metadata.document_uid: dataset for dataset in available_datasets}

        missing_uids = [document_uid for document_uid in requested_uids if document_uid not in dataset_by_uid]
        if missing_uids:
            permission_checks = await asyncio.gather(*(self.rebac.has_user_permission(user, DocumentPermission.READ, document_uid) for document_uid in missing_uids))
            forbidden_uids = [document_uid for document_uid, allowed in zip(missing_uids, permission_checks) if not allowed]
            if forbidden_uids:
                logger.warning("[TABULAR] user=%s requested forbidden datasets=%s", user.uid, forbidden_uids)
                raise PermissionError(f"Not authorized to read datasets: {', '.join(forbidden_uids)}")
            raise FileNotFoundError(f"Requested tabular datasets were not found: {', '.join(missing_uids)}")

        return [dataset_by_uid[document_uid] for document_uid in requested_uids]

    async def _resolve_scope_tag_ids(
        self,
        user: KeycloakUser,
        *,
        document_library_tags_ids: list[str] | None,
        owner_filter: OwnerFilter | None,
        team_id: str | None,
    ) -> set[str] | None:
        """
        Resolve the active tabular scope to one authorized tag-id set.

        Why this exists:
        - Tabular access must follow the same library and team/personal scope
          rules as vector search.

        How to use:
        - Call before filtering document metadata.
        - Returns `None` when no extra tabular scope is active, so callers can
          keep the simpler document-level ReBAC behavior.
        """

        if owner_filter is None and not document_library_tags_ids:
            return None

        authorized_tag_ids = await self._get_tag_service().list_authorized_tags_ids(
            user,
            owner_filter,
            team_id,
        )
        if document_library_tags_ids:
            return set(document_library_tags_ids) & authorized_tag_ids
        return authorized_tag_ids

    def _get_tag_service(self) -> TagService:
        """
        Return the tag service only when tabular scope resolution needs it.

        Why this exists:
        - Default tabular reads should still work in lightweight/offline test
          environments that do not bootstrap the full tag backend.

        How to use:
        - Call from helpers that resolve `owner_filter`, `team_id`, or library
          tag ids.
        """

        if self.tag_service is None:
            self.tag_service = TagService()
        return self.tag_service

    async def _mount_datasets(
        self,
        *,
        connection: duckdb.DuckDBPyConnection,
        datasets: list[ResolvedDataset],
    ) -> None:
        """
        Mount authorized Parquet datasets as temporary DuckDB views.

        Why this exists:
        - DuckDB is not the security boundary; only the views registered in the
          session are visible to the query.

        How to use:
        - Call on a fresh in-memory connection before executing one SQL query.
        """

        dataset_locations: list[tuple[ResolvedDataset, str]] = []
        for dataset in datasets:
            location = self._resolve_dataset_location(dataset.artifact.object_key)
            dataset_locations.append((dataset, location))

        if any(self._requires_httpfs(location) for _, location in dataset_locations):
            self._ensure_httpfs_ready(connection)

        for dataset, location in dataset_locations:
            connection.from_parquet(location).create_view(dataset.query_alias)

    def _resolve_dataset_location(self, object_key: str) -> str:
        """
        Resolve one content-store object to a DuckDB-readable location.

        Why this exists:
        - Remote object stores use backend-internal presigned URLs through
          DuckDB `httpfs`.
        - The local filesystem content store used in local development and
          offline tests should expose a direct file path instead of emulating a
          remote download flow.

        How to use:
        - Call while mounting the per-query DuckDB session.
        """

        tabular_config = self.tabular_config
        try:
            return self.content_store.get_presigned_url_internal(
                object_key,
                expires=timedelta(seconds=tabular_config.query.internal_presigned_ttl_seconds),
            )
        except NotImplementedError:
            return self._resolve_local_dataset_path(object_key)

    def _resolve_local_dataset_path(self, object_key: str) -> str:
        """
        Resolve one dataset artifact to its real local filesystem path.

        Why this exists:
        - The local filesystem content store does not expose presigned URLs.
        - Local development and test setups should still query tabular
          artifacts directly from disk.

        How to use:
        - Called only when the content store does not support presigned URLs.
        """

        if isinstance(self.content_store, FileSystemContentStore):
            local_path = self.content_store.object_root / object_key.lstrip("/")
            if not local_path.exists():
                raise FileNotFoundError(f"Tabular artifact '{object_key}' was not found in local content storage")
            return str(local_path)

        raise RuntimeError("Tabular querying requires presigned URLs or a local filesystem content store")

    def _ensure_httpfs_ready(self, connection: duckdb.DuckDBPyConnection) -> None:
        """
        Ensure DuckDB `httpfs` is available for remote Parquet access.

        Why this exists:
        - The S3-compatible runtime is intentionally `httpfs`-based.
        - Kubernetes/offline deployments preinstall the extension in the image,
          while connected environments may still need one best-effort
          `INSTALL httpfs` before the query can proceed.

        How to use:
        - Call before executing `from_parquet(...)` on HTTP(S) locations.
        """

        try:
            connection.execute("LOAD httpfs")
            return
        except Exception as load_exc:  # noqa: BLE001
            logger.info(
                "[TABULAR] DuckDB httpfs not yet available, trying INSTALL+LOAD: %s",
                load_exc,
            )
        try:
            connection.execute("INSTALL httpfs")
            connection.execute("LOAD httpfs")
        except Exception as install_exc:  # noqa: BLE001
            raise RuntimeError(
                "DuckDB httpfs is required for remote tabular dataset access. Preinstall it in the runtime image for offline/containerized deployments, or allow DuckDB to install extensions at startup in connected environments."
            ) from install_exc

    def _requires_httpfs(self, location: str) -> bool:
        """
        Return whether one dataset location points to an HTTP(S) resource.

        Why this exists:
        - The tabular runtime needs one small predicate to decide when DuckDB
          `httpfs` must be loaded.

        How to use:
        - Pass the location returned by `_resolve_dataset_location(...)`.
        """

        return location.startswith(("http://", "https://"))

    def _dataset_to_response(self, dataset: ResolvedDataset) -> TabularDatasetResponse:
        """
        Convert one resolved dataset into the REST response model.

        Why this exists:
        - The list endpoint should expose one stable, serializable view of
          authorized datasets without leaking the internal content-store key.

        How to use:
        - Use for `GET /tabular/datasets`.
        """

        return TabularDatasetResponse(
            document_uid=dataset.metadata.document_uid,
            document_name=dataset.metadata.document_name,
            query_alias=dataset.query_alias,
            row_count=dataset.artifact.row_count,
            columns=dataset.artifact.columns,
            tag_ids=list(dataset.metadata.tags.tag_ids or []),
            tag_names=list(dataset.metadata.tags.tag_names or []),
            source_tag=dataset.metadata.source_tag,
            generated_at=dataset.artifact.generated_at,
        )

    def _load_dataset_frame(
        self,
        *,
        dataset: ResolvedDataset,
        max_rows: int | None = None,
    ) -> pd.DataFrame:
        """
        Read one dataset artifact from Parquet into a pandas DataFrame.

        Why this exists:
        - Full dataset reads and preview reads share the same object-location
          resolution and DuckDB/httpfs setup.
        - Keeping that logic in one helper avoids preview-specific drift.

        How to use:
        - Pass a resolved dataset from `_get_dataset_or_raise(...)`.
        - Optionally set `max_rows` to limit the returned preview size.

        Example:
        - `frame = self._load_dataset_frame(dataset=dataset, max_rows=200)`
        """
        connection = duckdb.connect(database=":memory:")
        try:
            location = self._resolve_dataset_location(dataset.artifact.object_key)
            if self._requires_httpfs(location):
                self._ensure_httpfs_ready(connection)

            relation = connection.from_parquet(location)
            if max_rows is not None:
                relation = relation.limit(max_rows)
            return relation.df()
        finally:
            connection.close()
