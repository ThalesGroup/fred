# Copyright Thales 2026
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

"""`POST /documents/name-check` — the pre-upload conflict question.

What these pin: the answer is the subset of the asked names the destination
folder already holds, scoped to that folder and to nothing else, and the route
refuses exactly where an import into the same folder would.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fred_core import AuthorizationError, KeycloakUser, Resource, TeamPermission, get_current_user
from fred_core.common import register_exception_handlers
from fred_core.documents.document_structures import (
    DocumentMetadata,
    FileInfo,
    FileType,
    Identity,
    SourceInfo,
    SourceType,
    Tagging,
)

from knowledge_flow_backend.core.stores.tags.base_tag_store import TagNotFoundError
from knowledge_flow_backend.features.ingestion import ingestion_controller as ingestion_module
from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController

ROUTE = "/knowledge-flow/v1/documents/name-check"
_T = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _FakeRebac:
    """Grants team edit permission on `writable` teams only, and records what
    it was asked — a route checking the wrong permission still fails here."""

    def __init__(self, writable: set[str]) -> None:
        self.writable = writable
        self.calls: list[tuple[object, str]] = []

    async def check_user_permission_or_raise(self, user, permission, resource_id, **_kw) -> None:
        self.calls.append((permission, resource_id))
        if resource_id not in self.writable:
            raise AuthorizationError(user.uid, str(permission), Resource.TAGS)


class _FolderStore:
    async def get_tags_by_ids(self, tag_ids):
        return [SimpleNamespace(id=tag_id, owner_id="team-forbidden" if tag_id == "folder-forbidden" else "team-a", deletion_task_id=None) for tag_id in tag_ids]

    async def get_tag_by_id(self, tag_id):
        raise TagNotFoundError(tag_id)


def _doc(uid: str, name: str, tag_id: str) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name=name, document_uid=uid, title=name, author="a", created=_T, modified=_T, last_modified_by="a"),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="fred"),
        file=FileInfo(file_type=FileType.OTHER, file_name=name),
        tags=Tagging(tag_ids=[tag_id]),
    )


@pytest.fixture
def name_check_client(app_context, metadata_store, monkeypatch):
    """The ingestion router alone, with a folder the caller may write in
    ("folder-a"), one they may not ("folder-forbidden"), and documents seeded
    in two folders."""
    for uid, name, tag in [
        ("uid-report", "report.pdf", "folder-a"),
        ("uid-notes", "notes.md", "folder-a"),
        ("uid-elsewhere", "elsewhere.pdf", "folder-b"),
    ]:
        asyncio.run(metadata_store.save_metadata(_doc(uid, name, tag)))

    reads: list[str] = []
    held = metadata_store.document_uids_by_name_in_tag

    async def _recording_held(tag_id, names, session=None):
        reads.append(tag_id)
        return await held(tag_id, names, session=session)

    monkeypatch.setattr(metadata_store, "document_uids_by_name_in_tag", _recording_held)

    rebac = _FakeRebac(writable={"team-a"})
    monkeypatch.setattr(ingestion_module, "get_rebac_engine", lambda: rebac)
    # No folder here is a synchronized library; that guard has its own tests.
    app_context._tag_store_instance = _FolderStore()

    app = FastAPI()
    register_exception_handlers(app)
    router = APIRouter(prefix="/knowledge-flow/v1")
    IngestionController(router)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(uid="alice", username="alice", email=None, roles=[])
    with TestClient(app) as client:
        client.rebac = rebac  # type: ignore[attr-defined]
        client.reads = reads  # type: ignore[attr-defined]
        yield client


def test_returns_only_the_names_the_folder_already_holds(name_check_client: TestClient) -> None:
    response = name_check_client.post(
        ROUTE,
        json={"destinations": [{"tag_id": "folder-a", "names": ["report.pdf", "brand-new.pdf", "notes.md", "report.pdf"]}]},
    )

    assert response.status_code == 200
    # In the order asked, each name once however often it was asked.
    assert response.json() == {"conflicts": [{"tag_id": "folder-a", "names": ["report.pdf", "notes.md"]}]}


def test_no_conflict_yields_an_empty_list(name_check_client: TestClient) -> None:
    response = name_check_client.post(
        ROUTE,
        json={"destinations": [{"tag_id": "folder-a", "names": ["brand-new.pdf", "another.md"]}]},
    )

    assert response.status_code == 200
    assert response.json() == {"conflicts": []}


def test_a_name_held_only_by_another_folder_is_not_a_conflict(name_check_client: TestClient) -> None:
    # The same name in a different folder is a legitimate second document, and
    # must not raise a question about this import.
    response = name_check_client.post(
        ROUTE,
        json={"destinations": [{"tag_id": "folder-a", "names": ["elsewhere.pdf"]}]},
    )

    assert response.status_code == 200
    assert response.json() == {"conflicts": []}


def test_several_destinations_are_answered_in_one_request(name_check_client: TestClient) -> None:
    # A dropped directory targets one folder per subdirectory; asking per
    # folder would cost one round trip each.
    response = name_check_client.post(
        ROUTE,
        json={
            "destinations": [
                {"tag_id": "folder-a", "names": ["report.pdf"]},
                {"tag_id": "folder-b", "names": ["elsewhere.pdf"]},
            ]
        },
    )

    assert response.status_code == 200
    assert name_check_client.rebac.calls == [(TeamPermission.CAN_UPDATE_RESOURCES, "team-a")]
    assert response.json() == {
        "conflicts": [
            {"tag_id": "folder-a", "names": ["report.pdf"]},
            {"tag_id": "folder-b", "names": ["elsewhere.pdf"]},
        ]
    }


def test_a_caller_without_write_access_learns_nothing(name_check_client: TestClient) -> None:
    response = name_check_client.post(
        ROUTE,
        json={"destinations": [{"tag_id": "folder-forbidden", "names": ["report.pdf"]}]},
    )

    assert response.status_code == 403
    assert "conflicts" not in response.json()
    assert name_check_client.rebac.calls == [(TeamPermission.CAN_UPDATE_RESOURCES, "team-forbidden")]  # type: ignore[attr-defined]


def test_every_destination_is_authorized_before_any_is_read(name_check_client: TestClient) -> None:
    # A caller holding one folder must not learn the contents of that folder
    # from a request that also names one they cannot write in.
    response = name_check_client.post(
        ROUTE,
        json={
            "destinations": [
                {"tag_id": "folder-a", "names": ["report.pdf"]},
                {"tag_id": "folder-forbidden", "names": ["report.pdf"]},
            ]
        },
    )

    assert response.status_code == 403
    assert name_check_client.reads == []  # type: ignore[attr-defined]
