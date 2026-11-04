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

"""Router tests: session state, download (.docx) and preview (PDF), offline
- the store is the fake, the template fetch and the KF PDF conversion are
stubbed."""

from __future__ import annotations

import asyncio

import pytest
from conftest import form_document, load, to_bytes
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fred_capability_word_template import router as router_module
from fred_capability_word_template import store as store_module
from fred_capability_word_template.router import build_router
from fred_capability_word_template.session_document import save_snapshot
from fred_capability_word_template.store import BaseRef, Writer
from fred_core import KeycloakUser, get_current_user
from port_fakes import FakeWordTemplateStore

_PREFIX = "/capabilities/word_template"
_AUTH = {"Authorization": "Bearer token-1"}


@pytest.fixture()
def client(monkeypatch, form_bytes):
    fake = FakeWordTemplateStore()
    store_module.set_store_provider(lambda: fake)
    fetched: list[dict] = []

    async def fetch(**kwargs):
        fetched.append(kwargs)
        return form_bytes if kwargs["template_key"] == "tpl" else None

    monkeypatch.setattr(router_module, "_fetch_template_bytes", fetch)
    app = FastAPI()
    app.include_router(build_router(), prefix=_PREFIX)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(
        uid="u-1", username="u-1", roles=[]
    )
    try:
        yield TestClient(app), fake, fetched
    finally:
        store_module.clear_store_provider()


def _seed(
    fake: FakeWordTemplateStore, *, key: str = "tpl", instance: str | None = "a-1"
):
    writer = Writer(user_id="u-1", team_id="team-1", agent_instance_id=instance)
    asyncio.run(
        fake.append_batch(
            "s-1",
            BaseRef("template", key),
            [{"op": "set_text", "address": "T1.R1.C2", "text": "Week 41"}],
            writer,
            expected_count=0,
        )
    )


def test_session_state(client):
    http, fake, _ = client
    assert http.get(f"{_PREFIX}/sessions/s-1").json()["edit_count"] == 0
    _seed(fake)
    body = http.get(f"{_PREFIX}/sessions/s-1").json()
    assert body["template_key"] == "tpl" and body["pinned"] is True
    assert body["edit_count"] == 1


def test_download_replays_the_log_on_the_pinned_template(client):
    http, fake, fetched = client
    _seed(fake)
    response = http.get(f"{_PREFIX}/sessions/s-1/document.docx", headers=_AUTH)
    assert response.status_code == 200
    assert response.headers["content-disposition"].endswith('.docx"')
    document = load(response.content)
    assert document.tables[0].cell(0, 1).text == "Week 41"
    assert fetched == [
        {
            "team_id": "team-1",
            "agent_instance_id": "a-1",
            "template_key": "tpl",
            "access_token": "token-1",
        }
    ]
    # The replay is persisted: the next refresh does not redo it.
    assert fake.snapshots["s-1"].seq == 1


def test_download_uses_the_session_snapshot(client):
    http, fake, fetched = client
    _seed(fake)
    marker = form_document()
    marker.tables[0].cell(0, 1).text = "From the snapshot"
    asyncio.run(
        save_snapshot(
            "s-1",
            BaseRef("template", "tpl"),
            asyncio.run(fake.list_batches("s-1")),
            to_bytes(marker),
        )
    )
    response = http.get(f"{_PREFIX}/sessions/s-1/document.docx", headers=_AUTH)
    assert response.status_code == 200
    assert load(response.content).tables[0].cell(0, 1).text == "From the snapshot"
    assert fetched == []  # neither the template fetch nor a replay


def test_download_unknown_session_is_404(client):
    http, _fake, _ = client
    response = http.get(f"{_PREFIX}/sessions/nope/document.docx", headers=_AUTH)
    assert response.status_code == 404


def test_download_without_agent_instance_or_template_is_409(client):
    http, fake, _ = client
    _seed(fake, instance=None)
    assert (
        http.get(f"{_PREFIX}/sessions/s-1/document.docx", headers=_AUTH).status_code
        == 409
    )
    fake.sessions.clear()
    fake.batches.clear()
    _seed(fake, key="gone")
    response = http.get(f"{_PREFIX}/sessions/s-1/document.docx", headers=_AUTH)
    assert response.status_code == 409


def test_preview_converts_in_the_pod(client, monkeypatch):
    http, fake, _ = client
    _seed(fake)
    converted: list[bytes] = []

    async def convert(data, *, suffix):
        assert suffix == ".docx"
        converted.append(data)
        return b"%PDF-1.7 fake"

    monkeypatch.setattr(router_module, "convert_office_bytes_to_pdf", convert)
    response = http.get(f"{_PREFIX}/sessions/s-1/preview.pdf", headers=_AUTH)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-1.7 fake"
    assert load(converted[0]).tables[0].cell(0, 1).text == "Week 41"


def test_preview_conversion_failure_is_502(client, monkeypatch):
    http, fake, _ = client
    _seed(fake)

    async def convert(data, *, suffix):
        return None

    monkeypatch.setattr(router_module, "convert_office_bytes_to_pdf", convert)
    response = http.get(f"{_PREFIX}/sessions/s-1/preview.pdf", headers=_AUTH)
    assert response.status_code == 502
