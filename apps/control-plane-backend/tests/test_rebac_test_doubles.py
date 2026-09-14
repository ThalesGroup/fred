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

"""The counting double must model removal, not just report that it happened.

A double whose delete leaves its read-state intact makes a cleanup assertion
pass against an engine that removed nothing.
"""

from __future__ import annotations

import pytest
from fred_core import RebacReference, Relation, RelationType, Resource
from tests._rebac_test_doubles import CountingRebacEngine

_APP = RebacReference(Resource.APP, "reporting")
_OTHER_APP = RebacReference(Resource.APP, "planning")
_TEAM = RebacReference(Resource.TEAM, "team-0")


def _grant(resource: RebacReference) -> Relation:
    return Relation(subject=_TEAM, relation=RelationType.ENABLED, resource=resource)


@pytest.mark.asyncio
async def test_delete_relation_removes_it_from_subsequent_reads() -> None:
    grant = _grant(_APP)
    engine = CountingRebacEngine(direct_relations=[grant])

    assert await engine.list_direct_relations(_APP) == [grant]

    await engine.delete_relation(grant)

    assert await engine.list_direct_relations(_APP) == []
    assert engine.deleted_relations == [grant]


@pytest.mark.asyncio
async def test_reference_cleanup_removes_only_that_reference() -> None:
    removed = _grant(_APP)
    retained = _grant(_OTHER_APP)
    engine = CountingRebacEngine(direct_relations=[removed, retained])

    await engine.delete_all_relations_of_reference(_APP)

    assert await engine.list_direct_relations(_APP) == []
    assert await engine.list_direct_relations(_OTHER_APP) == [retained]
    assert engine.deleted_reference_calls == [_APP]
    assert engine.deleted_relations == [removed]


@pytest.mark.asyncio
async def test_reference_cleanup_matches_the_subject_side_too() -> None:
    membership = Relation(subject=_TEAM, relation=RelationType.ENABLED, resource=_APP)
    engine = CountingRebacEngine(direct_relations=[membership])

    await engine.delete_all_relations_of_reference(_TEAM)

    assert await engine.list_direct_relations(_APP) == []
    assert engine.deleted_relations == [membership]
