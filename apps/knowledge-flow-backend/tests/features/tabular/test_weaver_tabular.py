# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Published SQL data uses the common Weaver boundary, including direct reads."""

import hashlib
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import duckdb
import pytest
from fred_core.documents import access
from fred_core.documents.document_structures import DocumentMetadata, FileInfo, Identity, ProcessingStage, SourceInfo, SourceType
from fred_core.documents.selection import DocumentScope
from fred_core.security.delegation import AssertedUser

from knowledge_flow_backend.common.structures import TabularStoreConfig
from knowledge_flow_backend.features.tabular import service as module
from knowledge_flow_backend.features.tabular.artifacts import TabularArtifactV1, build_default_query_alias
from knowledge_flow_backend.features.tabular.structures import TabularColumnSchema, TabularQueryRequest, TabularSearchRequest

SPACE, OTHER_SPACE, A, B, D1, D2, D3 = [UUID(int=i) for i in range(1, 8)]
PERSON = AssertedUser(uid="alice", client_id="fred-agents", run_id="turn", agent_id="agent")


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


@pytest.fixture
def published(tmp_path, monkeypatch):
    facts, objects = [], {}
    for uid, folder in [(D1, A), (D2, A), (D3, B)]:
        path = f"datasets/{uid}.parquet"
        local = tmp_path / str(uid)
        with duckdb.connect() as conn:
            conn.sql("select 'Paris' as city, 12 as amount union all select 'Lyon', 8").write_parquet(str(local))
        table = TabularArtifactV1(
            dataset_uid=str(uid),
            object_key=path,
            source_revision="a" * 64,
            row_count=2,
            columns=[TabularColumnSchema(name="city", dtype="string", is_categorical=True), TabularColumnSchema(name="amount", dtype="integer")],
            generated_at="2026-01-01T00:00:00Z",
            file_size_bytes=local.stat().st_size,
        )
        metadata = DocumentMetadata(
            identity=Identity(document_uid=str(uid), document_name=f"{uid}.csv"),
            source=SourceInfo(source_type=SourceType.PUSH, retrievable=True),
            file=FileInfo(sha256="a" * 64, row_count=2),
            extensions={"tabular_v1": table.model_dump()},
        )
        metadata.mark_stage_done(ProcessingStage.SQL_INDEXED)
        prefix = f"generation/{uid}/"
        payloads = {"metadata.json": metadata.model_dump_json().encode(), path: local.read_bytes(), "output.md": b"preview"}
        for name, data in payloads.items():
            objects[prefix + name] = data
            facts.append(
                dict(
                    id=uid,
                    name=f"{uid}.csv",
                    sha256="a" * 64,
                    folder_id=folder,
                    space_id=SPACE,
                    deletion_id=None,
                    space_deletion_id=None,
                    retrievable=True,
                    retrievable_pending=False,
                    generation_id=uid,
                    prefix=prefix,
                    path=name,
                    size=len(data),
                    artifact_sha256=hashlib.sha256(data).hexdigest(),
                )
            )

    class Engine:
        @asynccontextmanager
        async def connect(self):
            yield self

        async def execute(self, statement, params):
            if statement is access._SPACE:
                return Rows([dict(id=SPACE, parent_id=None, organization_id=SPACE, deletion_id=None)])
            if statement is access._FOLDERS:
                return Rows([dict(id=id, path=f"/{id}/") for id in params["folder_ids"] if id in (A, B)])
            assert statement is access._TABULAR_DOCUMENTS
            # Model the SQL publication/space/page predicate, not the visibility filter.
            return Rows(
                [
                    row
                    for row in facts
                    if row["generation_id"] is not None and row["space_id"] in params["space_ids"] and row["id"] > params["after"] and (params["all_documents"] or row["id"] in params["document_ids"])
                ]
            )

    reads = []

    def read_bytes(prefix, artifact):
        reads.append(prefix + artifact.path)
        data = objects[prefix + artifact.path]
        assert len(data) == artifact.size and hashlib.sha256(data).hexdigest() == artifact.sha256
        return data

    def location(bucket, key, **kwargs):
        assert key in objects
        return str(tmp_path / key.split("/")[-1].removesuffix(".parquet"))

    context = SimpleNamespace(
        get_pg_async_engine=lambda: Engine(),
        get_config=lambda: SimpleNamespace(storage=SimpleNamespace(tabular_store=TabularStoreConfig())),
        get_published_artifact_reader=lambda: SimpleNamespace(read_bytes=read_bytes, bucket="derived", client=SimpleNamespace(presigned_get_object=location)),
    )
    monkeypatch.setattr(module.ApplicationContext, "get_instance", lambda: context)
    permission = AsyncMock()
    monkeypatch.setattr(module, "require_space_read", permission)

    def service(scope=DocumentScope()):
        return module.TabularService(space_id=SPACE, document_scope=scope)

    return SimpleNamespace(service=service, facts=facts, reads=reads, permission=permission, objects=objects)


