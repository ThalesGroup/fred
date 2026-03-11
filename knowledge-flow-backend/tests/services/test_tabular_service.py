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
from pathlib import Path

import pandas as pd
import pytest
from fred_core import DocumentPermission, KeycloakUser, OwnerFilter, SQLTableStore, StoreInfo

from knowledge_flow_backend.common.document_structures import (
    DocumentMetadata,
    FileInfo,
    FileType,
    Identity,
    Processing,
    ProcessingStage,
    ProcessingStatus,
    SourceInfo,
    SourceType,
    Tagging,
)
from knowledge_flow_backend.features.tabular.registry_service import TabularRegistryService
from knowledge_flow_backend.features.tabular.service import TabularService

pytestmark = pytest.mark.asyncio


class DummyMetadataService:
    def __init__(self, visible_docs: dict[str, list[DocumentMetadata]]):
        self.visible_docs = visible_docs

    async def get_documents_metadata(self, user: KeycloakUser, _filters: dict) -> list[DocumentMetadata]:
        return [doc.model_copy(deep=True) for doc in self.visible_docs.get(user.uid, [])]


class DummyRebac:
    def __init__(self, permissions: dict[tuple[str, str], set[DocumentPermission]]):
        self.permissions = permissions

    async def check_user_permission_or_raise(self, user: KeycloakUser, permission: DocumentPermission, document_uid: str, **_kwargs) -> None:
        granted = self.permissions.get((user.uid, document_uid), set())
        if permission not in granted:
            raise PermissionError(f"{user.uid} cannot {permission.value} {document_uid}")


class DummyTagService:
    def __init__(self, authorized_tags: dict[tuple[str, OwnerFilter | None, str | None], set[str]]):
        self.authorized_tags = authorized_tags

    async def list_authorized_tags_ids(
        self,
        user: KeycloakUser,
        owner_filter: OwnerFilter | None,
        team_id: str | None,
    ) -> set[str]:
        return set(self.authorized_tags.get((user.uid, owner_filter, team_id), set()))


def _metadata(document_uid: str, document_name: str) -> DocumentMetadata:
    processing = Processing(stages={ProcessingStage.SQL_INDEXED: ProcessingStatus.DONE})
    return DocumentMetadata(
        identity=Identity(
            document_uid=document_uid,
            document_name=document_name,
            canonical_name=document_name,
            created=datetime.now(timezone.utc),
        ),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"),
        file=FileInfo(file_type=FileType.CSV, row_count=1),
        tags=Tagging(tag_ids=["tag-a"]),
        processing=processing,
    )


def _service(tmp_path, metadata_store, registry_store, visible_docs, permissions, authorized_tags=None):
    db_path = tmp_path / "tabular.sqlite"
    store = SQLTableStore(driver="sqlite", path=db_path)
    stores_info = {"tabular": StoreInfo(store=store, mode="read_and_write")}
    registry_service = TabularRegistryService(
        registry_store=registry_store,
        stores_info=stores_info,
        metadata_store=metadata_store,
    )
    service = TabularService(
        stores_info=stores_info,
        metadata_service=DummyMetadataService(visible_docs),
        registry_service=registry_service,
        tag_service=DummyTagService(authorized_tags or {}),
    )
    service.rebac = DummyRebac(permissions)
    return service, store, registry_service


async def _register_dataset(metadata_store, registry_service, store: SQLTableStore, metadata: DocumentMetadata, rows: list[dict]) -> str:
    await metadata_store.save_metadata(metadata)
    dataset = await registry_service.upsert_for_metadata(metadata, db_name="tabular", row_count=len(rows))
    store.save_table(dataset.physical_table_name, pd.DataFrame(rows))
    return dataset.query_alias


@pytest.fixture
def users():
    return {
        "alice": KeycloakUser(uid="alice", username="alice", email="alice@test.local", roles=["admin"], groups=[]),
        "bob": KeycloakUser(uid="bob", username="bob", email="bob@test.local", roles=["admin"], groups=[]),
    }


