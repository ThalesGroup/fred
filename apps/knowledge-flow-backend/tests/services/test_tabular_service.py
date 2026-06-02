from __future__ import annotations

import resource
from pathlib import Path
from types import SimpleNamespace

import pytest
from fred_core import KeycloakUser
from fred_core.common import OwnerFilter

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.document_structures import (
    DocumentMetadata,
    FileInfo,
    FileType,
    Identity,
    ProcessingStage,
    ProcessingStatus,
    SourceInfo,
    SourceType,
    Tagging,
)
from knowledge_flow_backend.core.processors.output.tabular_processor.tabular_processor import TabularProcessor
from knowledge_flow_backend.core.stores.metadata.base_metadata_store import BaseMetadataStore
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.tabular.artifacts import (
    TABULAR_EXTENSION_KEY,
    document_artifact_prefix,
    read_tabular_artifact,
)
from knowledge_flow_backend.features.tabular.service import TabularService
from knowledge_flow_backend.features.tabular.structures import TabularQueryRequest
from knowledge_flow_backend.features.tag.structure import MissingTeamIdError


def _user() -> KeycloakUser:
    return KeycloakUser(
        uid="u-1",
        username="tester",
        email="tester@example.com",
        roles=["admin"],
        groups=["admins"],
    )


def _metadata(
    *,
    document_uid: str,
    file_name: str,
    tag_ids: list[str] | None = None,
    tag_names: list[str] | None = None,
) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name=file_name, document_uid=document_uid, title=file_name),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"),
        file=FileInfo(file_type=FileType.CSV, mime_type="text/csv"),
        tags=Tagging(tag_ids=tag_ids or [], tag_names=tag_names or []),
    )


async def _ingest_csv(
    *,
    tmp_path: Path,
    metadata_store,
    document_uid: str,
    file_name: str,
    content: str,
    tag_ids: list[str] | None = None,
    tag_names: list[str] | None = None,
) -> DocumentMetadata:
    csv_path = tmp_path / file_name
    csv_path.write_text(content, encoding="utf-8")

    processor = TabularProcessor()
    metadata = _metadata(
        document_uid=document_uid,
        file_name=file_name,
        tag_ids=tag_ids,
        tag_names=tag_names,
    )
    processed_metadata = processor.process(str(csv_path), metadata)
    await MetadataService().save_document_metadata(_user(), processed_metadata)
    return processed_metadata


class _FakeRebac:
    def __init__(self, readable_document_uids: set[str]):
        self.readable_document_uids = readable_document_uids

    async def lookup_user_resources(self, user, permission):
        del user, permission
        return [SimpleNamespace(id=document_uid) for document_uid in sorted(self.readable_document_uids)]

    async def has_user_permission(self, user, permission, resource_id):
        del user, permission
        return resource_id in self.readable_document_uids


class _FakeTagService:
    """
    Minimal tag service stub used to emulate team/personal tabular scope.

    Why this exists:
    - Tabular tests need deterministic scope resolution without booting full tag
      ReBAC fixtures.

    How to use:
    - Configure readable tags globally and optional team-specific subsets.
    - Assign the instance to `service.tag_service`.
    """

    def __init__(
        self,
        *,
        readable_tag_ids: set[str],
        team_scopes: dict[str, set[str]] | None = None,
        personal_scope: set[str] | None = None,
    ) -> None:
        self.readable_tag_ids = readable_tag_ids
        self.team_scopes = team_scopes or {}
        self.personal_scope = personal_scope or set()

    async def list_authorized_tags_ids(self, user, owner_filter, team_id):
        del user
        if owner_filter is None:
            return set(self.readable_tag_ids)
        if owner_filter == OwnerFilter.TEAM:
            if not team_id:
                raise MissingTeamIdError("team_id is required when owner_filter is 'team'")
            return set(self.team_scopes.get(team_id, set()))
        return set(self.personal_scope)


