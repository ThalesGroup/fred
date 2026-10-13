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

import json
from datetime import datetime, timedelta, timezone

from knowledge_flow_backend.features.corpus_tree.tree_builder import DocLeaf, build_tree, render_tree


def test_nested_folders_render_with_indentation():
    folders = [("Sales", ["doc-1"]), ("Sales/HR", ["doc-2"])]
    leaves = {
        "doc-1": DocLeaf("doc-1", "Overview.pdf", datetime(2026, 1, 1, tzinfo=timezone.utc)),
        "doc-2": DocLeaf("doc-2", "Onboarding.pdf", datetime(2026, 2, 1, tzinfo=timezone.utc)),
    }

    root = build_tree(folders=folders, leaves_by_uid=leaves)
    text, truncated = render_tree(root, max_chars=10_000)

    assert not truncated
    assert '"folder":"Sales"' in text
    assert '"folder":"HR"' in text
    assert json.loads(text.splitlines()[3])["created"] == "2026-01-01T00:00:00+00:00"
    assert text.splitlines()[2].startswith("    {")
    assert json.loads(text.splitlines()[2])["name"] == "Onboarding.pdf"


def test_leaf_includes_document_uid_so_callers_can_target_other_tools():
    """The tree is the agent's main way to discover a document's uid before
    calling summarize_document or search's document_uids filter -- the uid must
    be visible and unambiguous in the rendered line, not just the display name."""
    folders = [("Sales", ["doc-abc-123"])]
    leaves = {"doc-abc-123": DocLeaf("doc-abc-123", "Report.pdf", None)}

    root = build_tree(folders=folders, leaves_by_uid=leaves)
    text, _ = render_tree(root, max_chars=10_000)

    assert json.loads(text.splitlines()[1])["uid"] == "doc-abc-123"


def test_folder_renders_its_tag_id_so_callers_can_filter_on_it():
    """Folder ids remain distinguishable from document uids."""
    folders = [("Sales", ["doc-1"], "tag-sales"), ("Sales/HR", ["doc-2"], "tag-hr")]
    leaves = {"doc-1": DocLeaf("doc-1", "Overview.pdf", None), "doc-2": DocLeaf("doc-2", "Onboarding.pdf", None)}

    root = build_tree(folders=folders, leaves_by_uid=leaves)
    text, _ = render_tree(root, max_chars=10_000)

    assert '"folder":"Sales","folder_id":"tag-sales"' in text
    assert '"folder":"HR","folder_id":"tag-hr"' in text
    # Folder ids must not be advertised as document uids.
    assert '"uid":"tag-sales"' not in text
    assert '"uid":"tag-hr"' not in text


def test_synthetic_parent_folder_has_no_tag_id():
    """'Sales' was never a real tag (only 'Sales/HR' was) -- it is a synthetic
    grouping node and must render without a bracketed id to filter on."""
    folders = [("Sales/HR", ["doc-1"], "tag-hr")]
    leaves = {"doc-1": DocLeaf("doc-1", "Doc.pdf", None)}

    root = build_tree(folders=folders, leaves_by_uid=leaves)
    text, _ = render_tree(root, max_chars=10_000)

    assert '"folder":"Sales"' in text
    assert '"folder":"Sales","folder_id"' not in text
    assert '"folder":"HR","folder_id":"tag-hr"' in text


def test_folders_without_tag_id_stay_backward_compatible():
    """Two-tuple folders (no tag id) still render as plain 'name/'."""
    folders = [("Sales", ["doc-1"])]
    leaves = {"doc-1": DocLeaf("doc-1", "Overview.pdf", None)}

    root = build_tree(folders=folders, leaves_by_uid=leaves)
    text, _ = render_tree(root, max_chars=10_000)

    assert '"folder":"Sales"' in text
    assert '"folder":"Sales","folder_id"' not in text


def test_document_in_multiple_folders_appears_as_a_leaf_under_each():
    folders = [("Sales/HR", ["doc-1"]), ("Sales/Legal", ["doc-1"])]
    leaves = {"doc-1": DocLeaf("doc-1", "Policy.pdf", None)}

    root = build_tree(folders=folders, leaves_by_uid=leaves)
    text, truncated = render_tree(root, max_chars=10_000)

    assert not truncated
    assert text.count("Policy.pdf") == 2


