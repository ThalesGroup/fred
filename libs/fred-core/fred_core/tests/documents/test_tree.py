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

"""Visible document listing decisions, on rows built in memory.

The SQL schema belongs to the Control Plane migrations; no database is used here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fred_core.documents.access import SearchScope
from fred_core.documents.tree import (
    SpaceLabel,
    VisibleDocument,
    build_documents,
    list_visible_documents,
    visible_rows,
)
from sqlalchemy.ext.asyncio import AsyncConnection

ORG, TEAM, PROJECT = uuid4(), uuid4(), uuid4()
SCOPE = SearchScope(space_ids=(ORG, TEAM))
ADDED = datetime(2026, 10, 26, tzinfo=timezone.utc)
TOP, MIDDLE = uuid4(), uuid4()


def path(*folders: UUID) -> str:
    return "/" + "".join(f"{folder}/" for folder in folders)


def document(**changes: Any) -> dict[str, Any]:
    row = {
        "id": uuid4(),
        "space_id": TEAM,
        "folder_id": None,
        "name": "report.pdf",
        "mime": "application/pdf",
        "created_at": ADDED,
        "deletion_id": None,
        "space_deletion_id": None,
        "retrievable": True,
        "retrievable_pending": False,
        "path": None,
        "published": True,
    }
    return {**row, **changes}


def listed(row: dict[str, Any], names: dict[UUID, str] | None = None) -> list[Any]:
    return list(build_documents(visible_rows(SCOPE, [row]), names or {}))


@pytest.mark.parametrize(
    "changes",
    [
        {"space_id": PROJECT},
        {"deletion_id": uuid4()},
        {"space_deletion_id": uuid4()},
        {"retrievable": False},
        {"retrievable_pending": True},
        {"published": False},
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
def test_document_facts_hide_the_document(changes: dict[str, Any]) -> None:
    assert listed(document(**changes)) == []


def test_root_document_has_no_folders() -> None:
    row = document()
    assert listed(row) == [
        VisibleDocument(
            document_uid=str(row["id"]),
            name="report.pdf",
            mime="application/pdf",
            added_at=ADDED,
            space_id=TEAM,
            folder_ids=(),
            folder_names=(),
        )
    ]


def test_nested_folders_are_named_in_path_order() -> None:
    leaf = uuid4()
    row = document(folder_id=leaf, path=path(TOP, MIDDLE, leaf))
    names = {leaf: "Q3", TOP: "Finance", MIDDLE: "Reports"}
    [visible] = listed(row, names)
    assert visible.folder_ids == (TOP, MIDDLE, leaf)
    assert visible.folder_names == ("Finance", "Reports", "Q3")


@pytest.mark.parametrize(
    "path_value",
    [None, path(TOP, MIDDLE), "/not-a-uuid/", "/"],
    ids=["path-absent", "other-folder", "malformed", "empty"],
)
def test_unknown_folder_path_hides_the_document(path_value: str | None) -> None:
    row = document(folder_id=uuid4(), path=path_value)
    assert listed(row, {TOP: "Finance", MIDDLE: "Reports"}) == []


def test_unnamed_ancestor_hides_the_document() -> None:
    row = document(folder_id=MIDDLE, path=path(TOP, MIDDLE))
    assert listed(row, {MIDDLE: "Reports"}) == []


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def mappings(self) -> FakeResult:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class FakeConnection:
    """Answers the space, document and folder-name queries in that order."""

    def __init__(self, *results: list[dict[str, Any]]) -> None:
        self.results = list(results)
        self.calls: list[dict[str, Any]] = []

    async def execute(self, _: Any, parameters: dict[str, Any]) -> FakeResult:
        self.calls.append(parameters)
        return FakeResult(self.results.pop(0))


SPACES = [
    {"id": TEAM, "kind": "team", "name": "fredlab"},
    {"id": ORG, "kind": "organization", "name": "TSN"},
]


@pytest.mark.asyncio
async def test_root_documents_read_no_folder_names() -> None:
    conn = FakeConnection(SPACES, [document(), document(space_id=ORG)])
    listing = await list_visible_documents(cast(AsyncConnection, conn), SCOPE)
    assert len(conn.calls) == 2
    assert listing.spaces == (
        SpaceLabel(ORG, "organization", "TSN"),
        SpaceLabel(TEAM, "team", "fredlab"),
    )
    assert [d.space_id for d in listing.documents] == [TEAM, ORG]
    assert listing.truncated is False


@pytest.mark.asyncio
async def test_folder_names_are_read_once_for_kept_paths() -> None:
    rows = [
        document(folder_id=MIDDLE, path=path(TOP, MIDDLE)),
        document(folder_id=TOP, path=path(TOP)),
        document(folder_id=uuid4(), path=None),
    ]
    names = [{"id": TOP, "name": "Finance"}, {"id": MIDDLE, "name": "Reports"}]
    conn = FakeConnection(SPACES, rows, names)
    listing = await list_visible_documents(cast(AsyncConnection, conn), SCOPE)
    assert conn.calls[2] == {"folder_ids": [TOP, MIDDLE]}
    assert [d.folder_names for d in listing.documents] == [
        ("Finance", "Reports"),
        ("Finance",),
    ]


@pytest.mark.asyncio
async def test_extra_row_marks_the_listing_truncated() -> None:
    rows = [document(name=name) for name in ("a", "b", "c")]
    conn = FakeConnection(SPACES, rows)
    listing = await list_visible_documents(
        cast(AsyncConnection, conn), SCOPE, max_rows=2
    )
    assert conn.calls[1]["limit"] == 3
    assert [d.name for d in listing.documents] == ["a", "b"]
    assert listing.truncated is True


@pytest.mark.asyncio
async def test_invalid_max_rows_reads_nothing() -> None:
    conn = FakeConnection()
    with pytest.raises(ValueError):
        await list_visible_documents(cast(AsyncConnection, conn), SCOPE, max_rows=0)
    assert conn.calls == []


class FailingConnection:
    async def execute(self, *_: Any) -> Any:
        raise RuntimeError("database unavailable")


@pytest.mark.asyncio
async def test_database_failure_is_not_an_empty_listing() -> None:
    conn = cast(AsyncConnection, FailingConnection())
    with pytest.raises(RuntimeError):
        await list_visible_documents(conn, SCOPE)
