# Copyright Thales 2025
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

from datetime import datetime, timezone

from knowledge_flow_backend.features.tree.tree_builder import build_tree, render_tree


def test_nested_folders_render_with_indentation():
    folders = [("Sales", ["doc-1"]), ("Sales/HR", ["doc-2"])]
    leaves = {
        "doc-1": ("Overview.pdf", datetime(2026, 1, 1, tzinfo=timezone.utc)),
        "doc-2": ("Onboarding.pdf", datetime(2026, 2, 1, tzinfo=timezone.utc)),
    }

    root = build_tree(folders=folders, leaves_by_uid=leaves)
    text, truncated = render_tree(root, max_chars=10_000)

    assert not truncated
    assert "Sales/" in text
    assert "  HR/" in text
    assert "Overview.pdf [doc-1] (uploaded 2026-01-01)" in text
    assert "    Onboarding.pdf [doc-2] (uploaded 2026-02-01)" in text


def test_leaf_includes_document_uid_so_callers_can_target_other_tools():
    """The tree is the agent's main way to discover a document's uid before
    calling summarize_document or search's document_uids filter -- the uid must
    be visible and unambiguous in the rendered line, not just the display name."""
    folders = [("Sales", ["doc-abc-123"])]
    leaves = {"doc-abc-123": ("Report.pdf", None)}

    root = build_tree(folders=folders, leaves_by_uid=leaves)
    text, _ = render_tree(root, max_chars=10_000)

    assert "[doc-abc-123]" in text


def test_document_in_multiple_folders_appears_as_a_leaf_under_each():
    folders = [("Sales/HR", ["doc-1"]), ("Sales/Legal", ["doc-1"])]
    leaves = {"doc-1": ("Policy.pdf", None)}

    root = build_tree(folders=folders, leaves_by_uid=leaves)
    text, truncated = render_tree(root, max_chars=10_000)

    assert not truncated
    assert text.count("Policy.pdf") == 2


def test_implicit_parent_segment_without_its_own_tag_still_groups_children():
    """'Sales' itself was never created as a Tag, only 'Sales/HR' was -- the
    builder should still synthesize a 'Sales' grouping node."""
    folders = [("Sales/HR", ["doc-1"])]
    leaves = {"doc-1": ("Doc.pdf", None)}

    root = build_tree(folders=folders, leaves_by_uid=leaves)
    text, truncated = render_tree(root, max_chars=10_000)

    assert not truncated
    assert "Sales/" in text
    assert "  HR/" in text


def test_unresolved_uid_is_silently_skipped():
    """If metadata lookup didn't return a uid (e.g. deleted concurrently), the
    tree should just omit it rather than erroring."""
    folders = [("Sales", ["doc-missing"])]

    root = build_tree(folders=folders, leaves_by_uid={})
    text, truncated = render_tree(root, max_chars=10_000)

    assert not truncated
    assert "doc-missing" not in text


def test_empty_tree_renders_as_empty_placeholder():
    root = build_tree(folders=[], leaves_by_uid={})
    text, truncated = render_tree(root, max_chars=10_000)

    assert text == "(empty)"
    assert not truncated


def test_oversized_deep_branch_is_pruned_with_fallback_hint():
    folders = [("Sales/HR/Payroll/Archive", [f"doc-{i}" for i in range(50)])]
    leaves = {f"doc-{i}": (f"file-{i}.pdf", None) for i in range(50)}

    root = build_tree(folders=folders, leaves_by_uid=leaves)
    text, truncated = render_tree(root, max_chars=200)

    assert truncated
    assert "more item(s) below" in text
    assert "use search_documents_using_vectorization" in text
    # The placeholder is a synthetic note, not a real DocLeaf -- it must not be
    # run through _format_leaf (which would add a bogus "[] (uploaded ...)").
    assert "[]" not in text
    assert "uploaded unknown date" not in text


def test_oversized_root_level_omits_items_with_count():
    folders = [(f"folder-{i}", [f"doc-{i}"]) for i in range(50)]
    leaves = {f"doc-{i}": (f"file-{i}.pdf", None) for i in range(50)}

    root = build_tree(folders=folders, leaves_by_uid=leaves)
    text, truncated = render_tree(root, max_chars=300)

    assert truncated
    assert "more item(s) at this level" in text
    assert len(text) <= 300