class _TrackingMetadataStore(BaseMetadataStore):
    """
    Delegate wrapper that records targeted vs full metadata reads.

    Why this exists:
    - Tabular authorization should use one uid-targeted metadata lookup once
      ReBAC has already narrowed the readable document set.

    How to use:
    - Wrap the real metadata store, assign it to `service.metadata_store`, then
      inspect the recorded calls after one request.

    Example:
    - `service.metadata_store = _TrackingMetadataStore(metadata_store)`
    """

    def __init__(self, delegate) -> None:
        self._delegate = delegate
        self.get_all_metadata_calls = 0
        self.get_metadata_by_uids_calls: list[list[str]] = []

    async def get_all_metadata(self, filters: dict, session=None):
        self.get_all_metadata_calls += 1
        return await self._delegate.get_all_metadata(filters, session=session)

    async def get_metadata_by_uids(self, document_uids: list[str], session=None):
        self.get_metadata_by_uids_calls.append(list(document_uids))
        return await self._delegate.get_metadata_by_uids(document_uids, session=session)

    async def get_metadata_by_uid(self, document_uid: str, session=None) -> DocumentMetadata | None:
        return await self._delegate.get_metadata_by_uid(document_uid, session=session)

    async def get_metadata_in_tag(self, tag_id: str, session=None) -> list[DocumentMetadata]:
        return await self._delegate.get_metadata_in_tag(tag_id, session=session)

    async def list_by_source_tag(self, source_tag: str, session=None) -> list[DocumentMetadata]:
        return await self._delegate.list_by_source_tag(source_tag, session=session)

    async def save_metadata(self, metadata: DocumentMetadata, session=None) -> None:
        await self._delegate.save_metadata(metadata, session=session)

    async def delete_metadata(self, document_uid: str, session=None) -> None:
        await self._delegate.delete_metadata(document_uid, session=session)

    async def clear(self, session=None) -> None:
        await self._delegate.clear(session=session)

    def __getattr__(self, name):
        return getattr(self._delegate, name)


class _PresignedLocalContentStore:
    """
    Local content store wrapper that advertises presigned URLs.

    Why this exists:
    - Tests need a remote-style dataset location without requiring a live S3
      service.

    How to use:
    - Wrap the test local content store and override `get_presigned_url(...)`.
    """

    def __init__(self, delegate) -> None:
        self._delegate = delegate
        self.public_presigned_calls = 0
        self.internal_presigned_calls = 0

    def get_presigned_url(self, key, expires=None) -> str:
        del expires
        self.public_presigned_calls += 1
        return f"https://signed.example.invalid/{key}"

    def get_presigned_url_internal(self, key, expires=None) -> str:
        del expires
        self.internal_presigned_calls += 1
        return f"https://internal-signed.example.invalid/{key}"

    def __getattr__(self, name):
        return getattr(self._delegate, name)


@pytest.mark.asyncio
async def test_tabular_processor_stores_one_parquet_artifact_and_replaces_previous_revision(tmp_path, metadata_store):
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    metadata = await _ingest_csv(
        tmp_path=tmp_path,
        metadata_store=metadata_store,
        document_uid="doc-1",
        file_name="sales.csv",
        content="city,amount,created_at\nParis,10,2024-01-01\nLyon,20,2024-01-02\n",
    )
    artifact = read_tabular_artifact(metadata)

    assert artifact is not None
    assert artifact.dataset_uid == "doc-1"
    assert artifact.row_count == 2
    assert [column.name for column in artifact.columns] == ["city", "amount", "created_at"]
    assert metadata.extensions is not None
    assert TABULAR_EXTENSION_KEY in metadata.extensions

    tabular_config = ApplicationContext.get_instance().get_config().storage.tabular_store
    object_prefix = document_artifact_prefix(
        artifacts_prefix=tabular_config.artifacts_prefix,
        document_uid="doc-1",
    )
    stored_objects = content_store.list_objects(object_prefix)
    assert len(stored_objects) == 1
    assert stored_objects[0].key == artifact.object_key

    updated_csv = tmp_path / "sales.csv"
    updated_csv.write_text("city,amount,created_at\nParis,30,2024-02-01\n", encoding="utf-8")

    processor = TabularProcessor()
    updated_metadata = processor.process(str(updated_csv), metadata)
    updated_artifact = read_tabular_artifact(updated_metadata)
    assert updated_artifact is not None
    assert updated_artifact.object_key != artifact.object_key

    stored_objects = content_store.list_objects(object_prefix)
    assert {stored_object.key for stored_object in stored_objects} == {
        artifact.object_key,
        updated_artifact.object_key,
    }

    await MetadataService().save_document_metadata(_user(), updated_metadata)

    stored_objects = content_store.list_objects(object_prefix)
    assert len(stored_objects) == 1
    assert stored_objects[0].key == updated_artifact.object_key