@pytest.mark.asyncio
async def test_published_csv_supports_sql_schema_search_and_direct_reads(published):
    service = published.service(DocumentScope.from_ids(document_ids=[str(D1)]))
    [document] = await service.list_documents(PERSON)
    alias = document.tables[0].query_alias
    result = await service.query_read(PERSON, request=TabularQueryRequest(sql=f"select sum(amount) as total from {alias}", dataset_uids=[str(D1)]))
    assert result.rows == [{"total": 20}]
    [description] = await service.describe_documents(PERSON, [str(D1)])
    assert description.tables[0].columns[1].min_value == 8
    assert description.tables[0].columns[1].max_value == 12
    matches = await service.search_values(PERSON, request=TabularSearchRequest(keyword="PARIS"))
    assert matches.searched_dataset_uids == [str(D1)]
    assert len(await service.read_dataset_frame(PERSON, str(D1))) == 2
    assert len(await service.read_dataset_preview_frame(PERSON, str(D1), max_rows=1)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "selection,expected",
    [
        (DocumentScope.from_ids([str(A)]), {D1, D2}),
        (DocumentScope.from_ids([str(A)]).intersect(DocumentScope.from_ids(document_ids=[str(D1)])), {D1}),
        (DocumentScope.from_ids([str(A)]).intersect(DocumentScope.from_ids([], [])), set()),
        (DocumentScope.from_ids([str(A)]).intersect(DocumentScope.from_ids()), {D1, D2}),
        (DocumentScope.from_ids([str(A)], [str(D3)]), {D1, D2, D3}),
        (DocumentScope.from_ids([str(A)]).intersect(DocumentScope.from_ids(document_ids=[str(D3)])), set()),
    ],
)
async def test_discovery_preserves_union_intersection_empty_and_reset(published, selection, expected):
    docs = await published.service(selection).list_documents(PERSON)
    assert {UUID(doc.document_uid) for doc in docs} == expected
    assert all(any(f"/{uid}/" in key for uid in expected) for key in published.reads)
    published.permission.assert_awaited_once_with(PERSON, SPACE)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["describe", "frame", "preview", "query", "search"])
async def test_known_uuid_and_multi_dataset_cannot_escape_selection(published, operation):
    service = published.service(DocumentScope.from_ids([str(A)]))
    with pytest.raises(PermissionError):
        if operation == "describe":
            await service.describe_documents(PERSON, [str(D1), str(D3)])
        elif operation == "frame":
            await service.read_dataset_frame(PERSON, str(D3))
        elif operation == "preview":
            await service.read_dataset_preview_frame(PERSON, str(D3))
        elif operation == "query":
            await service.query_read(PERSON, request=TabularQueryRequest(sql=f"select * from {build_default_query_alias(str(D1), f'{D1}.csv')}", dataset_uids=[str(D1), str(D3)]))
        else:
            await service.search_values(PERSON, request=TabularSearchRequest(keyword="Paris", dataset_uids=[str(D1), str(D3)]))
    assert not any(f"/{D3}/" in key for key in published.reads)


@pytest.mark.asyncio
@pytest.mark.parametrize("inventory", ["list_documents", "list_datasets"])
@pytest.mark.parametrize("field,value", [("generation_id", None), ("deletion_id", D3), ("space_deletion_id", D3), ("space_id", OTHER_SPACE), ("retrievable", False), ("retrievable_pending", True)])
async def test_each_read_rechecks_publication_lifecycle_and_space(published, field, value, inventory):
    service = published.service(DocumentScope.from_ids(document_ids=[str(D1)]))
    list_inventory = getattr(service, inventory)
    assert len(await list_inventory(PERSON)) == 1
    for row in published.facts:
        if row["id"] == D1:
            row[field] = value
    published.reads.clear()
    assert await list_inventory(PERSON) == []
    assert published.reads == []
    with pytest.raises(PermissionError):
        await service.read_dataset_frame(PERSON, str(D1))