async def test_list_tables_returns_only_visible_aliases(tmp_path, metadata_store, app_context, users):
    alice_doc = _metadata("doc-alice", "sales.csv")
    bob_doc = _metadata("doc-bob", "sales.csv")

    service, store, registry_service = _service(
        tmp_path,
        metadata_store,
        app_context._tabular_dataset_registry_store_instance,
        visible_docs={"alice": [alice_doc], "bob": [bob_doc]},
        permissions={
            ("alice", "doc-alice"): {DocumentPermission.READ, DocumentPermission.UPDATE, DocumentPermission.DELETE},
            ("bob", "doc-bob"): {DocumentPermission.READ, DocumentPermission.UPDATE, DocumentPermission.DELETE},
        },
    )

    alice_alias = await _register_dataset(metadata_store, registry_service, store, alice_doc, [{"id": 1, "value": "alice"}])
    await _register_dataset(metadata_store, registry_service, store, bob_doc, [{"id": 2, "value": "bob"}])

    response = await service.list_tables(users["alice"], "tabular")

    assert response.tables == [alice_alias]
    assert response.datasets[0].document_uid == "doc-alice"


async def test_list_tables_respects_team_scope_tags(tmp_path, metadata_store, app_context, users):
    personal_doc = _metadata("doc-personal", "sales.csv")
    personal_doc.tags.tag_ids = ["tag-personal"]
    team_doc = _metadata("doc-team", "sales.csv")
    team_doc.tags.tag_ids = ["tag-team"]

    service, store, registry_service = _service(
        tmp_path,
        metadata_store,
        app_context._tabular_dataset_registry_store_instance,
        visible_docs={"alice": [personal_doc, team_doc]},
        permissions={
            ("alice", "doc-personal"): {DocumentPermission.READ, DocumentPermission.UPDATE, DocumentPermission.DELETE},
            ("alice", "doc-team"): {DocumentPermission.READ, DocumentPermission.UPDATE, DocumentPermission.DELETE},
        },
        authorized_tags={
            ("alice", None, None): {"tag-personal", "tag-team"},
            ("alice", OwnerFilter.PERSONAL, None): {"tag-personal"},
            ("alice", OwnerFilter.TEAM, "team-1"): {"tag-team"},
        },
    )

    personal_alias = await _register_dataset(metadata_store, registry_service, store, personal_doc, [{"id": 1, "value": "personal"}])
    team_alias = await _register_dataset(metadata_store, registry_service, store, team_doc, [{"id": 2, "value": "team"}])

    team_response = await service.list_tables(
        users["alice"],
        "tabular",
        owner_filter=OwnerFilter.TEAM,
        team_id="team-1",
    )
    personal_response = await service.list_tables(
        users["alice"],
        "tabular",
        owner_filter=OwnerFilter.PERSONAL,
    )

    assert team_response.tables == [team_alias]
    assert personal_response.tables == [personal_alias]


async def test_query_read_supports_joins_across_visible_aliases(tmp_path, metadata_store, app_context, users):
    left = _metadata("doc-left", "customers.csv")
    right = _metadata("doc-right", "orders.csv")
    visible_docs = {"alice": [left, right]}
    permissions = {
        ("alice", "doc-left"): {DocumentPermission.READ, DocumentPermission.UPDATE, DocumentPermission.DELETE},
        ("alice", "doc-right"): {DocumentPermission.READ, DocumentPermission.UPDATE, DocumentPermission.DELETE},
    }
    service, store, registry_service = _service(
        tmp_path,
        metadata_store,
        app_context._tabular_dataset_registry_store_instance,
        visible_docs=visible_docs,
        permissions=permissions,
    )

    left_alias = await _register_dataset(metadata_store, registry_service, store, left, [{"id": 1, "name": "Ada"}])
    right_alias = await _register_dataset(metadata_store, registry_service, store, right, [{"id": 1, "amount": 42}])

    result = await service.query_read(
        users["alice"],
        "tabular",
        f'SELECT c.id, c.name, o.amount FROM {left_alias} c JOIN {right_alias} o ON c.id = o.id',
    )

    assert result.rows == [{"id": 1, "name": "Ada", "amount": 42}]


async def test_query_read_rejects_unauthorized_or_physical_table_names(tmp_path, metadata_store, app_context, users):
    allowed = _metadata("doc-allowed", "allowed.csv")
    hidden = _metadata("doc-hidden", "hidden.csv")
    service, store, registry_service = _service(
        tmp_path,
        metadata_store,
        app_context._tabular_dataset_registry_store_instance,
        visible_docs={"alice": [allowed]},
        permissions={
            ("alice", "doc-allowed"): {DocumentPermission.READ, DocumentPermission.UPDATE, DocumentPermission.DELETE},
        },
    )

    allowed_alias = await _register_dataset(metadata_store, registry_service, store, allowed, [{"id": 1}])
    hidden_alias = await _register_dataset(metadata_store, registry_service, store, hidden, [{"id": 2}])
    hidden_dataset = await registry_service.get_by_query_alias(hidden_alias)
    assert hidden_dataset is not None

    with pytest.raises(ValueError, match="Invalid or unauthorized table name"):
        await service.query_read(
            users["alice"],
            "tabular",
            f"SELECT * FROM {allowed_alias} a JOIN {hidden_alias} h ON a.id = h.id",
        )

    with pytest.raises(ValueError, match="Physical table names are not allowed"):
        await service.query_read(
            users["alice"],
            "tabular",
            f'SELECT * FROM "{hidden_dataset.physical_table_name}"',
        )


