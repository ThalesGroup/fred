from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fred_core import AuthorizationError, KeycloakUser, RelationType, Resource, TagPermission, TeamPermission
from fred_core.documents.tag_models import TagRow
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import create_async_engine

from knowledge_flow_backend.core.stores.tags.postgres_tag_store import PostgresTagStore
from knowledge_flow_backend.features.tag.corpus_access import CorpusAccess
from knowledge_flow_backend.features.tag.structure import Tag, TagType
from knowledge_flow_backend.features.tag.tag_service import TagService


def _folder(uid="root", *, path=None, owner="team-a"):
    now = datetime.now(timezone.utc)
    return Tag(id=uid, name=uid, path=path, owner_id=owner, type=TagType.DOCUMENT, created_at=now, updated_at=now)


@pytest.mark.asyncio
@pytest.mark.parametrize("write", [False, True])
async def test_human_permission_uses_stored_team_and_never_public_profile_permission(write):
    user = KeycloakUser(uid="alice", username="alice", roles=[])
    rebac = AsyncMock()
    folders = AsyncMock()
    folders.get_tag_by_id.return_value = _folder(owner="stored-team")
    await CorpusAccess(rebac, folders).get_folder(user, "root", write=write)
    rebac.check_user_permission_or_raise.assert_awaited_once_with(user, TeamPermission.CAN_UPDATE_RESOURCES if write else TeamPermission.CAN_USE_TEAM_KNOWLEDGE_BASES, "stored-team")
    rebac.lookup_user_resources.assert_not_called()


@pytest.mark.asyncio
async def test_source_role_does_not_replace_exact_account_root_grant():
    folders = AsyncMock()
    folders.get_tag_by_id.return_value = _folder("child", path="root/nested")
    folders.get_by_owner_type_full_path.return_value = _folder()
    rebac = AsyncMock()

    async def direct_grant(subject, relation, resource):
        assert relation == RelationType.EDITOR and resource.id == "root"
        return subject.id == "source-a"

    rebac.has_direct_relation.side_effect = direct_grant
    access = CorpusAccess(rebac, folders)
    for uid in ["source-a", "source-b"]:
        user = KeycloakUser(uid=uid, username=uid, roles=["service_agent"])
        if uid == "source-a":
            await access.get_folder(user, "child", write=True)
        else:
            with pytest.raises(AuthorizationError):
                await access.get_folder(user, "child", write=True)
    rebac.lookup_user_resources.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [999, 1000, 1001, 5000])
async def test_team_listing_does_not_use_fga_inventory_or_scale_checks_with_folders(count):
    engine = create_async_engine("sqlite+aiosqlite://")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(TagRow.__table__.create)
            rows = []
            for i in range(count):
                tag = _folder(f"folder-{i:05d}")
                rows.append(dict(tag_id=tag.id, owner_id=tag.owner_id, name=tag.name, type=tag.type.value, doc=tag.model_dump(mode="json")))
            foreign = _folder("aaa-foreign", owner="team-b")
            rows.append(dict(tag_id=foreign.id, owner_id=foreign.owner_id, name=foreign.name, type=foreign.type.value, doc=foreign.model_dump(mode="json")))
            await connection.execute(insert(TagRow), rows)
        service = TagService.__new__(TagService)
        service._tag_store = PostgresTagStore(engine)
        service.rebac = AsyncMock()
        service.rebac.has_user_permission.return_value = True
        service.corpus_access = CorpusAccess(service.rebac, service._tag_store)
        metadata = AsyncMock()
        metadata.document_uids_by_tags.return_value = {}
        service.document_metadata_service = SimpleNamespace(metadata_store=metadata)
        user = KeycloakUser(uid="alice", username="alice", roles=[])
        result = await service.list_all_tags_for_user(user, team_id="team-a", limit=count + 1)
        assert len(result) == count
        assert all(tag.owner_id == "team-a" and TagPermission.SHARE not in tag.permissions for tag in result)
        service.rebac.check_user_permission_or_raise.assert_awaited_once_with(user, TeamPermission.CAN_USE_TEAM_KNOWLEDGE_BASES, "team-a")
        service.rebac.has_user_permission.assert_awaited_once_with(user, TeamPermission.CAN_UPDATE_RESOURCES, "team-a")
        service.rebac.lookup_user_resources.assert_not_called()
        service.rebac.lookup_resources.assert_not_called()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [999, 1000, 1001, 5000])
