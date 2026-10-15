# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied.

import asyncio
from collections import Counter
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from fred_core import AuthorizationError, KeycloakUser
from fred_core.documents.document_structures import DocumentMetadata, FileInfo, Identity, Processing, ProcessingStage, ProcessingStatus, SourceInfo, SourceType, Tagging
from fred_core.documents.postgres_document_store import PostgresDocumentMetadataStore
from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter
from fred_core.models.base import Base
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from fred_core.security.rebac.openfga_engine import OpenFgaRebacEngine
from fred_core.security.structure import OpenFgaRebacConfig
from sqlalchemy.ext.asyncio import create_async_engine

from knowledge_flow_backend.core.stores.tags.base_tag_store import TagNotFoundError
from knowledge_flow_backend.core.stores.tags.postgres_tag_store import PostgresTagStore
from knowledge_flow_backend.features.metadata.service import MetadataService, MetadataUpdateError
from knowledge_flow_backend.features.tag import tag_service as tag_module
from knowledge_flow_backend.features.tag.structure import Tag, TagType, TagUpdate
from knowledge_flow_backend.features.tag.tag_item_service import DocumentTagItemService
from knowledge_flow_backend.features.tag.tag_service import TagService

pytestmark = pytest.mark.asyncio
USER = KeycloakUser(uid="reader", username="reader", roles=[])


class FgaClient:
    """Exercise the real engine through an offline SDK transport boundary."""

    def __init__(self):
        self.calls = Counter()
        self.writes = 0
        self.denied = set()
        self.failure = None
        self.active = self.peak = 0
        self.global_documents = [f"document:other-{i}" for i in range(1000)]

    async def check(self, body, options):
        self.calls[(body.relation, body.object)] += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(0)
            if self.failure:
                raise self.failure
            return SimpleNamespace(allowed=body.object not in self.denied)
        finally:
            self.active -= 1

    async def list_objects(self, body, options):
        self.calls[("list_objects", body.type)] += 1
        return SimpleNamespace(objects=self.global_documents[:1000])

    async def write(self, body, options):
        self.writes += 1
        return None


def engine_and_client():
    engine = OpenFgaRebacEngine(OpenFgaRebacConfig(api_url="http://unused:8080"), token="offline-fixture")  # nosec B106
    client = FgaClient()
    engine._cached_client = client
    return engine, client


def document(uid, tags):
    return DocumentMetadata(
        identity=Identity(document_uid=uid, document_name=f"{uid}.txt"),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"),
        tags=Tagging(tag_ids=tags),
        file=FileInfo(file_size_bytes=10),
        processing=Processing(stages={ProcessingStage.VECTORIZED: ProcessingStatus.DONE}),
    )


def folder(uid, name, path=None, owner="team-a", kind=TagType.DOCUMENT):
    now = datetime.now(timezone.utc)
    return Tag(id=uid, name=name, path=path, owner_id=owner, type=kind, created_at=now, updated_at=now)


@pytest.fixture
def candidates():
    svc = MetadataService.__new__(MetadataService)
    svc.rebac, client = engine_and_client()
    docs = [document(f"d-{i:02}", ["folder"]) for i in range(20)]
    svc.metadata_store = SimpleNamespace(
        get_metadata_by_uids=AsyncMock(return_value=docs),
        get_metadata_in_tag=AsyncMock(return_value=docs),
        document_uids_by_tags=AsyncMock(return_value={"folder": [d.document_uid for d in docs], "shared": [docs[0].document_uid]}),
        metadata_in_tags=AsyncMock(return_value=docs),
        browse_metadata_in_tag=AsyncMock(return_value=(docs[5:10], 20)),
    )
    return svc, client, docs


@pytest.mark.parametrize("irrelevant", [0, 1001])
@pytest.mark.parametrize("method", ["uids", "folder", "folder_ids", "folders", "page"])
async def test_known_candidates_ignore_global_inventory(candidates, method, irrelevant):
    svc, client, docs = candidates
    client.global_documents = [f"document:other-{i}" for i in range(irrelevant)]
    client.denied = {"document:d-07"}
    selected = docs[5:10] if method == "page" else docs
    expected = [d.document_uid for d in selected if d.document_uid != "d-07"]
    if method == "uids":
        result = await svc.get_documents_by_uids(USER, [d.document_uid for d in docs] + ["missing"])
    elif method == "folder":
        result = await svc.get_document_metadata_in_tag(USER, "folder")
    elif method == "folder_ids":
        by_tag = await svc.get_document_uids_in_tags(USER, ["folder", "shared"])
        assert by_tag == {"folder": expected, "shared": ["d-00"]}
        result = [d for d in docs if d.document_uid in by_tag["folder"]]
    elif method == "folders":
        result = await svc.get_documents_metadata_in_tags(USER, ["folder", "shared"])
    else:
        result, total = await svc.browse_documents_in_tag(USER, "folder", offset=5, limit=5, sort_by="name", sort_order="desc")
        assert total == 20
        svc.metadata_store.browse_metadata_in_tag.assert_awaited_once_with("folder", offset=5, limit=5, sort_by="name", sort_order="desc")
    assert [d.document_uid for d in result] == expected
    assert client.calls == {("read", f"document:{d.document_uid}"): 1 for d in selected}
    assert client.peak <= 10


