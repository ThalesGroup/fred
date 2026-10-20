# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied.

"""SQL folder membership selects candidates; ReBAC parents authorize reads."""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fred_core import DocumentPermission, RebacDisabledResult, Relation, TagPermission
from fred_core.documents.document_structures import DocumentMetadata, Identity, SourceInfo, SourceType, Tagging
from fred_core.documents.postgres_document_store import PostgresDocumentMetadataStore
from fred_core.models.base import Base as CoreBase
from fred_core.security.rebac.rebac_engine import ResourcePermission
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from knowledge_flow_backend.core.stores.resources.postgres_resource_store import PostgresResourceStore
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.resources.service import ResourceService
from knowledge_flow_backend.features.resources.structures import Resource, ResourceKind, ResourceUpdate
from knowledge_flow_backend.features.tabular.artifacts import TABULAR_EXTENSION_KEY, TabularArtifactV1
from knowledge_flow_backend.features.tabular.service import TabularService
from knowledge_flow_backend.features.tag.tag_item_service import DocumentTagItemService, ResourceTagItemService
from knowledge_flow_backend.models.base import Base as KnowledgeBase

pytestmark = pytest.mark.asyncio

A, B = "removed-folder", "retained-folder"
DOCUMENT, RESOURCE = "00-confidential", "confidential-resource"
PUBLIC_DOCUMENTS = ["10-visible", "20-visible"]
EDITOR = SimpleNamespace(uid="editor", roles=[])
READER_A = SimpleNamespace(uid="reader-a", roles=[])
READER_B = SimpleNamespace(uid="reader-b", roles=[])
DOCUMENT_SURFACES = ["documents", "labels", "label-uids", "label-documents", "label-page", "tabular-datasets", "tabular-documents", "tabular-explicit"]


class _FolderRebac:
    """Parent-based READ with FGA parents independent of stored SQL tags."""

    def __init__(self, readable_tags: set[str] | dict[str, set[str]] | None, parents: dict[str, set[str]]) -> None:
        self.readable_tags = readable_tags
        self.parents = parents

    def _tags_for(self, user: SimpleNamespace) -> set[str]:
        if isinstance(self.readable_tags, dict):
            return self.readable_tags[user.uid]
        return self.readable_tags or set()

    async def lookup_user_resources(self, user: SimpleNamespace, permission: TagPermission) -> list[SimpleNamespace] | RebacDisabledResult:
        assert permission is TagPermission.READ, "Listings must not enumerate documents or resources"
        if self.readable_tags is None:
            return RebacDisabledResult()
        return [SimpleNamespace(id=tag_id) for tag_id in self._tags_for(user)]

    async def has_user_permission(self, user: SimpleNamespace, permission: TagPermission | DocumentPermission | ResourcePermission, uid: str) -> bool:
        if self.readable_tags is None:
            return True
        if permission is TagPermission.READ:
            return uid in self._tags_for(user)
        if permission is TagPermission.UPDATE:
            return user.uid == EDITOR.uid and uid in self._tags_for(user)
        if permission is DocumentPermission.READ or permission is ResourcePermission.READ:
            return bool(self.parents.get(uid, set()) & self._tags_for(user))
        if permission is DocumentPermission.UPDATE or permission is ResourcePermission.UPDATE:
            return user.uid == EDITOR.uid and bool(self.parents.get(uid, set()) & self._tags_for(user))
        raise AssertionError(permission)

    async def check_user_permission_or_raise(self, user: SimpleNamespace, permission: TagPermission | DocumentPermission | ResourcePermission, uid: str) -> None:
        if not await self.has_user_permission(user, permission, uid):
            raise PermissionError(f"{permission} denied for {user.uid}: {uid}")

    async def delete_relation(self, relation: Relation) -> None:
        self.parents[relation.resource.id].discard(relation.subject.id)


def _doc(uid: str, tags: list[str], *, tabular: bool = False) -> DocumentMetadata:
    doc = DocumentMetadata(
        identity=Identity(document_uid=uid, document_name=f"{uid}.csv" if tabular else f"{uid}.txt"),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"),
        tags=Tagging(tag_ids=tags),
    )
    if tabular:
        doc.extensions = {
            TABULAR_EXTENSION_KEY: TabularArtifactV1(
                dataset_uid=uid,
                object_key=f"tabular/{uid}/data.parquet",
                source_revision="revision",
                generated_at="2026-10-20T00:00:00+00:00",
            ).model_dump(mode="json")
        }
    return doc