@pytest.mark.asyncio
async def test_tabular_processor_converts_csv_without_pandas_read_csv(tmp_path, monkeypatch):
    import pandas as pd

    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    csv_path = tmp_path / "sales.csv"
    csv_path.write_text("city,amount\nParis,10\nLyon,20\n", encoding="utf-8")

    monkeypatch.setattr(pd, "read_csv", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("pandas path should not be used")))

    processor = TabularProcessor()
    metadata = _metadata(document_uid="doc-no-pandas", file_name="sales.csv")

    processed_metadata = processor.process(str(csv_path), metadata)
    artifact = read_tabular_artifact(processed_metadata)

    assert artifact is not None
    assert artifact.row_count == 2
    assert [column.name for column in artifact.columns] == ["city", "amount"]
    assert [column.dtype for column in artifact.columns] == ["string", "integer"]
    assert processed_metadata.processing.stages[ProcessingStage.PREVIEW_READY] == ProcessingStatus.DONE
    assert processed_metadata.processing.stages[ProcessingStage.SQL_INDEXED] == ProcessingStatus.DONE


@pytest.mark.asyncio
async def test_tabular_processor_keeps_mixed_numeric_and_text_column_as_string(tmp_path):
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    csv_path = tmp_path / "mixed-values.csv"
    with csv_path.open("w", encoding="utf-8") as file_handle:
        file_handle.write("id,label,value\n")
        for index in range(30_000):
            file_handle.write(f"{index},row,{index / 10}\n")
        file_handle.write("30000,tail,xxxxxxxxxxxxxxx\n")

    processor = TabularProcessor()
    metadata = _metadata(document_uid="doc-mixed-types", file_name="mixed-values.csv")

    processed_metadata = processor.process(str(csv_path), metadata)
    artifact = read_tabular_artifact(processed_metadata)

    assert artifact is not None
    assert artifact.row_count == 30_001
    assert [column.name for column in artifact.columns] == ["id", "label", "value"]
    assert [column.dtype for column in artifact.columns] == ["integer", "string", "string"]


@pytest.mark.integration
def test_tabular_processor_limits_python_rss_growth_for_large_csv(tmp_path):
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    row_count = 400_000
    csv_path = tmp_path / "large.csv"
    with csv_path.open("w", encoding="utf-8") as file_handle:
        file_handle.write("city,amount,created_at\n")
        for index in range(row_count):
            file_handle.write(f"city_{index % 100},{index},2024-01-{(index % 28) + 1:02d}\n")

    assert csv_path.stat().st_size > 9 * 1024 * 1024

    processor = TabularProcessor()
    metadata = _metadata(document_uid="doc-large", file_name="large.csv")
    rss_before_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    processed_metadata = processor.process(str(csv_path), metadata)

    rss_after_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_growth_bytes = max(0, rss_after_kb - rss_before_kb) * 1024

    assert processed_metadata.file.row_count == row_count
    assert rss_growth_bytes < 128 * 1024 * 1024


@pytest.mark.asyncio
async def test_tabular_service_lists_context_and_queries_datasets(tmp_path):
    app_context = ApplicationContext.get_instance()
    content_store = app_context.get_content_store()
    metadata_store = app_context.get_metadata_store()
    content_store.clear()

    await _ingest_csv(
        tmp_path=tmp_path,
        metadata_store=metadata_store,
        document_uid="doc-sales",
        file_name="sales.csv",
        content="city,amount\nParis,10\nLyon,20\n",
    )
    await _ingest_csv(
        tmp_path=tmp_path,
        metadata_store=metadata_store,
        document_uid="doc-targets",
        file_name="targets.csv",
        content="city,target\nParis,15\nLyon,25\n",
    )

    service = TabularService()
    datasets = await service.list_datasets(_user())
    assert {dataset.document_uid for dataset in datasets} == {"doc-sales", "doc-targets"}

    dataset_by_uid = {dataset.document_uid: dataset for dataset in datasets}
    sales_alias = dataset_by_uid["doc-sales"].query_alias
    targets_alias = dataset_by_uid["doc-targets"].query_alias

    sales_frame = await service.read_dataset_frame(_user(), "doc-sales")
    assert sales_frame.to_dict(orient="records") == [
        {"city": "Paris", "amount": 10},
        {"city": "Lyon", "amount": 20},
    ]

    query_response = await service.query_read(
        _user(),
        request=TabularQueryRequest(
            sql=(f"SELECT s.city, s.amount, t.target FROM {sales_alias} AS s JOIN {targets_alias} AS t ON s.city = t.city ORDER BY s.amount DESC"),
        ),
    )
    assert query_response.rows == [
        {"city": "Lyon", "amount": 20, "target": 25},
        {"city": "Paris", "amount": 10, "target": 15},
    ]

    count_query = await service.query_read(_user(), request=TabularQueryRequest(sql=f"SELECT COUNT(*) AS total_rows FROM {sales_alias}"))
    assert count_query.rows == [{"total_rows": 2}]

    with pytest.raises(ValueError, match="Only SELECT or WITH statements are allowed"):
        await service.query_read(
            _user(),
            request=TabularQueryRequest(sql=f"DROP TABLE {sales_alias}"),
        )


