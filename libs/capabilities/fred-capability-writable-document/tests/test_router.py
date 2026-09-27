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

"""Router tests: list/get/put/export happy paths + authz (404 missing, 403 foreign).

The auth dependency and the store are both overridden so the routes run offline:
`get_current_user` returns a chosen `KeycloakUser`, and the store is the in-memory fake.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fred_capability_writable_document import store as store_module
from fred_capability_writable_document.router import build_router
from fred_capability_writable_document.store import WritableDocumentRecord
from fred_core import KeycloakUser, get_current_user
from port_fakes import FakeWritableDocumentStore

_PREFIX = "/capabilities/writable_document"


def _user(uid: str) -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, roles=[])


def _seed(fake: FakeWritableDocumentStore, **overrides) -> None:
    record = WritableDocumentRecord(
        session_id=overrides.get("session_id", "s-1"),
        document_id=overrides.get("document_id", "doc-1"),
        user_id=overrides.get("user_id", "u-1"),
        title=overrides.get("title", "Report"),
        content_md=overrides.get("content_md", "# Report\n\nBody"),
        updated_by=overrides.get("updated_by", "agent"),
        agent_notified_at=overrides.get("agent_notified_at"),
        created_at=overrides.get("created_at"),
    )
    asyncio.run(fake.upsert(record))


@pytest.fixture()
def app_client():
    fake = FakeWritableDocumentStore()
    store_module.set_store_provider(lambda: fake)
    app = FastAPI()
    app.include_router(build_router(), prefix=_PREFIX)
    app.dependency_overrides[get_current_user] = lambda: _user("u-1")
    client = TestClient(app)
    try:
        yield client, fake, app
    finally:
        store_module.clear_store_provider()


def test_list_scopes_to_the_authenticated_user(app_client):
    client, fake, _app = app_client
    _seed(fake, document_id="mine-1", user_id="u-1", title="Mine 1")
    _seed(fake, document_id="mine-2", user_id="u-1", title="Mine 2")
    _seed(fake, document_id="theirs", user_id="u-2", title="Theirs")

    resp = client.get(f"{_PREFIX}/sessions/s-1/documents")
    assert resp.status_code == 200
    ids = sorted(d["document_id"] for d in resp.json())
    assert ids == ["mine-1", "mine-2"]


def test_get_returns_the_document(app_client):
    client, fake, _app = app_client
    _seed(fake)
    resp = client.get(f"{_PREFIX}/sessions/s-1/documents/doc-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == "doc-1"
    assert body["content_md"] == "# Report\n\nBody"
    assert body["updated_by"] == "agent"


def test_get_missing_is_404(app_client):
    client, _fake, _app = app_client
    resp = client.get(f"{_PREFIX}/sessions/s-1/documents/nope")
    assert resp.status_code == 404


def test_get_foreign_user_is_403(app_client):
    client, fake, _app = app_client
    _seed(fake, user_id="u-2")  # owned by someone else; auth is u-1
    resp = client.get(f"{_PREFIX}/sessions/s-1/documents/doc-1")
    assert resp.status_code == 403


def test_put_marks_user_and_clears_agent_notified_at(app_client):
    client, fake, _app = app_client
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _seed(
        fake,
        updated_by="agent",
        agent_notified_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        created_at=created,
    )

    resp = client.put(
        f"{_PREFIX}/sessions/s-1/documents/doc-1",
        json={"content_md": "user rewrote it", "title": "Report v2"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated_by"] == "user"
    assert body["content_md"] == "user rewrote it"
    assert body["title"] == "Report v2"
    # created_at preserved across the edit.
    assert body["created_at"].startswith("2026-01-01")

    # agent_notified_at cleared so the middleware re-notifies next turn.
    stored = asyncio.run(fake.get("s-1", "doc-1"))
    assert stored is not None
    assert stored.agent_notified_at is None


def test_put_foreign_user_is_403(app_client):
    client, fake, _app = app_client
    _seed(fake, user_id="u-2")
    resp = client.put(
        f"{_PREFIX}/sessions/s-1/documents/doc-1",
        json={"content_md": "hax"},
    )
    assert resp.status_code == 403


def test_export_docx(app_client):
    client, fake, _app = app_client
    _seed(fake, content_md="# Title\n\nBody", title="My Doc")
    resp = client.get(
        f"{_PREFIX}/sessions/s-1/documents/doc-1/export", params={"format": "docx"}
    )
    assert resp.status_code == 200
    assert (
        resp.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "My_Doc.docx" in resp.headers["content-disposition"]
    assert resp.content[:2] == b"PK"  # docx is a zip


def test_export_md_passthrough(app_client):
    client, fake, _app = app_client
    _seed(fake, content_md="# Title\n\nBody")
    resp = client.get(
        f"{_PREFIX}/sessions/s-1/documents/doc-1/export", params={"format": "md"}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert resp.text == "# Title\n\nBody"
