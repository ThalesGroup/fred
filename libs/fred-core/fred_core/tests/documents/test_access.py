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
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4, uuid5

import pytest
from fred_core.documents.access import (
    Candidate,
    PublishedArtifact,
    SearchScope,
    SpaceNotFoundError,
    SpacePendingDeletionError,
    filter_candidates,
    is_live_document,
    published_artifact,
    scope_from_space,
    verify_candidates,
)
from fred_core.documents.selection import DocumentScope
from fred_core.documents.transport import DocumentAccessContext
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
        "session_id": None,
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


def test_published_attachment_is_not_a_live_corpus_document() -> None:
    row = document(session_id=uuid4(), folder_id=None)
    candidate = Candidate(str(row["id"]), chunk(2))
    scope = SearchScope(
        space_ids=(TEAM,),
        document_scope=DocumentScope.from_ids(document_ids=[str(row["id"])]),
    )
    assert not is_live_document(row, scope.space_ids)
    assert filter_candidates(scope, [candidate], [row]) == []


@pytest.mark.asyncio
async def test_attachment_rejection_is_reported_without_an_extra_query(caplog) -> None:
    row = document(session_id=uuid4())
    conn = MagicMock(spec=AsyncConnection)
    conn.execute = AsyncMock(return_value=MagicMock())
    conn.execute.return_value.mappings.return_value.all.return_value = [row]
    with caplog.at_level("INFO", logger="fred_core.documents.access"):
        assert (
            await verify_candidates(conn, SCOPE, [Candidate(str(row["id"]), chunk(2))])
            == []
        )
    conn.execute.assert_awaited_once()
    record = next(
        r
        for r in caplog.records
        if getattr(r, "event_name", None) == "vector_visibility_checked"
    )
    assert record.document_rejection_facts == {"attachment": 1}


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


@pytest.mark.asyncio
@pytest.mark.parametrize("space_id", [ORG, TEAM])
async def test_published_artifact_uses_one_query(space_id: UUID) -> None:
    row = document(
        space_id=space_id, prefix="org/doc/output/generation/", size=42, sha256="a" * 64
    )
    conn = MagicMock(spec=AsyncConnection)
    conn.execute = AsyncMock(return_value=MagicMock())
    conn.execute.return_value.mappings.return_value.first.return_value = row
    artifact = await published_artifact(conn, SCOPE, row["id"], "output.md")
    assert artifact == PublishedArtifact(row["prefix"], 42, "a" * 64)
    conn.execute.assert_awaited_once()
    statement, params = conn.execute.call_args.args
    assert params == {"document_id": row["id"], "path": "output.md"}
    sql = str(statement)
    assert "g.id = d.published_generation" in sql
    assert "a.generation_id = g.id AND a.path = :path" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row",
    [
        None,
        document(space_id=PROJECT),
        document(space_id=PERSONAL),
        document(deletion_id=uuid4()),
        document(space_deletion_id=uuid4()),
        document(retrievable=False),
        document(retrievable_pending=True),
        document(retrievable_pending=None),
        document(session_id=uuid4()),
    ],
    ids=[
        "missing-document-generation-or-path",
        "out-of-scope",
        "personal",
        "retired",
        "space-deleting",
        "not-retrievable",
        "pending",
        "unknown-pending",
        "attachment",
    ],
)
async def test_published_artifact_refuses_invisible_or_absent_rows(
    row: dict[str, Any] | None,
) -> None:
    conn = MagicMock(spec=AsyncConnection)
    conn.execute = AsyncMock(return_value=MagicMock())
    conn.execute.return_value.mappings.return_value.first.return_value = row
    assert await published_artifact(conn, SCOPE, uuid4(), "output.md") is None
    conn.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_published_artifact_propagates_database_failure() -> None:
    with pytest.raises(RuntimeError, match="database unavailable"):
        await published_artifact(
            cast(AsyncConnection, FailingConnection()), SCOPE, uuid4(), "output.md"
        )


@pytest.mark.parametrize("source", ["folder", "explicit", "both"])
def test_selection_unions_direct_contents_and_explicit_documents(source: str) -> None:
    folder, other = uuid4(), uuid4()
    row = document(folder_id=folder)
    scope = SearchScope(
        space_ids=(TEAM,),
        document_scope=DocumentScope.from_ids(
            [str(folder)] if source != "explicit" else [],
            [str(row["id"])] if source != "folder" else [],
        ),
    )
    candidate = Candidate(str(row["id"]), chunk(2))
    assert filter_candidates(scope, [candidate], [row]) == [candidate]
    row["folder_id"] = other
    assert filter_candidates(scope, [candidate], [row]) == (
        [] if source == "folder" else [candidate]
    )