async def test_document_page_remains_complete_above_fga_document_limit(count):
    from fred_core.documents.document_models import DocumentMetadataRow
    from fred_core.documents.document_structures import DocumentMetadata, Identity, SourceInfo, SourceType
    from fred_core.documents.label_models import DocumentLabelRow
    from fred_core.documents.postgres_document_store import PostgresDocumentMetadataStore

    from knowledge_flow_backend.features.metadata.service import MetadataService

    engine = create_async_engine("sqlite+aiosqlite://")
    try:
        async with engine.begin() as connection:
            for table in (TagRow.__table__, DocumentMetadataRow.__table__, DocumentLabelRow.__table__):
                await connection.run_sync(table.create)
            for uid in ("selected", "other"):
                folder = _folder(uid, owner="team-a" if uid == "selected" else "team-b")
                await connection.execute(insert(TagRow), dict(tag_id=uid, owner_id=folder.owner_id, name=folder.name, type="document", doc=folder.model_dump(mode="json")))
            rows = []
            for i in range(count):
                uid = f"document-{i:05d}"
                metadata = DocumentMetadata(identity=Identity(document_uid=uid, document_name=f"{uid}.pdf"), source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"))
                rows.append(dict(document_uid=uid, kind="corpus", folder_id="selected" if i < 20 else "other", doc=metadata.model_dump(mode="json")))
            await connection.execute(insert(DocumentMetadataRow), rows)
            await connection.execute(insert(DocumentLabelRow), [{"document_uid": row["document_uid"], "label": "SHARED"} for row in rows])
        service = MetadataService.__new__(MetadataService)
        service.metadata_store = PostgresDocumentMetadataStore(engine)
        service.rebac = AsyncMock()
        service.rebac.lookup_user_resources.side_effect = AssertionError("FGA must never inventory corpus documents")
        service.corpus_access = CorpusAccess(service.rebac, PostgresTagStore(engine))
        user = KeycloakUser(uid="alice", username="alice", roles=[])
        documents, total = await service.browse_documents_in_tag(user, "selected", limit=20)
        assert total == 20 and len(documents) == 20
        assert {doc.document_uid for doc in documents} == {f"document-{i:05d}" for i in range(20)}
        service.rebac.check_user_permission_or_raise.assert_awaited_once_with(user, TeamPermission.CAN_USE_TEAM_KNOWLEDGE_BASES, "team-a")
        service.rebac.lookup_user_resources.assert_not_called()
        service.rebac.check_user_permission_or_raise.reset_mock()
        page, label_total = await service.get_documents_with_label_page(user, "SHARED", team_id="team-a", offset=10, limit=5)
        assert label_total == 20
        assert [doc.document_uid for doc in page] == [f"document-{i:05d}" for i in range(10, 15)]
        service.rebac.check_user_permission_or_raise.assert_awaited_once_with(user, TeamPermission.CAN_USE_TEAM_KNOWLEDGE_BASES, "team-a")
        service.rebac.has_user_permission.side_effect = lambda user, permission, team: team == "team-a"
        selected = await service.get_documents_by_uids(user, [f"document-{i:05d}" for i in range(count)])
        assert {doc.document_uid for doc in selected} == {f"document-{i:05d}" for i in range(20)}
        assert service.rebac.has_user_permission.await_count == 2
        assert {call.args[1] for call in service.rebac.has_user_permission.await_args_list} == {TeamPermission.CAN_USE_TEAM_KNOWLEDGE_BASES}
        service.rebac.lookup_user_resources.assert_not_called()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_generic_corpus_document_reads_never_expose_conversation_attachment():
    from fred_core.documents.document_structures import DocumentMetadata, Identity, SourceInfo, SourceType

    from knowledge_flow_backend.features.metadata.service import MetadataService

    attachment = DocumentMetadata(
        kind="attachment", identity=Identity(document_uid="attachment", document_name="chat.csv", uploaded_by="alice"), source=SourceInfo(source_type=SourceType.PUSH, source_tag="fast_ingest")
    )
    service = MetadataService.__new__(MetadataService)
    service.metadata_store = AsyncMock()
    service.metadata_store.get_metadata_by_uid.return_value = attachment
    service.metadata_store.get_metadata_by_uids.return_value = [attachment]
    folders = AsyncMock()
    service.corpus_access = CorpusAccess(AsyncMock(), folders)
    user = KeycloakUser(uid="alice", username="alice", roles=[])
    assert await service.get_documents_by_uids(user, ["attachment"]) == []
    with pytest.raises(AuthorizationError):
        await service.get_document_metadata(user, "attachment")
    folders.get_tag_by_id.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["original", "media", "artifact"])