@pytest.mark.asyncio
@pytest.mark.parametrize("inventory", ["list_documents", "list_datasets"])
@pytest.mark.parametrize("error", [PermissionError, RuntimeError])
async def test_each_inventory_rechecks_space_before_artifact_access(published, inventory, error):
    list_inventory = getattr(published.service(), inventory)
    assert len(await list_inventory(PERSON)) == 3
    published.reads.clear()
    published.permission.side_effect = error("space authorization unavailable")
    with pytest.raises(error, match="space authorization unavailable"):
        await list_inventory(PERSON)
    assert not published.reads
    assert published.permission.await_count == 2


@pytest.mark.parametrize("key", ["document_scope", "space_id", "owner_filter", "attachment_uids", "corpus_document_uids"])
def test_tool_arguments_cannot_supply_authority(key):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TabularQueryRequest.model_validate({"sql": "select 1", key: []})


@pytest.mark.asyncio
async def test_table_must_belong_to_the_same_published_manifest(published):
    # A descriptor in valid metadata cannot point at another document's object.
    import json

    key = f"generation/{D1}/metadata.json"
    metadata = json.loads(published.objects[key])
    metadata["extensions"]["tabular_v1"]["object_key"] = f"datasets/{D3}.parquet"
    data = json.dumps(metadata).encode()
    published.objects[key] = data
    for row in published.facts:
        if row["id"] == D1 and row["path"] == "metadata.json":
            row.update(size=len(data), artifact_sha256=hashlib.sha256(data).hexdigest())
    with pytest.raises(ValueError, match="artifact"):
        await published.service(DocumentScope.from_ids(document_ids=[str(D1)])).list_documents(PERSON)


@pytest.mark.asyncio
async def test_weaver_resolution_preserves_sql_sandbox_and_explicit_empty_query(published):
    service = published.service(DocumentScope.from_ids([str(A)]))
    [document] = await service.describe_documents(PERSON, [str(D1)])
    alias = document.tables[0].query_alias
    for sql in [f"DROP TABLE {alias}", "SELECT * FROM read_parquet('/etc/passwd')", f"SELECT current_setting('allowed_paths') FROM {alias}", "SELECT 1"]:
        with pytest.raises(ValueError):
            await service.query_read(PERSON, request=TabularQueryRequest(sql=sql))
    with pytest.raises(ValueError):
        await service.query_read(PERSON, request=TabularQueryRequest(sql=f"SELECT * FROM {alias}", dataset_uids=[]))
    result = await service.query_read(PERSON, request=TabularQueryRequest(sql=f"SELECT sum(amount) AS total FROM {alias}", dataset_uids=[str(D1)]))
    assert result.rows == [{"total": 20}]


@pytest.mark.asyncio
async def test_workbook_reads_every_published_table_and_its_catalog(published):
    import json

    key = f"generation/{D1}/metadata.json"
    metadata = json.loads(published.objects[key])
    single = metadata["extensions"].pop("tabular_v1")
    # Two identical sheets can share the same Parquet object and keep distinct aliases.
    metadata["extensions"]["tabular_multi_v1"] = {"tables": [{**single, "query_alias": alias, "sheet": alias, "table_id": alias} for alias in ("sales_a", "sales_b")]}
    metadata["file"]["row_count"] = 4
    data = json.dumps(metadata).encode()
    published.objects[key] = data
    for row in published.facts:
        if row["id"] == D1 and row["path"] == "metadata.json":
            row.update(size=len(data), artifact_sha256=hashlib.sha256(data).hexdigest())
    service = published.service(DocumentScope.from_ids(document_ids=[str(D1)]))
    [document] = await service.describe_documents(PERSON, [str(D1)])
    assert document.kind == "spreadsheet"
    assert document.markdown == "preview"
    assert {table.query_alias for table in document.tables} == {"sales_a", "sales_b"}
    result = await service.query_read(
        PERSON,
        request=TabularQueryRequest(
            sql="select sum(a.amount + b.amount) as total from sales_a a join sales_b b on a.city=b.city",
            dataset_uids=[str(D1)],
        ),
    )
    assert result.rows == [{"total": 40}]
    # The same published object is no longer visible when the document is excluded.
    for row in published.facts:
        if row["id"] == D1:
            row["retrievable"] = False
    with pytest.raises(PermissionError):
        await service.describe_documents(PERSON, [str(D1)])