@pytest.mark.parametrize(("readable_tags", "expected"), [({"lib-a"}, ["in-a", "in-a-and-b"]), (None, ["in-a", "in-a-and-b", "in-b", "untagged"])])
async def test_document_listing_follows_readable_folders(readable_tags, expected):
    service = MetadataService.__new__(MetadataService)
    docs = [_doc("in-a", ["lib-a"]), _doc("in-a-and-b", ["lib-b", "lib-a"]), _doc("in-b", ["lib-b"]), _doc("untagged", [])]
    service.rebac = _FolderRebac(readable_tags, {doc.document_uid: set(doc.tags.tag_ids) for doc in docs})
    service.metadata_store = SimpleNamespace(get_all_metadata=AsyncMock(return_value=docs))

    listed = await service.get_documents_metadata(SimpleNamespace(uid="u-1"), {})

    assert [doc.document_uid for doc in listed] == expected


@pytest.mark.parametrize(("readable_tags", "expected"), [({"lib-a"}, ["prompt-a"]), (set(), []), (None, ["prompt-a", "prompt-b"])])
async def test_resource_listing_follows_readable_folders(readable_tags, expected):
    service = ResourceService.__new__(ResourceService)
    resources = [SimpleNamespace(id="prompt-a", library_tags=["lib-a"]), SimpleNamespace(id="prompt-b", library_tags=["lib-b"])]
    service.rebac = _FolderRebac(readable_tags, {resource.id: set(resource.library_tags) for resource in resources})
    service._resource_store = SimpleNamespace(get_all_resources=AsyncMock(return_value=resources))

    listed = await service.list_resources_by_kind(kind=ResourceKind.PROMPT, user=SimpleNamespace(uid="u-1"))

    assert [resource.id for resource in listed] == expected


@pytest_asyncio.fixture
async def stored_services() -> AsyncIterator[SimpleNamespace]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(CoreBase.metadata.create_all)
        await connection.run_sync(KnowledgeBase.metadata.create_all)
    try:
        rebac = _FolderRebac(
            {EDITOR.uid: {A, B}, READER_A.uid: {A}, READER_B.uid: {B}},
            {DOCUMENT: {A, B}, RESOURCE: {A, B}, **{uid: {A} for uid in PUBLIC_DOCUMENTS}},
        )
        metadata = MetadataService.__new__(MetadataService)
        metadata.metadata_store = PostgresDocumentMetadataStore(engine)
        metadata.rebac = rebac
        metadata.content_store = metadata.vector_store = None
        resources = ResourceService.__new__(ResourceService)
        resources._resource_store = PostgresResourceStore(engine)
        resources.rebac = rebac
        tabular = TabularService.__new__(TabularService)
        tabular.metadata_store = metadata.metadata_store
        tabular.rebac = rebac
        for uid, tags in [(DOCUMENT, [A, B]), *((uid, [A]) for uid in PUBLIC_DOCUMENTS)]:
            await metadata.metadata_store.save_metadata(_doc(uid, tags, tabular=True))
            await metadata.metadata_store.add_label(uid, "shared")
            await metadata.metadata_store.add_label(uid, "secret-label" if uid == DOCUMENT else "public-label")
        now = datetime.now(timezone.utc)
        await resources._resource_store.create_resource(
            Resource(
                id=RESOURCE,
                kind=ResourceKind.PROMPT,
                version="1",
                name="Original",
                author=EDITOR.uid,
                created_at=now,
                updated_at=now,
                content="CONFIDENTIAL FULL CONTENT",
                library_tags=[A, B],
            )
        )
        yield SimpleNamespace(metadata=metadata, resources=resources, tabular=tabular, rebac=rebac)
    finally:
        await engine.dispose()