async def test_content_reads_authorize_folder_team_once_before_storage(operation):
    from io import BytesIO
    from unittest.mock import Mock

    from fred_core.documents.document_structures import DocumentMetadata, Identity, SourceInfo, SourceType, Tagging

    from knowledge_flow_backend.features.content.content_service import ContentService

    metadata = DocumentMetadata(identity=Identity(document_uid="doc", document_name="report.pdf"), source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"), tags=Tagging(tag_ids=["root"]))
    folders = AsyncMock()
    folders.get_tag_by_id.return_value = _folder(owner="stored-team")
    rebac = AsyncMock()
    service = ContentService.__new__(ContentService)
    service.metadata_store = AsyncMock()
    service.metadata_store.get_metadata_by_uid.return_value = metadata
    service.corpus_access = CorpusAccess(rebac, folders)
    service.content_store = Mock()
    service.content_store.get_content.return_value = BytesIO(b"pdf")
    service.content_store.get_media.return_value = BytesIO(b"image")
    service.content_store.get_output_artifact.return_value = b"preview"
    user = KeycloakUser(uid="alice", username="alice", roles=[])

    if operation == "original":
        await service.get_original_content(user, "doc")
    elif operation == "media":
        await service.get_document_media(user, "doc", "page.png")
    else:
        await service.get_preview_artifact(user, "doc", "output.md")
    rebac.check_user_permission_or_raise.assert_awaited_once_with(user, TeamPermission.CAN_USE_TEAM_KNOWLEDGE_BASES, "stored-team")

    service.content_store.reset_mock()
    rebac.check_user_permission_or_raise.side_effect = AuthorizationError(user.uid, "read", Resource.TEAM)
    with pytest.raises(AuthorizationError):
        await service.get_original_content(user, "doc")
    assert service.content_store.mock_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["rename", "title", "retrievable"])
async def test_metadata_mutations_require_one_team_editor_check(operation):
    from fred_core.documents.document_structures import DocumentMetadata, Identity, SourceInfo, SourceType, Tagging

    from knowledge_flow_backend.features.metadata.service import MetadataService

    document = DocumentMetadata(identity=Identity(document_uid="doc", document_name="old.pdf"), source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"), tags=Tagging(tag_ids=["root"]))
    service = MetadataService.__new__(MetadataService)
    service.metadata_store = AsyncMock()
    service.metadata_store.get_metadata_by_uid.return_value = document
    service.metadata_store.get_metadata_in_tag.return_value = []
    rebac = AsyncMock()
    folders = AsyncMock()
    folders.get_tag_by_id.return_value = _folder()
    service.corpus_access = CorpusAccess(rebac, folders)
    user = KeycloakUser(uid="alice", username="alice", roles=[])

    async def mutate():
        if operation == "rename":
            await service.rename_document(user, "doc", "new.pdf", user.uid)
        elif operation == "title":
            await service.update_document_title(user, "doc", "new title", user.uid)
        else:
            await service.update_document_retrievable(user, "doc", False, user.uid)

    await mutate()
    rebac.check_user_permission_or_raise.assert_awaited_once_with(user, TeamPermission.CAN_UPDATE_RESOURCES, "team-a")
    service.metadata_store.save_metadata.assert_awaited_once()
    service.metadata_store.save_metadata.reset_mock()
    rebac.check_user_permission_or_raise.side_effect = AuthorizationError(user.uid, "update", Resource.TEAM)
    with pytest.raises(AuthorizationError):
        await mutate()
    service.metadata_store.save_metadata.assert_not_awaited()


@pytest.mark.parametrize("method,path", [("POST", "/tags/root/share"), ("DELETE", "/tags/root/share/alice"), ("GET", "/tags/root/members")])
def test_folder_sharing_routes_are_retired(method, path):
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient

    from knowledge_flow_backend.features.tag.tag_controller import TagController

    controller = TagController.__new__(TagController)
    controller.service = AsyncMock()
    router = APIRouter()
    controller._register_routes(router)
    app = FastAPI()
    app.include_router(router)
    assert TestClient(app).request(method, path).status_code == 404
    assert not any("/share" in route or "/members" in route for route in app.openapi()["paths"])
