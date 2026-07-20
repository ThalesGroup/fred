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

"""service_agent recognition in tabular dataset authorization (RFC EVAL-AUTH, Solution A).

The evaluation worker (service_agent) must read the TEAM's tabular corpus, scoped to
team_id, even though it holds no per-user document relations — mirrors
test_tag_service_service_agent.py, one layer up (documents instead of tags).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fred_core import KeycloakUser
from fred_core.common import OwnerFilter

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.tabular.service import TabularService
from tests.services.test_tabular_service import _FakeRebac, _FakeTagService, _ingest_csv


def _user(roles: list[str]) -> KeycloakUser:
    return KeycloakUser(uid="u", username="u", email="u@example.com", roles=roles)


@pytest.mark.asyncio
async def test_service_agent_sees_team_dataset_despite_empty_user_baseline(tmp_path: Path, metadata_store):
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    await _ingest_csv(
        tmp_path=tmp_path,
        metadata_store=metadata_store,
        document_uid="doc-team-a",
        file_name="sales-team-a.csv",
        content="city,amount\nParis,10\n",
        tag_ids=["tag-team-a"],
        tag_names=["Team A"],
    )

    service = TabularService()
    # A service_agent holds zero per-user document relations by design.
    service.rebac = _FakeRebac(set())
    service.tag_service = _FakeTagService(
        readable_tag_ids=set(),
        team_scopes={"team-a": {"tag-team-a"}},
    )

    datasets = await service.list_datasets(
        _user(["service_agent"]),
        owner_filter=OwnerFilter.TEAM,
        team_id="team-a",
    )
    assert [dataset.document_uid for dataset in datasets] == ["doc-team-a"]

    schema = await service.describe_dataset(
        _user(["service_agent"]),
        "doc-team-a",
        owner_filter=OwnerFilter.TEAM,
        team_id="team-a",
    )
    assert schema.document_uid == "doc-team-a"


@pytest.mark.asyncio
async def test_service_agent_without_team_fails_closed(tmp_path: Path, metadata_store):
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    await _ingest_csv(
        tmp_path=tmp_path,
        metadata_store=metadata_store,
        document_uid="doc-team-a",
        file_name="sales-team-a.csv",
        content="city,amount\nParis,10\n",
        tag_ids=["tag-team-a"],
        tag_names=["Team A"],
    )

    service = TabularService()
    service.rebac = _FakeRebac(set())
    service.tag_service = _FakeTagService(
        readable_tag_ids=set(),
        team_scopes={"team-a": {"tag-team-a"}},
    )

    assert await service.list_datasets(_user(["service_agent"])) == []


@pytest.mark.asyncio
async def test_normal_user_still_uses_per_user_rebac_lookup(tmp_path: Path, metadata_store):
    content_store = ApplicationContext.get_instance().get_content_store()
    content_store.clear()

    await _ingest_csv(
        tmp_path=tmp_path,
        metadata_store=metadata_store,
        document_uid="doc-team-a",
        file_name="sales-team-a.csv",
        content="city,amount\nParis,10\n",
        tag_ids=["tag-team-a"],
        tag_names=["Team A"],
    )

    service = TabularService()
    # A regular user with no readable-document tuple must still be denied, even
    # though the team owns the tag — the service_agent bypass must not leak to them.
    service.rebac = _FakeRebac(set())
    service.tag_service = _FakeTagService(
        readable_tag_ids=set(),
        team_scopes={"team-a": {"tag-team-a"}},
    )

    assert (
        await service.list_datasets(
            _user(["viewer"]),
            owner_filter=OwnerFilter.TEAM,
            team_id="team-a",
        )
        == []
    )