def test_implicit_parent_segment_without_its_own_tag_still_groups_children():
    """'Sales' itself was never created as a Tag, only 'Sales/HR' was -- the
    builder should still synthesize a 'Sales' grouping node."""
    folders = [("Sales/HR", ["doc-1"])]
    leaves = {"doc-1": DocLeaf("doc-1", "Doc.pdf", None)}

    root = build_tree(folders=folders, leaves_by_uid=leaves)
    text, truncated = render_tree(root, max_chars=10_000)

    assert not truncated
    assert '"folder":"Sales"' in text
    assert '"folder":"HR"' in text


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
    leaves = {f"doc-{i}": DocLeaf(f"doc-{i}", f"file-{i}.pdf", None) for i in range(50)}

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
    leaves = {f"doc-{i}": DocLeaf(f"doc-{i}", f"file-{i}.pdf", None) for i in range(50)}

    root = build_tree(folders=folders, leaves_by_uid=leaves)
    text, truncated = render_tree(root, max_chars=300)

    assert truncated
    assert "more item(s) at this level" in text
    assert len(text) <= 300


def test_wide_shallow_tree_never_reports_truncated_with_zero_omission_signal():
    """Regression: a label match spread across many folders (one document
    each) is wide, not deep -- depth-based pruning collapses every folder's
    single document into an "N more item(s) below" note, but the FINAL
    root-level budget fallback used to rebuild its candidate lines from
    scratch (bare folder headers only), discarding those notes entirely.
    150 folder headers alone fit comfortably under 6000 chars, so the old
    code returned truncated=True with 150 folders, 0 documents, and 0
    words telling the caller anything was omitted -- indistinguishable from
    a complete, empty-of-content corpus. `truncated=True` must never ship
    without an explicit, non-empty signal of what was left out."""
    folders = [(f"Folder{i:03d}", [f"doc-{i:03d}"], f"tag-{i:03d}") for i in range(150)]
    leaves = {f"doc-{i:03d}": DocLeaf(f"doc-{i:03d}", f"document-{i:03d}.pdf", None) for i in range(150)}

    root = build_tree(folders=folders, leaves_by_uid=leaves)
    text, truncated = render_tree(root, max_chars=6000)

    assert truncated
    assert len(text) <= 6000
    documents_rendered = sum(1 for line in text.splitlines() if line.lstrip().startswith("{"))
    omission_signals = sum(1 for line in text.splitlines() if "more item(s)" in line)
    assert documents_rendered > 0 or omission_signals > 0, (
        f"truncated=True but the response shows {documents_rendered} documents and {omission_signals} omission notes -- indistinguishable from a complete, empty corpus"
    )


def test_timestamps_keep_same_day_order_offsets_and_precision():
    leaves = {
        "early": DocLeaf("early", "Early.pdf", added_to_kb=datetime(2026, 10, 12, 10, 0, tzinfo=timezone(timedelta(hours=2)))),
        "late": DocLeaf("late", "Late.pdf", added_to_kb=datetime(2026, 10, 12, 8, 0, 0, 123456)),
    }
    text, truncated = render_tree(build_tree(folders=[("Docs", list(leaves))], leaves_by_uid=leaves), max_chars=1000)
    records = [json.loads(line) for line in text.splitlines()[1:]]
    assert not truncated
    assert records[0]["added_to_kb"] == "2026-10-12T08:00:00+00:00"
    assert records[1]["added_to_kb"] == "2026-10-12T08:00:00.123456+00:00"
    assert records[0]["created"] is None
    assert records[0]["modified"] is None


def test_metadata_punctuation_stays_in_one_complete_leaf():
    name = "Report [draft]/\nNext.pdf"
    leaf = DocLeaf("doc", name, title='Title "quoted"\nNext', labels=["[folder:fake]", "Finance"], page_count=0)
    text, truncated = render_tree(build_tree(folders=[("Docs", ["doc"])], leaves_by_uid={"doc": leaf}), max_chars=1000)
    assert not truncated
    assert len(text.splitlines()) == 2
    record = json.loads(text.splitlines()[1])
    assert record["name"] == name
    assert record["title"] == 'Title "quoted"\nNext'
    assert record["labels"] == ["[folder:fake]", "Finance"]
    assert record["page_count"] == 0


def test_oversized_metadata_is_omitted_as_a_whole_document():
    leaf = DocLeaf("doc", "Large.pdf", title="x" * 2000)
    text, truncated = render_tree(build_tree(folders=[("Docs", ["doc"])], leaves_by_uid={"doc": leaf}), max_chars=500)
    assert truncated
    assert len(text) <= 500
    assert '"uid"' not in text
    assert "more item(s)" in text


def test_allowed_folder_punctuation_and_newlines_stay_in_one_record():
    folder_name = "{Drafts}\n[copy]"
    text, truncated = render_tree(build_tree(folders=[(folder_name, ["doc"], "folder-id")], leaves_by_uid={"doc": DocLeaf("doc", "Report.pdf")}), max_chars=1000)
    lines = text.splitlines()
    assert not truncated
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"folder": folder_name, "folder_id": "folder-id"}
    assert json.loads(lines[1])["uid"] == "doc"
