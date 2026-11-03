# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timezone
from uuid import UUID

from fred_capability_document_access.tree_builder import build_tree, render_tree
from fred_core.documents.tree import (
    DocumentTreeDocument,
    DocumentTreeFolder,
    DocumentTreeResult,
    DocumentTreeSpace,
)

SPACE, FOLDER, CHILD = [UUID(int=i) for i in range(1, 4)]


def document(uid=4, folder_id=FOLDER, name="Report.pdf"):
    return DocumentTreeDocument(
        document_uid=UUID(int=uid),
        space_id=SPACE,
        folder_id=folder_id,
        name=name,
        mime="application/pdf",
        added_at=datetime(2026, 11, 3, tzinfo=timezone.utc),
    )


def result(*, documents=(), folders=None):
    return DocumentTreeResult(
        spaces=(DocumentTreeSpace(space_id=SPACE, name="Team"),),
        folders=folders
        if folders is not None
        else (
            DocumentTreeFolder(
                folder_id=FOLDER, space_id=SPACE, parent_id=None, name='Sales\n"Q4"'
            ),
        ),
        documents=documents,
    )


def test_swift_json_lines_golden_with_weaver_metadata():
    text, truncated = render_tree(
        build_tree(result(documents=(document(),))), max_chars=20000
    )
    assert text == (
        '{"folder":"Team"}\n'
        '  {"folder":"Sales\\n\\"Q4\\"","folder_id":"00000000-0000-0000-0000-000000000002"}\n'
        '    {"uid":"00000000-0000-0000-0000-000000000004","name":"Report.pdf","mime":"application/pdf","added_to_kb":"2026-11-03T00:00:00+00:00"}'
    )
    assert not truncated


def test_prunes_deepest_branch_before_shallow_document():
    folders = (
        DocumentTreeFolder(
            folder_id=FOLDER, space_id=SPACE, parent_id=None, name="Parent"
        ),
        DocumentTreeFolder(
            folder_id=CHILD, space_id=SPACE, parent_id=FOLDER, name="Child"
        ),
    )
    tree = result(
        folders=folders,
        documents=(document(name="shallow.pdf"), document(5, CHILD, "deep" * 100)),
    )
    text, truncated = render_tree(build_tree(tree), max_chars=550)
    assert truncated
    assert "shallow.pdf" in text
    assert "deepdeep" not in text
    assert "more item(s) below" in text
    assert len(text) <= 550


def test_wide_tree_keeps_omission_notes_and_never_exceeds_budget():
    folders = tuple(
        DocumentTreeFolder(
            folder_id=UUID(int=i), space_id=SPACE, parent_id=None, name=f"folder-{i}"
        )
        for i in range(10, 160)
    )
    tree = result(
        folders=folders,
        documents=tuple(document(i + 200, f.folder_id) for i, f in enumerate(folders)),
    )
    text, truncated = render_tree(build_tree(tree), max_chars=500)
    assert truncated
    assert "more item(s)" in text
    assert len(text) <= 500


def test_same_folder_name_in_different_spaces_never_merges_documents():
    other = UUID(int=9)
    tree = result(documents=(document(folder_id=None),))
    tree = tree.model_copy(
        update={
            "spaces": (*tree.spaces, DocumentTreeSpace(space_id=other, name="Team")),
            "documents": (
                *tree.documents,
                document(5, None, "Other.pdf").model_copy(update={"space_id": other}),
            ),
        }
    )
    text, _ = render_tree(build_tree(tree), max_chars=20000)
    assert text.count('{"folder":"Team"}') == 2
    assert text.count('"uid":') == 2


def test_empty_tree_and_subtree_anchor_with_missing_parent():
    assert render_tree(build_tree(DocumentTreeResult()), max_chars=500) == (
        "(empty)",
        False,
    )
    tree = result(
        folders=(
            DocumentTreeFolder(
                folder_id=CHILD, space_id=SPACE, parent_id=FOLDER, name="Child"
            ),
        ),
        documents=(document(folder_id=CHILD),),
    )
    text, truncated = render_tree(build_tree(tree), max_chars=500)
    assert '"folder":"Child"' in text and '"name":"Report.pdf"' in text
    assert not truncated


def test_oversized_root_block_is_omitted_whole():
    tree = DocumentTreeResult(
        spaces=(DocumentTreeSpace(space_id=SPACE, name="long" * 200),)
    )
    text, truncated = render_tree(build_tree(tree), max_chars=500)
    assert truncated
    assert (
        text
        == "... 1 more item(s) at this level, use search_documents or narrow folder_id"
    )
