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

"""AUTHZ-05 §27: `/mcp/reports/write` must be team-scoped via a required
`tag_id`, and the resulting report document must get a real `tag` parent
relation — previously reports had no ReBAC team association at all (only the
free-text `tags` UI chips), so a report document was effectively unowned.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fred_core import KeycloakUser, RebacReference, Relation, RelationType, Resource, TagPermission, get_current_user

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.content import report_controller as report_module


class _FakeRebac:
    def __init__(self) -> None:
        self.checks: list[tuple[object, str]] = []
        self.relations_added: list[Relation] = []

    async def check_user_permission_or_raise(self, user, permission, resource_id, **_kw) -> None:
        self.checks.append((permission, resource_id))

    async def add_relation(self, relation: Relation) -> None:
        self.relations_added.append(relation)


@pytest.fixture
def report_client(monkeypatch, app_context: ApplicationContext):
    fake_rebac = _FakeRebac()
    monkeypatch.setattr(app_context, "get_rebac_engine", lambda: fake_rebac)

    app = FastAPI()
    app.include_router(report_module.router)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(uid="alice", username="alice", email=None, roles=[], groups=[])
    with TestClient(app) as client:
        yield client, fake_rebac


def test_write_report_requires_tag_id(report_client) -> None:
    client, fake_rebac = report_client

    response = client.post(
        "/mcp/reports/write",
        json={"title": "Q1 report", "markdown": "# Q1"},
    )

    assert response.status_code == 422
    assert fake_rebac.checks == []


def test_write_report_checks_tag_permission_and_creates_parent_relation(report_client) -> None:
    client, fake_rebac = report_client

    response = client.post(
        "/mcp/reports/write",
        json={"title": "Q1 report", "markdown": "# Q1", "tag_id": "tag-finance"},
    )

    assert response.status_code == 200
    assert fake_rebac.checks == [(TagPermission.UPDATE, "tag-finance")]

    document_uid = response.json()["document_uid"]
    assert fake_rebac.relations_added == [
        Relation(
            subject=RebacReference(Resource.TAGS, "tag-finance"),
            relation=RelationType.PARENT,
            resource=RebacReference(Resource.DOCUMENTS, document_uid),
        )
    ]