async def test_checker_deduplicates_and_bounds_tasks(candidates):
    svc, client, _ = candidates
    uids = [f"d-{i}" for i in range(37)]
    assert await svc.filter_readable_document_uids(USER, uids * 3) == set(uids)
    assert sum(client.calls.values()) == 37
    assert client.peak == 10
    client.calls.clear()
    assert await svc.filter_readable_document_uids(USER, []) == set()
    assert not client.calls


async def test_disabled_authorization_keeps_candidates(candidates):
    svc, _, docs = candidates
    svc.rebac = NoopRebacEngine()
    assert await svc.get_document_metadata_in_tag(USER, "folder") == docs


async def test_authority_failure_is_not_empty_inventory(candidates):
    svc, client, _ = candidates
    client.failure = TimeoutError("authority unavailable")
    with pytest.raises(TimeoutError):
        await svc.get_document_metadata_in_tag(USER, "folder")


@pytest_asyncio.fixture
async def deletion(tmp_path, monkeypatch):
    sql = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'inventory.db'}")
    async with sql.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    tags, store = PostgresTagStore(sql), PostgresDocumentMetadataStore(sql)
    rebac, client = engine_and_client()
    md = MetadataService.__new__(MetadataService)
    md.metadata_store, md.rebac = store, rebac
    md.vector_store, md.content_store = Mock(), Mock()
    # Both fixture folders have the same owner; only the final unlink releases bytes.
    md._resolve_storage_deltas = AsyncMock(side_effect=lambda **kw: ({"team-a": -kw["old_size"]}, {}) if kw["new_size"] == 0 else ({}, {}))
    md._apply_storage_deltas = AsyncMock()
    ctx = SimpleNamespace(get_pg_async_engine=lambda: sql, get_tag_store=lambda: tags, get_kpi_writer=NoOpKPIWriter)
    monkeypatch.setattr(tag_module.ApplicationContext, "get_instance", lambda: ctx)
    item = DocumentTagItemService.__new__(DocumentTagItemService)
    item.document_metadata_service = md
    monkeypatch.setattr(tag_module, "get_specific_tag_item_service", lambda kind: item)
    svc = TagService.__new__(TagService)
    svc._tag_store, svc.rebac, svc.document_metadata_service = tags, rebac, md
    try:
        yield svc, md, client, tags, store
    finally:
        await sql.dispose()


async def test_delete_uses_complete_subtree_and_preserves_other_owners(deletion):
    svc, md, client, tags, store = deletion
    for tag in [folder("root", "Reports"), folder("child", "Child", "Reports"), folder("sibling", "Reports-other"), folder("foreign", "Reports", owner="team-b")]:
        await tags.create_tag(tag)
    for i in range(20):
        await store.save_metadata(document(f"d-{i}", ["root", "child"]))
    await store.save_metadata(document("elsewhere", ["foreign"]))

    await svc.delete_tag_for_user("root", USER)

    assert {tag.id for tag in await tags.list_all_tags()} == {"sibling", "foreign"}
    assert [d.document_uid for d in await store.get_all_metadata({})] == ["elsewhere"]
    assert md.vector_store.delete_vectors_for_document.call_count == 20
    assert md.content_store.delete_content.call_count == 20
    releases = [call.kwargs for call in md._resolve_storage_deltas.await_args_list if call.kwargs["new_size"] == 0]
    assert len(releases) == 20
    assert all(call["old_tags"] == {"root"} for call in releases)
    assert sum(call.args[0].get("team-a", 0) for call in md._apply_storage_deltas.await_args_list) == -200
    assert client.peak <= 10
    # F=2 folders, N=20 documents, M=40 memberships; admission is tested separately.
    assert sum(client.calls.values()) == 1 + 2 * 2 + 20 + 2 * 40
    assert client.writes == 40