async def _assert_document_surface(services: SimpleNamespace, user: SimpleNamespace, surface: str) -> None:
    expected = PUBLIC_DOCUMENTS if user.uid == READER_A.uid else [DOCUMENT]
    metadata = services.metadata
    if surface == "labels":
        assert await metadata.list_document_labels(user) == (["public-label", "shared"] if user.uid == READER_A.uid else ["secret-label", "shared"])
    elif surface == "label-uids":
        assert await metadata.get_document_uids_with_any_label(user, ["shared", "secret-label"]) == set(expected)
    elif surface == "label-page":
        for offset in range(len(expected) + 1):
            rows, total = await metadata.get_documents_with_label_page(user, "shared", offset=offset, limit=1)
            assert ([doc.document_uid for doc in rows], total) == (expected[offset : offset + 1], len(expected))
        rows, total = await metadata.get_documents_with_label_page(user, "secret-label", limit=1)
        assert ([doc.document_uid for doc in rows], total) == (([], 0) if user.uid == READER_A.uid else ([DOCUMENT], 1))
    else:
        if surface == "documents":
            rows = await metadata.get_documents_metadata(user, {})
        elif surface == "label-documents":
            rows = await metadata.get_documents_with_label(user, "shared")
        elif surface == "tabular-datasets":
            rows = await services.tabular.list_datasets(user)
        elif surface == "tabular-documents":
            rows = await services.tabular.list_documents(user)
        elif surface == "tabular-explicit":
            rows = await services.tabular.list_documents(user, corpus_document_uids=[DOCUMENT, *PUBLIC_DOCUMENTS])
        else:
            raise AssertionError(surface)
        assert sorted(doc.document_uid for doc in rows) == expected


async def _assert_resource_visibility(services: SimpleNamespace) -> None:
    assert await services.resources.list_resources_by_kind(kind=ResourceKind.PROMPT, user=READER_A) == []
    with pytest.raises(PermissionError):
        await services.resources.get(resource_id=RESOURCE, user=READER_A)
    visible = await services.resources.list_resources_by_kind(kind=ResourceKind.PROMPT, user=READER_B)
    direct = await services.resources.get(resource_id=RESOURCE, user=READER_B)
    assert [resource.id for resource in visible] == [RESOURCE]
    assert visible[0].content == direct.content
    assert "CONFIDENTIAL FULL CONTENT" in direct.content


@pytest.mark.parametrize("mutation", ["title", "name", "retrievable"])
async def test_stale_document_save_cannot_restore_read_access(stored_services: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, mutation: str) -> None:
    service = stored_services.metadata
    store = service.metadata_store
    arrived, resume = asyncio.Event(), asyncio.Event()
    save_metadata = store.save_metadata

    async def paused_save(metadata: DocumentMetadata, session: AsyncSession | None = None) -> None:
        if metadata.identity.last_modified_by == "stale-editor":
            assert metadata.tags.tag_ids == [A, B]
            arrived.set()
            await resume.wait()
        await save_metadata(metadata, session=session)

    monkeypatch.setattr(store, "save_metadata", paused_save)
    if mutation == "title":
        update = service.update_document_title(EDITOR, DOCUMENT, "Renamed", "stale-editor")
    elif mutation == "name":
        update = service.rename_document(EDITOR, DOCUMENT, "renamed.csv", "stale-editor")
    else:
        update = service.update_document_retrievable(EDITOR, DOCUMENT, False, "stale-editor")
    pending = asyncio.create_task(update)
    try:
        await asyncio.wait_for(arrived.wait(), timeout=5)
        items = DocumentTagItemService.__new__(DocumentTagItemService)
        items.document_metadata_service = service
        await items.remove_tag_id_from_item(EDITOR, DOCUMENT, A)
        assert (await store.get_metadata_by_uid(DOCUMENT)).tags.tag_ids == [B]
        assert stored_services.rebac.parents[DOCUMENT] == {B}
    finally:
        resume.set()
        await pending

    persisted = await store.get_metadata_by_uid(DOCUMENT)
    assert set(persisted.tags.tag_ids) == {A, B}
    assert stored_services.rebac.parents[DOCUMENT] == {B}
    if mutation == "title":
        assert persisted.identity.title == "Renamed"
    elif mutation == "name":
        assert persisted.document_name == "renamed.csv"
    else:
        assert persisted.source.retrievable is False
    with pytest.raises(PermissionError):
        await service.get_document_metadata(READER_A, DOCUMENT)
    assert (await service.get_document_metadata(READER_B, DOCUMENT)).document_uid == DOCUMENT
    for surface in DOCUMENT_SURFACES:
        await _assert_document_surface(stored_services, READER_A, surface)
        await _assert_document_surface(stored_services, READER_B, surface)