def test_folder_agent_and_document_turn_intersect_by_coverage() -> None:
    folder = uuid4()
    row = document(folder_id=folder)
    candidate = Candidate(str(row["id"]), chunk(2))
    agent = DocumentScope.from_ids([str(folder)])
    turn = DocumentScope.from_ids(document_ids=[str(row["id"])])
    scope = SearchScope(space_ids=(TEAM,), document_scope=agent.intersect(turn))
    assert filter_candidates(scope, [candidate], [row]) == [candidate]
    row["folder_id"] = uuid4()
    assert filter_candidates(scope, [candidate], [row]) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", [False, True])
async def test_known_id_cannot_bypass_published_artifact_selection(empty: bool) -> None:
    folder = uuid4()
    row = document(folder_id=folder, prefix="published/", size=42, sha256="a" * 64)
    scope = SearchScope(
        space_ids=(TEAM,),
        document_scope=DocumentScope.from_ids([] if empty else [str(uuid4())]),
    )
    conn = MagicMock(spec=AsyncConnection)
    conn.execute = AsyncMock(return_value=MagicMock())
    conn.execute.return_value.mappings.return_value.first.return_value = row
    assert await published_artifact(conn, scope, row["id"], "output.md") is None
    conn.execute.assert_awaited_once()


def test_empty_is_not_unrestricted_and_reset_keeps_agent_ceiling() -> None:
    folder, doc = uuid4(), uuid4()
    agent = DocumentScope.from_ids([str(folder)])
    empty = DocumentScope.from_ids(document_ids=[])
    assert not agent.intersect(empty).covers(doc, folder)
    reset = agent.intersect(DocumentScope.from_ids())
    assert reset.covers(doc, folder)
    assert not reset.covers(doc, uuid4())
    assert DocumentScope.model_validate_json(empty.model_dump_json()).is_empty


@pytest.mark.asyncio
async def test_folder_resolution_is_one_batched_query_without_document_enumeration() -> (
    None
):
    from fred_core.documents.access import resolve_scope

    folders = [uuid4(), uuid4()]
    conn = MagicMock(spec=AsyncConnection)
    space_result, folder_result = MagicMock(), MagicMock()
    space_result.mappings.return_value.first.return_value = space(TEAM, ORG, ORG)
    folder_result.mappings.return_value.all.return_value = [
        {"id": folders[0], "path": f"/{folders[0]}/"}
    ]
    conn.execute = AsyncMock(side_effect=[space_result, folder_result])
    scope = await resolve_scope(
        conn,
        DocumentAccessContext(
            space_id=TEAM,
            document_scope=DocumentScope.from_ids([str(id) for id in folders]),
        ),
        user_id="alice",
    )
    assert conn.execute.await_count == 2
    statement, params = conn.execute.call_args.args
    assert "FROM folder" in str(statement) and "FROM document" not in str(statement)
    assert set(params["folder_ids"]) == set(folders)
    assert scope.selection_terms == (
        {"folder_path": [f"/{folders[0]}/"], "document_uid": []},
    )
    assert not scope.document_scope.covers(uuid4(), folders[1])


CONVERSATION = uuid4()


def attachment_scope(
    *ids: UUID, selection: DocumentScope = DocumentScope()
) -> SearchScope:
    return SearchScope(
        space_ids=(ORG, TEAM),
        document_scope=selection,
        conversation_id=CONVERSATION,
        attachment_ids=ids,
        user_id="alice",
    )


def attachment(**changes: Any) -> dict[str, Any]:
    return document(
        folder_id=None,
        session_id=CONVERSATION,
        session_user_id="alice",
        session_deletion_id=None,
        **changes,
    )


@pytest.mark.parametrize(
    "selection",
    [DocumentScope.from_ids([], []), DocumentScope.from_ids([str(uuid4())])],
)
def test_attachment_visibility_is_independent_of_corpus_selection(selection) -> None:
    row = attachment()
    scope = attachment_scope(row["id"], selection=selection)
    candidate = Candidate(str(row["id"]), chunk(2))
    assert filter_candidates(scope, [candidate], [row]) == [candidate]
    assert (
        filter_candidates(scope, [Candidate(str(row["id"]), chunk(2, uuid4()))], [row])
        == []
    )