@pytest.mark.asyncio
async def test_tabular_service_rejects_duckdb_table_functions_outside_authorized_datasets(tmp_path):
    """
    Verify read-only tabular queries cannot bypass dataset scoping with DuckDB functions.

    Why this exists:
    - Bare table functions such as `read_parquet(...)` are not mounted Fred
      datasets and must be blocked by the dataset allowlist before execution.

    How to use:
    - Ingest one valid dataset, then assert that a query using
      `read_parquet(...)` is rejected.
    """

    app_context = ApplicationContext.get_instance()
    content_store = app_context.get_content_store()
    metadata_store = app_context.get_metadata_store()
    content_store.clear()

    await _ingest_csv(
        tmp_path=tmp_path,
        metadata_store=metadata_store,
        document_uid="doc-sales",
        file_name="sales.csv",
        content="city,amount\nParis,10\nLyon,20\n",
    )

    service = TabularService()

    with pytest.raises(ValueError, match=r"unauthorized datasets: read_parquet\(\)"):
        await service.query_read(
            _user(),
            request=TabularQueryRequest(
                sql="SELECT * FROM read_parquet('/tmp/forbidden.parquet')",
            ),
        )


@pytest.mark.asyncio
async def test_tabular_service_rejects_explicit_dataset_requests_without_rebac_access(tmp_path, metadata_store):
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    visible_metadata = await _ingest_csv(
        tmp_path=tmp_path,
        metadata_store=metadata_store,
        document_uid="doc-visible",
        file_name="visible.csv",
        content="city,amount\nParis,10\n",
    )
    await _ingest_csv(
        tmp_path=tmp_path,
        metadata_store=metadata_store,
        document_uid="doc-hidden",
        file_name="hidden.csv",
        content="city,amount\nLyon,20\n",
    )

    service = TabularService()
    service.rebac = _FakeRebac({"doc-visible"})

    datasets = await service.list_datasets(_user())
    assert [dataset.document_uid for dataset in datasets] == [visible_metadata.document_uid]

    with pytest.raises(PermissionError, match="doc-hidden"):
        await service.query_read(
            _user(),
            request=TabularQueryRequest(
                sql="SELECT 1",
                dataset_uids=["doc-hidden"],
            ),
        )


@pytest.mark.asyncio
async def test_tabular_service_lists_authorized_datasets_with_targeted_metadata_lookup(tmp_path, metadata_store):
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    await _ingest_csv(
        tmp_path=tmp_path,
        metadata_store=metadata_store,
        document_uid="doc-visible",
        file_name="visible.csv",
        content="city,amount\nParis,10\n",
    )
    await _ingest_csv(
        tmp_path=tmp_path,
        metadata_store=metadata_store,
        document_uid="doc-hidden",
        file_name="hidden.csv",
        content="city,amount\nLyon,20\n",
    )

    service = TabularService()
    tracking_store = _TrackingMetadataStore(metadata_store)
    service.metadata_store = tracking_store
    service.rebac = _FakeRebac({"doc-visible"})

    datasets = await service.list_datasets(_user())

    assert [dataset.document_uid for dataset in datasets] == ["doc-visible"]
    assert tracking_store.get_all_metadata_calls == 0
    assert tracking_store.get_metadata_by_uids_calls == [["doc-visible"]]