async def test_query_read_rejects_tables_outside_requested_team_scope(tmp_path, metadata_store, app_context, users):
    personal = _metadata("doc-personal", "personal.csv")
    personal.tags.tag_ids = ["tag-personal"]
    team = _metadata("doc-team", "team.csv")
    team.tags.tag_ids = ["tag-team"]

    service, store, registry_service = _service(
        tmp_path,
        metadata_store,
        app_context._tabular_dataset_registry_store_instance,
        visible_docs={"alice": [personal, team]},
        permissions={
            ("alice", "doc-personal"): {DocumentPermission.READ, DocumentPermission.UPDATE, DocumentPermission.DELETE},
            ("alice", "doc-team"): {DocumentPermission.READ, DocumentPermission.UPDATE, DocumentPermission.DELETE},
        },
        authorized_tags={
            ("alice", None, None): {"tag-personal", "tag-team"},
            ("alice", OwnerFilter.TEAM, "team-1"): {"tag-team"},
        },
    )

    personal_alias = await _register_dataset(metadata_store, registry_service, store, personal, [{"id": 1}])
    team_alias = await _register_dataset(metadata_store, registry_service, store, team, [{"id": 2}])

    with pytest.raises(ValueError, match="Invalid or unauthorized table name"):
        await service.query_read(
            users["alice"],
            "tabular",
            f"SELECT * FROM {personal_alias}",
            owner_filter=OwnerFilter.TEAM,
            team_id="team-1",
        )

    result = await service.query_read(
        users["alice"],
        "tabular",
        f"SELECT * FROM {team_alias}",
        owner_filter=OwnerFilter.TEAM,
        team_id="team-1",
    )

    assert result.rows == [{"id": 2}]


async def test_query_write_updates_authorized_dataset_and_blocks_create_table(tmp_path, metadata_store, app_context, users):
    target = _metadata("doc-target", "inventory.csv")
    service, store, registry_service = _service(
        tmp_path,
        metadata_store,
        app_context._tabular_dataset_registry_store_instance,
        visible_docs={"alice": [target]},
        permissions={
            ("alice", "doc-target"): {DocumentPermission.READ, DocumentPermission.UPDATE, DocumentPermission.DELETE},
        },
    )

    target_alias = await _register_dataset(metadata_store, registry_service, store, target, [{"id": 1, "value": "old"}])

    await service.query_write(
        users["alice"],
        "tabular",
        f"INSERT INTO {target_alias} (id, value) VALUES (2, 'new')",
    )

    dataset = await registry_service.get_by_query_alias(target_alias)
    assert dataset is not None
    refreshed = await registry_service.refresh_row_count(dataset.document_uid)
    assert refreshed is not None
    assert refreshed.row_count == 2

    with pytest.raises(ValueError):
        await service.query_write(
            users["alice"],
            "tabular",
            "CREATE TABLE orphan_table (id INTEGER)",
        )


async def test_delete_table_removes_registry_and_physical_table(tmp_path, metadata_store, app_context, users):
    target = _metadata("doc-delete", "cleanup.csv")
    service, store, registry_service = _service(
        tmp_path,
        metadata_store,
        app_context._tabular_dataset_registry_store_instance,
        visible_docs={"alice": [target]},
        permissions={
            ("alice", "doc-delete"): {DocumentPermission.READ, DocumentPermission.UPDATE, DocumentPermission.DELETE},
        },
    )

    alias = await _register_dataset(metadata_store, registry_service, store, target, [{"id": 1}])
    dataset = await registry_service.get_by_query_alias(alias)
    assert dataset is not None

    await service.delete_table(users["alice"], "tabular", alias)

    assert await registry_service.get_by_query_alias(alias) is None
    assert dataset.physical_table_name not in set(store.list_tables())
