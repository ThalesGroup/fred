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

"""Search scope and candidate verification decisions, on rows built in memory.

The SQL schema belongs to the Control Plane migrations; no database is used here.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID, uuid4, uuid5

import pytest
from fred_core.documents.access import (
    Candidate,
    SearchScope,
    SpaceNotFoundError,
    SpacePendingDeletionError,
    filter_candidates,
    scope_from_space,
    verify_candidates,
)
from sqlalchemy.ext.asyncio import AsyncConnection

ORG, TEAM, PROJECT, PERSONAL = uuid4(), uuid4(), uuid4(), uuid4()


def space(id: UUID, parent: UUID | None, organization: UUID) -> dict[str, Any]:
    return {
        "id": id,
        "parent_id": parent,
        "organization_id": organization,
        "deletion_id": None,
    }


@pytest.mark.parametrize(
    ("row", "path"),
    [
        (space(ORG, None, ORG), (ORG,)),
        (space(TEAM, ORG, ORG), (ORG, TEAM)),
        (space(PROJECT, TEAM, ORG), (ORG, TEAM, PROJECT)),
        (space(PERSONAL, None, ORG), (PERSONAL,)),
    ],
)
def test_scope_is_the_space_and_its_ancestors(
    row: dict[str, Any], path: tuple[UUID, ...]
) -> None:
    assert scope_from_space(row["id"], row) == SearchScope(space_ids=path)


def test_missing_and_deleting_spaces_are_distinct_errors() -> None:
    with pytest.raises(SpaceNotFoundError):
        scope_from_space(TEAM, None)
    with pytest.raises(SpacePendingDeletionError):
        scope_from_space(TEAM, {**space(TEAM, ORG, ORG), "deletion_id": uuid4()})


GENERATION = uuid4()
SCOPE = SearchScope(space_ids=(ORG, TEAM))


def chunk(ordinal: int, generation: UUID = GENERATION) -> str:
    return str(uuid5(generation, str(ordinal)))


def document(**changes: Any) -> dict[str, Any]:
    row = {
        "id": uuid4(),
        "space_id": TEAM,
        "deletion_id": None,
        "space_deletion_id": None,
        "retrievable": True,
        "retrievable_pending": False,
        "generation_id": GENERATION,
        "vector_ordinals": [0, 2, 5],
    }
    return {**row, **changes}


def kept(row: dict[str, Any], chunk_uid: str = chunk(2)) -> list[Candidate]:
    return filter_candidates(SCOPE, [Candidate(str(row["id"]), chunk_uid)], [row])


def test_published_in_scope_chunk_is_kept() -> None:
    row = document()
    assert kept(row) == [Candidate(str(row["id"]), chunk(2))]


@pytest.mark.parametrize(
    "changes",
    [
        {"space_id": PROJECT},
        {"deletion_id": uuid4()},
        {"space_deletion_id": uuid4()},
        {"retrievable": False},
        {"retrievable_pending": True},
        {"generation_id": None, "vector_ordinals": None},
    ],
    ids=[
        "out-of-scope",
        "retired",
        "space-deleting",
        "not-retrievable",
        "inclusion-pending",
        "unpublished",
    ],
)
def test_document_facts_reject_the_candidate(changes: dict[str, Any]) -> None:
    assert kept(document(**changes)) == []


def test_chunk_of_another_generation_is_dropped() -> None:
    assert kept(document(), chunk(2, uuid4())) == []


def test_ordinal_outside_the_published_vectors_is_dropped() -> None:
    assert kept(document(), chunk(1)) == []


def test_unknown_or_malformed_document_is_dropped() -> None:
    row = document()
    candidates = [Candidate("not-a-uuid", chunk(2)), Candidate(str(uuid4()), chunk(2))]
    assert filter_candidates(SCOPE, candidates, [row]) == []


def test_candidate_order_is_preserved() -> None:
    first, second = document(), document(space_id=ORG)
    candidates = [
        Candidate(str(second["id"]), chunk(5)),
        Candidate(str(first["id"]), chunk(1)),
        Candidate(str(first["id"]), chunk(0)),
        Candidate(str(second["id"]), chunk(0)),
    ]
    assert filter_candidates(SCOPE, candidates, [first, second]) == [
        candidates[0],
        candidates[2],
        candidates[3],
    ]


class FailingConnection:
    async def execute(self, *_: Any) -> Any:
        raise RuntimeError("database unavailable")


@pytest.mark.asyncio
async def test_database_failure_is_not_an_empty_result() -> None:
    conn = cast(AsyncConnection, FailingConnection())
    with pytest.raises(RuntimeError):
        await verify_candidates(conn, SCOPE, [Candidate(str(uuid4()), chunk(0))])


@pytest.mark.asyncio
async def test_no_valid_document_reads_nothing() -> None:
    conn = cast(AsyncConnection, FailingConnection())
    assert (
        await verify_candidates(conn, SCOPE, [Candidate("not-a-uuid", chunk(0))]) == []
    )
