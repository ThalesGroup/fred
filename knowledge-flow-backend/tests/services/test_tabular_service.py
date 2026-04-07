from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fred_core import KeycloakUser

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.document_structures import (
    DocumentMetadata,
    FileInfo,
    FileType,
    Identity,
    SourceInfo,
    SourceType,
)
from knowledge_flow_backend.core.processors.output.tabular_processor.tabular_processor import TabularProcessor
from knowledge_flow_backend.features.tabular.artifacts import (
    TABULAR_EXTENSION_KEY,
    document_artifact_prefix,
    read_tabular_artifact,
)
from knowledge_flow_backend.features.tabular.service import TabularService
from knowledge_flow_backend.features.tabular.structures import TabularQueryRequest


def _user() -> KeycloakUser:
    return KeycloakUser(
        uid="u-1",
        username="tester",
        email="tester@example.com",
        roles=["admin"],
        groups=["admins"],
    )


def _metadata(*, document_uid: str, file_name: str) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name=file_name, document_uid=document_uid, title=file_name),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"),
        file=FileInfo(file_type=FileType.CSV, mime_type="text/csv"),
    )


async def _ingest_csv(
    *,
    tmp_path: Path,
    metadata_store,
    document_uid: str,
    file_name: str,
    content: str,
) -> DocumentMetadata:
    csv_path = tmp_path / file_name
    csv_path.write_text(content, encoding="utf-8")

    processor = TabularProcessor()
    metadata = _metadata(document_uid=document_uid, file_name=file_name)
    processed_metadata = processor.process(str(csv_path), metadata)
    await metadata_store.save_metadata(processed_metadata)
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

    def get_presigned_url(self, key, expires=None) -> str:
        del expires
        return f"https://signed.example.invalid/{key}"

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

    object_prefix = document_artifact_prefix(
        artifacts_prefix=ApplicationContext.get_instance().get_config().tabular.artifacts_prefix,
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
    assert len(stored_objects) == 1
    assert stored_objects[0].key == updated_artifact.object_key


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
