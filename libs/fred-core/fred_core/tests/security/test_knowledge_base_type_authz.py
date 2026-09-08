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

"""
`fred_core.security.rebac.knowledge_base_type_authz` (docs/swift/rfc/KNOWLEDGE-BASE-RFC.md
§6) — mirrors `test_capability_authz.py`'s `can_team_use_capability` coverage
on the separate `knowledge_base_type` object type.
"""

from __future__ import annotations

import pytest

from fred_core.security.models import Resource
from fred_core.security.rebac.knowledge_base_type_authz import (
    can_team_use_knowledge_base_type,
)
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from fred_core.security.rebac.rebac_engine import (
    KnowledgeBaseTypePermission,
    RebacReference,
    RelationType,
)
from fred_core.tests.security.rebac_fakes import FakeRebacEngine


@pytest.mark.asyncio
async def test_can_team_use_knowledge_base_type_is_a_single_check_with_team_context() -> (
    None
):
    rebac = FakeRebacEngine(permitted=True)

    assert (
        await can_team_use_knowledge_base_type(
            rebac, "team-1", knowledge_base_type_id="local_fs_rag"
        )
        is True
    )
    assert rebac.checked == [
        (
            RebacReference(type=Resource.TEAM, id="team-1"),
            KnowledgeBaseTypePermission.CAN_USE,
            RebacReference(type=Resource.KNOWLEDGE_BASE_TYPE, id="local_fs_rag"),
        )
    ]
    assert [
        [c.relation for c in call] for call in rebac.checked_contextual_relations
    ] == [[RelationType.TEAM]]


@pytest.mark.asyncio
async def test_can_team_use_knowledge_base_type_reports_denial() -> None:
    rebac = FakeRebacEngine(permitted=False)

    assert (
        await can_team_use_knowledge_base_type(
            rebac, "team-1", knowledge_base_type_id="local_fs_rag"
        )
        is False
    )


@pytest.mark.asyncio
async def test_can_team_use_knowledge_base_type_allows_when_rebac_is_disabled() -> None:
    assert (
        await can_team_use_knowledge_base_type(
            NoopRebacEngine(), "team-1", knowledge_base_type_id="local_fs_rag"
        )
        is True
    )