@pytest.mark.parametrize("mutation", ["name", "content"])
async def test_stale_resource_save_cannot_restore_full_content_access(stored_services: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, mutation: str) -> None:
    service = stored_services.resources
    store = service._resource_store
    arrived, resume = asyncio.Event(), asyncio.Event()
    update_resource = store.update_resource
    payload = ResourceUpdate(name="Renamed") if mutation == "name" else ResourceUpdate(content="CHANGED CONFIDENTIAL FULL CONTENT")

    async def paused_update(resource_id: str, resource: Resource, session: AsyncSession | None = None) -> Resource:
        if resource.name == "Renamed" or resource.content.startswith("CHANGED"):
            assert resource.library_tags == [A, B]
            arrived.set()
            await resume.wait()
        return await update_resource(resource_id, resource, session=session)

    monkeypatch.setattr(store, "update_resource", paused_update)
    pending = asyncio.create_task(service.update(resource_id=RESOURCE, payload=payload, user=EDITOR))
    try:
        await asyncio.wait_for(arrived.wait(), timeout=5)
        items = ResourceTagItemService.__new__(ResourceTagItemService)
        items.resource_service = service
        await items.remove_tag_id_from_item(EDITOR, RESOURCE, A)
        assert (await store.get_resource_by_id(RESOURCE)).library_tags == [B]
        assert stored_services.rebac.parents[RESOURCE] == {B}
    finally:
        resume.set()
        await pending

    persisted = await store.get_resource_by_id(RESOURCE)
    assert set(persisted.library_tags) == {A, B}
    assert stored_services.rebac.parents[RESOURCE] == {B}
    assert getattr(persisted, mutation) == getattr(payload, mutation)
    await _assert_resource_visibility(stored_services)


@pytest.mark.parametrize("surface", [*DOCUMENT_SURFACES, "resources"])
async def test_historical_sql_parent_drift_never_authorizes_a_read(stored_services: SimpleNamespace, surface: str) -> None:
    stored_services.rebac.parents[DOCUMENT] = {B}
    stored_services.rebac.parents[RESOURCE] = {B}
    assert set((await stored_services.metadata.metadata_store.get_metadata_by_uid(DOCUMENT)).tags.tag_ids) == {A, B}
    assert set((await stored_services.resources._resource_store.get_resource_by_id(RESOURCE)).library_tags) == {A, B}
    if surface == "resources":
        await _assert_resource_visibility(stored_services)
    else:
        await _assert_document_surface(stored_services, READER_A, surface)
        await _assert_document_surface(stored_services, READER_B, surface)


@pytest.mark.parametrize("surface", [*DOCUMENT_SURFACES, "resources"])
async def test_listing_propagates_authorization_failure(stored_services: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, surface: str) -> None:
    monkeypatch.setattr(stored_services.rebac, "has_user_permission", AsyncMock(side_effect=RuntimeError("Authorization backend unavailable")))
    with pytest.raises(RuntimeError, match="Authorization backend unavailable"):
        if surface == "resources":
            await stored_services.resources.list_resources_by_kind(kind=ResourceKind.PROMPT, user=READER_A)
        else:
            await _assert_document_surface(stored_services, READER_A, surface)


@pytest.mark.parametrize("surface", ["documents", "resources", "tabular-datasets"])
async def test_listing_bounds_concurrent_authorization_checks(stored_services: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, surface: str) -> None:
    services = stored_services
    for index in range(23):
        uid = f"candidate-{index:02d}"
        services.rebac.parents[uid] = {A}
        if surface == "resources":
            resource = (await services.resources._resource_store.get_resource_by_id(RESOURCE)).model_copy(update={"id": uid})
            await services.resources._resource_store.create_resource(resource)
        else:
            await services.metadata.metadata_store.save_metadata(_doc(uid, [A], tabular=surface == "tabular-datasets"))
    active = maximum = calls = 0
    saturated, resume = asyncio.Event(), asyncio.Event()
    has_permission = services.rebac.has_user_permission

    async def paused_check(user: SimpleNamespace, permission: DocumentPermission | ResourcePermission, uid: str) -> bool:
        nonlocal active, maximum, calls
        assert permission is (ResourcePermission.READ if surface == "resources" else DocumentPermission.READ)
        calls += 1
        active += 1
        maximum = max(maximum, active)
        if active == 10:
            saturated.set()
        try:
            await resume.wait()
            return await has_permission(user, permission, uid)
        finally:
            active -= 1

    monkeypatch.setattr(services.rebac, "has_user_permission", paused_check)
    if surface == "resources":
        listing = services.resources.list_resources_by_kind(kind=ResourceKind.PROMPT, user=READER_A)
    elif surface == "documents":
        listing = services.metadata.get_documents_metadata(READER_A, {})
    else:
        listing = services.tabular.list_datasets(READER_A)
    pending = asyncio.create_task(listing)
    try:
        await asyncio.wait_for(saturated.wait(), timeout=5)
        assert maximum == 10
    finally:
        resume.set()
        await pending
    assert calls == (24 if surface == "resources" else 26)
    assert maximum == 10