@pytest.mark.parametrize(
    "change",
    [
        {"session_id": uuid4()},
        {"space_id": ORG},
        {"space_id": PROJECT},
        {"session_user_id": "bob"},
        {"session_user_id": None},
        {"session_deletion_id": uuid4()},
        {"deletion_id": uuid4()},
        {"retrievable": False},
        {"retrievable_pending": True},
        {"generation_id": None},
        {"id": uuid4()},
    ],
)
def test_attachment_must_match_all_sql_facts_and_the_explicit_list(change) -> None:
    row = attachment()
    scope = attachment_scope(row["id"])
    row.update(change)
    assert filter_candidates(scope, [Candidate(str(row["id"]), chunk(2))], [row]) == []


@pytest.mark.parametrize("scope", [SCOPE, attachment_scope()])
def test_conversation_or_corpus_id_alone_never_grants_an_attachment(scope) -> None:
    row = attachment()
    assert filter_candidates(scope, [Candidate(str(row["id"]), chunk(2))], [row]) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("retired", [False, True])
async def test_markdown_rechecks_attachment_conversation_after_scope_resolution(
    retired,
) -> None:
    row = attachment(prefix="published/current/", size=42, sha256="a" * 64)
    scope = attachment_scope(row["id"], selection=DocumentScope.from_ids([], []))
    if retired:
        row["session_deletion_id"] = uuid4()
    conn = MagicMock(spec=AsyncConnection)
    conn.execute = AsyncMock(return_value=MagicMock())
    conn.execute.return_value.mappings.return_value.first.return_value = row
    result = await published_artifact(conn, scope, row["id"], "output.md")
    assert result == (
        None if retired else PublishedArtifact("published/current/", 42, "a" * 64)
    )
    sql = str(conn.execute.call_args.args[0])
    assert "sm.session_id = d.session_id" in sql and "sm.space_id = d.space_id" in sql
    assert "g.id = d.published_generation" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize("authorized", [False, True])
@pytest.mark.parametrize("count", [0, 125])
async def test_resolver_checks_conversation_and_prefilters_all_attachment_ids(
    authorized, count
) -> None:
    from fred_core.documents import access

    rows = [attachment() for _ in range(count)]
    ids = tuple(row["id"] for row in rows)
    context = DocumentAccessContext(
        space_id=TEAM,
        document_scope=DocumentScope(),
        conversation_id=CONVERSATION,
        attachment_ids=ids,
    )
    space_result, session_result, documents_result = (
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    space_result.mappings.return_value.first.return_value = space(TEAM, ORG, ORG)
    session_result.mappings.return_value.first.return_value = (
        {"session_id": CONVERSATION} if authorized else None
    )
    documents_result.mappings.return_value.all.return_value = rows
    conn = MagicMock(spec=AsyncConnection)
    conn.execute = AsyncMock(
        side_effect=[space_result, session_result, documents_result]
    )
    scope = await access.resolve_scope(conn, context, user_id="alice")
    assert set(scope.attachment_ids) == (set(ids) if authorized else set())
    statement, params = conn.execute.call_args_list[1].args
    assert params == {
        "conversation_id": CONVERSATION,
        "space_id": TEAM,
        "user_id": "alice",
    }
    assert "session_id = :conversation_id AND space_id = :space_id" in str(statement)
    assert "user_id = :user_id AND deletion_id IS NULL" in str(statement)
    if count and authorized:
        statement, params = conn.execute.call_args.args
        assert set(params["document_ids"]) == set(ids)
        assert "LIMIT" not in str(statement)
    else:
        assert conn.execute.await_count == 2


@pytest.mark.asyncio
async def test_conversation_check_failure_never_falls_back_to_corpus() -> None:
    from fred_core.documents.access import resolve_scope

    result = MagicMock()
    result.mappings.return_value.first.return_value = space(TEAM, ORG, ORG)
    conn = MagicMock(spec=AsyncConnection)
    conn.execute = AsyncMock(side_effect=[result, RuntimeError("database unavailable")])
    with pytest.raises(RuntimeError, match="database unavailable"):
        await resolve_scope(
            conn,
            DocumentAccessContext(
                space_id=TEAM,
                document_scope=DocumentScope(),
                conversation_id=CONVERSATION,
            ),
            user_id="alice",
        )
