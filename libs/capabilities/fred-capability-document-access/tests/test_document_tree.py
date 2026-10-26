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

"""Offline tests for the document tree rendering."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from fred_capability_document_access.document_tree import render_listing
from fred_core.documents.tree import DocumentListing, SpaceLabel, VisibleDocument

ORG = UUID("00000000-0000-0000-0000-000000000001")
TEAM = UUID("00000000-0000-0000-0000-000000000002")
PROJECT = UUID("00000000-0000-0000-0000-000000000003")
HR = UUID("00000000-0000-0000-0000-00000000000a")
POLICIES = UUID("00000000-0000-0000-0000-00000000000b")
ARCHIVE = UUID("00000000-0000-0000-0000-00000000000c")
ADDED = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
ADDED_ISO = "2026-01-02T03:04:05+00:00"

# Scope order differs from alphabetical order on purpose.
SPACES = (
    SpaceLabel(ORG, "organization", "Zeta org"),
    SpaceLabel(TEAM, "team", "Alpha team"),
    SpaceLabel(PROJECT, "project", "Empty project"),
)


def doc(
    uid: str,
    name: str,
    space: UUID,
    folders: tuple[tuple[UUID, str], ...] = (),
    *,
    mime: str = "application/pdf",
    added_at: datetime = ADDED,
) -> VisibleDocument:
    return VisibleDocument(
        document_uid=uid,
        name=name,
        mime=mime,
        added_at=added_at,
        space_id=space,
        folder_ids=tuple(f for f, _ in folders),
        folder_names=tuple(n for _, n in folders),
    )


def listing(
    *documents: VisibleDocument,
    spaces: tuple[SpaceLabel, ...] = SPACES,
    truncated: bool = False,
) -> DocumentListing:
    return DocumentListing(spaces=spaces, documents=documents, truncated=truncated)


def corpus(*, truncated: bool = False) -> DocumentListing:
    hr = (HR, "HR")
    return listing(
        doc("d-handbook", "handbook.pdf", TEAM, (hr, (POLICIES, "Policies"))),
        doc("d-zz", "zz.pdf", ORG),
        doc("d-leave", "leave.pdf", TEAM, (hr,)),
        doc("d-old", "old.txt", TEAM, ((ARCHIVE, "Archive"),), mime=""),
        doc("d-a", "a.pdf", TEAM),
        truncated=truncated,
    )


def leaf(uid: str, name: str, mime: str | None = "application/pdf") -> str:
    mime_part = f',"mime_type":"{mime}"' if mime else ""
    return (
        f'{{"uid":"{uid}","name":"{name}","added_to_kb":"{ADDED_ISO}",'
        f'"created":null,"modified":null{mime_part}}}'
    )


def folder(name: str, folder_id: UUID | None = None) -> str:
    if folder_id is None:
        return f'{{"folder":"{name}"}}'
    return f'{{"folder":"{name}","folder_id":"{folder_id}"}}'


def folder_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if '"folder"' in line]


def test_nominal_two_spaces_with_nested_folders() -> None:
    text, truncated = render_listing(corpus())

    assert truncated is False
    assert text == (
        '{"folder":"Zeta org"}\n'
        '  {"uid":"d-zz","name":"zz.pdf","added_to_kb":"2026-01-02T03:04:05+00:00",'
        '"created":null,"modified":null,"mime_type":"application/pdf"}\n'
        '{"folder":"Alpha team"}\n'
        '  {"folder":"Archive","folder_id":"00000000-0000-0000-0000-00000000000c"}\n'
        '    {"uid":"d-old","name":"old.txt","added_to_kb":"2026-01-02T03:04:05+00:00",'
        '"created":null,"modified":null}\n'
        '  {"folder":"HR","folder_id":"00000000-0000-0000-0000-00000000000a"}\n'
        '    {"folder":"Policies","folder_id":"00000000-0000-0000-0000-00000000000b"}\n'
        '      {"uid":"d-handbook","name":"handbook.pdf",'
        '"added_to_kb":"2026-01-02T03:04:05+00:00",'
        '"created":null,"modified":null,"mime_type":"application/pdf"}\n'
        '    {"uid":"d-leave","name":"leave.pdf","added_to_kb":"2026-01-02T03:04:05+00:00",'
        '"created":null,"modified":null,"mime_type":"application/pdf"}\n'
        '  {"uid":"d-a","name":"a.pdf","added_to_kb":"2026-01-02T03:04:05+00:00",'
        '"created":null,"modified":null,"mime_type":"application/pdf"}'
    )


def test_space_without_visible_document_is_hidden() -> None:
    text, _ = render_listing(corpus())

    assert "Empty project" not in text


def test_spaces_follow_scope_order_not_names() -> None:
    reordered = (SPACES[1], SPACES[0])
    text, _ = render_listing(
        listing(doc("d-1", "x.pdf", ORG), doc("d-2", "y.pdf", TEAM), spaces=reordered)
    )

    assert folder_lines(text) == [folder("Alpha team"), folder("Zeta org")]


def test_nodes_with_the_same_name_do_not_merge() -> None:
    first = UUID("00000000-0000-0000-0000-0000000000f1")
    second = UUID("00000000-0000-0000-0000-0000000000f2")
    spaces = (SpaceLabel(ORG, "organization", "Docs"), SpaceLabel(TEAM, "team", "Docs"))
    text, _ = render_listing(
        listing(
            doc("d-1", "one.pdf", ORG, ((first, "Docs"),)),
            doc("d-2", "two.pdf", ORG, ((second, "Docs"),)),
            doc("d-3", "three.pdf", TEAM),
            spaces=spaces,
        )
    )

    assert text.splitlines() == [
        folder("Docs"),
        f"  {folder('Docs', first)}",
        f"    {leaf('d-1', 'one.pdf')}",
        f"  {folder('Docs', second)}",
        f"    {leaf('d-2', 'two.pdf')}",
        folder("Docs"),
        f"  {leaf('d-3', 'three.pdf')}",
    ]


def test_folders_and_leaves_sort_by_name_then_id() -> None:
    low = UUID("00000000-0000-0000-0000-000000000011")
    high = UUID("00000000-0000-0000-0000-000000000012")
    text, _ = render_listing(
        listing(
            doc("d-1", "x.pdf", TEAM, ((high, "Same"),)),
            doc("d-2", "x.pdf", TEAM, ((low, "Same"),)),
            doc("d-3", "y.pdf", TEAM, ((HR, "Before"),)),
            doc("b", "same.pdf", TEAM),
            doc("a", "same.pdf", TEAM),
            doc("c", "aaa.pdf", TEAM),
        )
    )

    assert text.splitlines() == [
        folder("Alpha team"),
        f"  {folder('Before', HR)}",
        f"    {leaf('d-3', 'y.pdf')}",
        f"  {folder('Same', low)}",
        f"    {leaf('d-2', 'x.pdf')}",
        f"  {folder('Same', high)}",
        f"    {leaf('d-1', 'x.pdf')}",
        f"  {leaf('c', 'aaa.pdf')}",
        f"  {leaf('a', 'same.pdf')}",
        f"  {leaf('b', 'same.pdf')}",
    ]


def test_leaf_format_has_null_dates_and_optional_mime() -> None:
    paris = timezone(timedelta(hours=1))
    text, _ = render_listing(
        listing(
            doc(
                "d-1",
                "a.pdf",
                ORG,
                added_at=datetime(2026, 1, 2, 4, 4, 5, tzinfo=paris),
            ),
            doc("d-2", "b", ORG, mime="", added_at=datetime(2026, 1, 2, 3, 4, 5)),
        )
    )
    records = [json.loads(line) for line in text.splitlines()[1:]]

    assert records == [
        {
            "uid": "d-1",
            "name": "a.pdf",
            "added_to_kb": ADDED_ISO,
            "created": None,
            "modified": None,
            "mime_type": "application/pdf",
        },
        {
            "uid": "d-2",
            "name": "b",
            "added_to_kb": ADDED_ISO,
            "created": None,
            "modified": None,
        },
    ]


def test_working_directory_on_a_space_keeps_the_root() -> None:
    text, truncated = render_listing(corpus(), working_directory="Zeta org")

    assert truncated is False
    assert text.splitlines() == [folder("Zeta org"), f"  {leaf('d-zz', 'zz.pdf')}"]


def test_working_directory_on_a_subfolder_keeps_ancestors() -> None:
    text, _ = render_listing(corpus(), working_directory="Alpha team/HR")

    assert text.splitlines() == [
        folder("Alpha team"),
        f"  {folder('HR', HR)}",
        f"    {folder('Policies', POLICIES)}",
        f"      {leaf('d-handbook', 'handbook.pdf')}",
        f"    {leaf('d-leave', 'leave.pdf')}",
    ]


@pytest.mark.parametrize("working_directory", ["Nope", "Alpha team/Nope", "Alpha"])
def test_unknown_working_directory_is_empty(working_directory: str) -> None:
    assert render_listing(corpus(), working_directory=working_directory) == (
        "(empty)",
        False,
    )


def test_working_directory_ignores_empty_segments() -> None:
    expected = render_listing(corpus(), working_directory="Alpha team/HR")

    assert render_listing(corpus(), working_directory="/Alpha team//HR/") == expected


@pytest.mark.parametrize("working_directory", [None, "", "/"])
def test_missing_working_directory_lists_everything(
    working_directory: str | None,
) -> None:
    assert render_listing(
        corpus(), working_directory=working_directory
    ) == render_listing(corpus())


def test_empty_listing() -> None:
    assert render_listing(listing()) == ("(empty)", False)


def test_truncated_listing_adds_a_final_root_note() -> None:
    text, truncated = render_listing(corpus(truncated=True))
    full, _ = render_listing(corpus())

    assert truncated is True
    assert text.startswith(full + "\n")
    last = text.splitlines()[-1]
    assert last.startswith("... listing incomplete")
    assert "search_documents_using_vectorization" in last


def test_truncated_listing_with_no_match_still_warns() -> None:
    text, truncated = render_listing(corpus(truncated=True), working_directory="Nope")

    assert truncated is True
    assert text.splitlines()[0] == "(empty)"
    assert text.splitlines()[1].startswith("... listing incomplete")


def test_budget_prunes_the_deepest_level_first() -> None:
    documents = [
        doc(f"d-{i:02d}", f"doc-{i:02d}.pdf", TEAM, ((HR, "HR"),)) for i in range(20)
    ]
    text, truncated = render_listing(listing(*documents), max_chars=500)

    assert truncated is True
    assert text.splitlines() == [
        folder("Alpha team"),
        f"  {folder('HR', HR)}",
        "    ... 20 more item(s) below, use search_documents_using_vectorization"
        " or narrow working_directory",
    ]


def test_budget_keeps_whole_top_level_blocks() -> None:
    spaces = tuple(
        SpaceLabel(UUID(int=100 + i), "project", f"Space {i:02d}") for i in range(30)
    )
    documents = [doc(f"d-{i:02d}", "x.pdf", UUID(int=100 + i)) for i in range(30)]
    text, truncated = render_listing(listing(*documents, spaces=spaces), max_chars=500)
    lines = text.splitlines()
    omitted = re.fullmatch(r"\.\.\. (\d+) more item\(s\) at this level, .+", lines[-1])

    assert truncated is True
    assert len(text) <= 500
    assert omitted is not None
    shown = lines[:-1]
    # Each shown space keeps its pruned content note: nothing vanishes silently.
    assert len(shown) % 2 == 0
    for header, note in zip(shown[::2], shown[1::2], strict=True):
        assert header.startswith('{"folder":"Space ')
        assert note.startswith("  ... 1 more item(s) below")
    assert len(shown) // 2 + int(omitted.group(1)) == 30


def test_truncated_listing_respects_the_budget() -> None:
    documents = [
        doc(f"d-{i:02d}", f"doc-{i:02d}.pdf", TEAM, ((HR, "HR"),)) for i in range(20)
    ]
    text, truncated = render_listing(listing(*documents, truncated=True), max_chars=500)

    assert truncated is True
    assert len(text) <= 500
    assert text.splitlines()[-1].startswith("... listing incomplete")


def test_max_chars_below_the_floor_is_refused() -> None:
    with pytest.raises(ValueError, match="max_chars"):
        render_listing(corpus(), max_chars=499)
    assert render_listing(corpus(), max_chars=500)[1] is True


def test_document_without_space_label_is_refused() -> None:
    stray = doc("d-1", "x.pdf", UUID(int=999))

    with pytest.raises(ValueError, match="no space label"):
        render_listing(listing(stray))
