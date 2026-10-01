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

"""Tabular inventories require explicit source-root or human team rights."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fred_core import KeycloakUser, RelationType
from fred_core.common import OwnerFilter

from knowledge_flow_backend.features.tabular.service import TabularService
from knowledge_flow_backend.features.tag.corpus_access import CorpusAccess
from knowledge_flow_backend.features.tag.tag_service import TagService
from tests.features.test_corpus_access import _folder
from tests.services.test_tabular_service import _ingest_csv


@pytest.mark.asyncio
@pytest.mark.parametrize("granted", [False, True])
async def test_service_role_requires_explicit_root_grant(tmp_path, metadata_store, granted):
    await _ingest_csv(tmp_path=tmp_path, metadata_store=metadata_store, document_uid="doc-team-a", file_name="a.csv", content="city,amount\nParis,10\n", tag_ids=["root"])
    await _ingest_csv(tmp_path=tmp_path, metadata_store=metadata_store, document_uid="doc-other", file_name="b.csv", content="city,amount\nLyon,20\n", tag_ids=["other"])
    rebac = AsyncMock()
    rebac.enabled = True
    rebac.has_direct_relation.side_effect = lambda subject, relation, resource: granted and resource.id == "root" and relation == RelationType.VIEWER
    folders = SimpleNamespace(list_by_owner=AsyncMock(return_value=[_folder("root"), _folder("other")]))
    tags = TagService.__new__(TagService)
    tags.corpus_access = CorpusAccess(rebac, folders)
    service = TabularService()
    service.tag_service = tags
    user = KeycloakUser(uid="source", username="source", roles=["service_agent"])
    datasets = await service.list_datasets(user, owner_filter=OwnerFilter.TEAM, team_id="team-a")
    assert [dataset.document_uid for dataset in datasets] == (["doc-team-a"] if granted else [])
    rebac.lookup_user_resources.assert_not_called()
    rebac.has_user_permission.assert_not_called()
    rebac.require_active_account.assert_awaited_once_with("source")


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1001, 5001])
async def test_human_tabular_listing_uses_one_team_decision_without_document_enumeration(tmp_path, metadata_store, count):
    template = await _ingest_csv(tmp_path=tmp_path, metadata_store=metadata_store, document_uid="doc-0", file_name="template.csv", content="city,amount\nParis,10\n", tag_ids=["root"])
    for index in range(1, count):
        metadata = template.model_copy(deep=True)
        metadata.identity.document_uid = f"doc-{index}"
        await metadata_store.save_metadata(metadata)
    rebac = AsyncMock()
    folders = SimpleNamespace(list_by_owner=AsyncMock(return_value=[_folder("root")]))
    tags = TagService.__new__(TagService)
    tags.corpus_access = CorpusAccess(rebac, folders)
    service = TabularService()
    service.tag_service = tags
    datasets = await service.list_datasets(KeycloakUser(uid="alice", username="alice", roles=[]), team_id="team-a")
    assert {dataset.document_uid for dataset in datasets} == {f"doc-{index}" for index in range(count)}
    rebac.check_user_permission_or_raise.assert_awaited_once()
    rebac.lookup_user_resources.assert_not_called()
    rebac.has_user_permission.assert_not_called()