@pytest.mark.asyncio
async def test_tabular_service_requires_httpfs_for_remote_locations(tmp_path, metadata_store):
    """
    Verify remote tabular access fails clearly when `httpfs` cannot be loaded.

    Why this exists:
    - Remote S3-compatible access must stay `httpfs`-only with no hidden local
      copy fallback.

    How to use:
    - Wrap the local content store with presigned URLs and force
      `_ensure_httpfs_ready(...)` to fail.
    """

    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    await _ingest_csv(
        tmp_path=tmp_path,
        metadata_store=metadata_store,
        document_uid="doc-sales",
        file_name="sales.csv",
        content="city,amount\nParis,10\nLyon,20\n",
    )

    service = TabularService()
    service.content_store = _PresignedLocalContentStore(content_store)
    service._ensure_httpfs_ready = lambda connection: (_ for _ in ()).throw(  # type: ignore[method-assign]
        RuntimeError("DuckDB httpfs is required for remote tabular dataset access.")
    )

    dataset = (await service.list_datasets(_user()))[0]
    with pytest.raises(RuntimeError, match="DuckDB httpfs is required"):
        await service.query_read(
            _user(),
            request=TabularQueryRequest(
                sql=f"SELECT city, amount FROM {dataset.query_alias} ORDER BY amount DESC",
            ),
        )

    with pytest.raises(RuntimeError, match="DuckDB httpfs is required"):
        await service.read_dataset_frame(_user(), "doc-sales")

    assert service.content_store.internal_presigned_calls >= 2
    assert service.content_store.public_presigned_calls == 0


@pytest.mark.asyncio
async def test_tabular_service_scopes_datasets_to_active_team_and_libraries(tmp_path, metadata_store):
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    await _ingest_csv(
        tmp_path=tmp_path,
        metadata_store=metadata_store,
        document_uid="doc-team-a",
        file_name="sales-team-a.csv",
        content="city,amount\nParis,10\n",
        tag_ids=["tag-team-a"],
        tag_names=["Team A"],
    )
    await _ingest_csv(
        tmp_path=tmp_path,
        metadata_store=metadata_store,
        document_uid="doc-team-b",
        file_name="sales-team-b.csv",
        content="city,amount\nLyon,20\n",
        tag_ids=["tag-team-b"],
        tag_names=["Team B"],
    )

    service = TabularService()
    service.tag_service = _FakeTagService(
        readable_tag_ids={"tag-team-a", "tag-team-b"},
        team_scopes={"team-a": {"tag-team-a"}, "team-b": {"tag-team-b"}},
    )

    team_a_datasets = await service.list_datasets(
        _user(),
        owner_filter=OwnerFilter.TEAM,
        team_id="team-a",
    )
    assert [dataset.document_uid for dataset in team_a_datasets] == ["doc-team-a"]

    scoped_schema = await service.describe_dataset(
        _user(),
        "doc-team-a",
        owner_filter=OwnerFilter.TEAM,
        team_id="team-a",
    )
    assert scoped_schema.document_uid == "doc-team-a"

    assert (
        await service.list_datasets(
            _user(),
            owner_filter=OwnerFilter.TEAM,
            team_id="team-a",
            document_library_tags_ids=["tag-team-b"],
        )
    ) == []

    all_datasets = await service.list_datasets(_user())
    alias_by_uid = {dataset.document_uid: dataset.query_alias for dataset in all_datasets}

    scoped_rows = await service.query_read(
        _user(),
        request=TabularQueryRequest(
            sql=f"SELECT city, amount FROM {alias_by_uid['doc-team-a']}",
            owner_filter=OwnerFilter.TEAM,
            team_id="team-a",
        ),
    )
    assert scoped_rows.rows == [{"city": "Paris", "amount": 10}]

    with pytest.raises(ValueError, match="unauthorized datasets"):
        await service.query_read(
            _user(),
            request=TabularQueryRequest(
                sql=f"SELECT city, amount FROM {alias_by_uid['doc-team-b']}",
                owner_filter=OwnerFilter.TEAM,
                team_id="team-a",
            ),
        )


def test_tabular_service_httpfs_install_is_attempted_after_load_failure():
    """
    Verify the tabular runtime tries `INSTALL httpfs` after a failed load.

    Why this exists:
    - Connected environments may start without the extension preloaded even
      though remote tabular access is still expected to work.

    How to use:
    - Call `_ensure_httpfs_ready(...)` with a fake DuckDB connection whose
      first `LOAD httpfs` fails and whose subsequent install+load succeeds.

    Example:
    - `service._ensure_httpfs_ready(fake_connection)`
    """

    class _ConnectionProbe:
        def __init__(self) -> None:
            self.commands: list[str] = []
            self._first_load = True

        def execute(self, sql: str) -> None:
            self.commands.append(sql)
            if sql == "LOAD httpfs" and self._first_load:
                self._first_load = False
                raise RuntimeError("missing extension")

    service = TabularService()
    connection = _ConnectionProbe()

    service._ensure_httpfs_ready(connection)  # type: ignore[arg-type]

    assert connection.commands == ["LOAD httpfs", "INSTALL httpfs", "LOAD httpfs"]