@pytest.mark.parametrize("denied", ["tag:child", "document:d-1"])
async def test_denied_subtree_is_rejected_before_any_removal(deletion, denied):
    svc, md, client, tags, store = deletion
    await tags.create_tag(folder("root", "Root"))
    await tags.create_tag(folder("child", "Child", "Root"))
    await store.save_metadata(document("d-1", ["child"]))
    client.denied.add(denied)
    with pytest.raises(AuthorizationError):
        await svc.delete_tag_for_user("root", USER)
    assert len(await tags.list_all_tags()) == 2
    assert (await store.get_metadata_by_uid("d-1")).tags.tag_ids == ["child"]
    md.content_store.delete_content.assert_not_called()


async def test_shared_document_survives_folder_deletion(deletion):
    svc, md, _, tags, store = deletion
    await tags.create_tag(folder("a", "A"))
    await tags.create_tag(folder("b", "B"))
    await store.save_metadata(document("shared", ["a", "b"]))
    await svc.delete_tag_for_user("a", USER)
    assert (await store.get_metadata_by_uid("shared")).tags.tag_ids == ["b"]
    md.content_store.delete_content.assert_not_called()
    md.vector_store.delete_vectors_for_document.assert_not_called()
    with pytest.raises(TagNotFoundError):
        await tags.get_tag_by_id("a")


async def test_remaining_membership_prevents_folder_removal(deletion, monkeypatch):
    svc, _, _, tags, store = deletion
    await tags.create_tag(folder("a", "A"))
    await store.save_metadata(document("d", ["a"]))
    monkeypatch.setattr(DocumentTagItemService, "remove_tag_id_from_item", AsyncMock())
    with pytest.raises(MetadataUpdateError, match="memberships remain"):
        await svc.delete_tag_for_user("a", USER)
    assert (await tags.get_tag_by_id("a")).id == "a"


async def test_update_removes_document_omitted_by_global_inventory(deletion):
    svc, md, _, tags, store = deletion
    await tags.create_tag(folder("a", "A"))
    await store.save_metadata(document("d", ["a"]))
    result = await svc.update_tag_for_user("a", TagUpdate(name="A", type=TagType.DOCUMENT, item_ids=[]), USER)
    assert result.item_ids == []
    assert await store.get_metadata_by_uid("d") is None
    md.content_store.delete_content.assert_called_once_with("d")


async def test_subtree_matches_literal_path_owner_and_type(deletion):
    _, _, _, tags, _ = deletion
    root = folder("root", "A_%")
    candidates = [
        root,
        folder("child", "Nested/Legacy", "A_%"),
        folder("prefix", "A_%more"),
        folder("wildcard", "Child", "ABx"),
        folder("foreign", "Child", "A_%", owner="team-b"),
        folder("other-type", "Child", "A_%", kind=TagType.PROMPT),
    ]
    for tag in candidates:
        await tags.create_tag(tag)
    assert {t.id for t in await tags.list_subtree(root)} == {"root", "child"}


async def test_failed_preflight_keeps_inventory(deletion):
    svc, md, _, tags, store = deletion
    await tags.create_tag(folder("a", "A"))
    await store.save_metadata(document("d", ["a"]))
    md.filter_readable_document_uids = AsyncMock(side_effect=TimeoutError("authority unavailable"))
    with pytest.raises(TimeoutError):
        await svc.delete_tag_for_user("a", USER)
    assert (await tags.get_tag_by_id("a")).id == "a"
    assert (await store.get_metadata_by_uid("d")).tags.tag_ids == ["a"]
    md.content_store.delete_content.assert_not_called()


async def test_empty_document_folder_can_be_deleted(deletion):
    svc, md, _, tags, _ = deletion
    await tags.create_tag(folder("a", "A"))
    await svc.delete_tag_for_user("a", USER)
    assert await tags.list_all_tags() == []
    md.content_store.delete_content.assert_not_called()


async def test_subtree_preflight_is_bounded_and_completes_before_mutation(deletion):
    svc, _, client, tags, _ = deletion
    await tags.create_tag(folder("root", "Root"))
    for i in range(25):
        await tags.create_tag(folder(f"child-{i}", f"Child-{i}", "Root"))

    async def remove(tag, user):
        assert all(client.calls[("delete", f"tag:child-{i}")] == 1 for i in range(25))

    svc._delete_one_tag = AsyncMock(side_effect=remove)
    await svc.delete_tag_for_user("root", USER)
    assert svc._delete_one_tag.await_count == 26
    assert client.calls[("delete", "tag:root")] == 2
    assert sum(client.calls.values()) == 27
    assert client.peak == 10
