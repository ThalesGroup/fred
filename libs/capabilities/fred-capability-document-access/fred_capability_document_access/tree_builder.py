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

"""Render authorized folders and document metadata as a budgeted indented tree."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fred_core.documents.tree import DocumentTreeDocument, DocumentTreeResult

_FALLBACK_HINT = "use search_documents or narrow folder_id"


@dataclass
class TreeNode:
    name: str
    folder_id: str | None = None
    children: dict[str, "TreeNode"] = field(default_factory=dict)
    docs: list[DocumentTreeDocument] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    omitted_items: int = 0

    def depth_of_deepest_branch(self) -> int:
        return (
            1 + max(c.depth_of_deepest_branch() for c in self.children.values())
            if self.children
            else 0
        )


def build_tree(result: DocumentTreeResult) -> TreeNode:
    root = TreeNode(name="")
    spaces = {space.space_id: TreeNode(name=space.name) for space in result.spaces}
    folders = {
        folder.folder_id: TreeNode(name=folder.name, folder_id=str(folder.folder_id))
        for folder in result.folders
    }
    for space_id, node in spaces.items():
        root.children[str(space_id)] = node
    for folder in result.folders:
        parent = folders.get(folder.parent_id) if folder.parent_id is not None else None
        parent = parent or spaces[folder.space_id]
        parent.children[str(folder.folder_id)] = folders[folder.folder_id]
    for doc in result.documents:
        parent = folders.get(doc.folder_id) if doc.folder_id is not None else None
        (parent or spaces[doc.space_id]).docs.append(doc)
    return root


def _children(node: TreeNode) -> list[TreeNode]:
    return sorted(
        node.children.values(), key=lambda child: (child.name, child.folder_id or "")
    )


def _timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _format_leaf(doc: DocumentTreeDocument) -> str:
    return json.dumps(
        {
            "uid": str(doc.document_uid),
            "name": doc.name,
            "mime": doc.mime,
            "added_to_kb": _timestamp(doc.added_at),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _format_folder(node: TreeNode) -> str:
    # JSON keeps allowed newlines and punctuation in folder names on one tree line.
    record = {"folder": node.name}
    if node.folder_id:
        record["folder_id"] = node.folder_id
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def render_tree(root: TreeNode, *, max_chars: int) -> tuple[str, bool]:
    """
    Render the tree as indented text, pruning the deepest branches first when the
    rendering would exceed `max_chars`. Returns (text, truncated).
    """
    text = _render(root, depth=0)
    if len(text) <= max_chars:
        return (text if text else "(empty)"), False

    # Prune one depth level at a time, starting from the deepest. Each level is
    # pruned at most once: re-pruning the same (now-placeholder) depth again would
    # never shrink the rendering further and would loop forever.
    for depth in range(root.depth_of_deepest_branch(), 0, -1):
        _prune_deepest(root, depth)
        text = _render(root, depth=0)
        if len(text) <= max_chars:
            return text, True

    # Even the top level alone overflows: keep as many root-level lines as fit.
    text = _render_budgeted_root(root, max_chars=max_chars)
    return text, True


def _render(node: TreeNode, *, depth: int) -> str:
    lines: list[str] = []
    indent = "  " * depth
    for child in _children(node):
        lines.append(f"{indent}{_format_folder(child)}")
        lines.append(_render(child, depth=depth + 1))
    for doc in sorted(node.docs, key=lambda d: (d.name, str(d.document_uid))):
        lines.append(f"{indent}{_format_leaf(doc)}")
    for note in node.notes:
        lines.append(f"{indent}{note}")
    return "\n".join(line for line in lines if line)


def _prune_deepest(
    node: TreeNode, target_depth: int, *, current_depth: int = 0
) -> None:
    """Replace every child subtree exactly at `target_depth` with a placeholder."""
    if current_depth == target_depth - 1:
        for child in list(node.children.values()):
            if child.children or child.docs:
                count = _count_items(child)
                child.omitted_items = count
                child.children.clear()
                child.docs.clear()
                child.notes = [f"... {count} more item(s) below, {_FALLBACK_HINT}"]
        return
    for child in node.children.values():
        _prune_deepest(child, target_depth, current_depth=current_depth + 1)


def _count_items(node: TreeNode) -> int:
    total = len(node.docs) + node.omitted_items
    for child in node.children.values():
        total += 1 + _count_items(child)
    return total


def _render_budgeted_root(node: TreeNode, *, max_chars: int) -> str:
    """Keep whole root blocks, reserving room for the omission notice."""
    candidate_blocks = [
        f"{_format_folder(child)}\n{_render(child, depth=1)}".rstrip()
        for child in _children(node)
    ]
    candidate_blocks += [
        _format_leaf(d)
        for d in sorted(node.docs, key=lambda d: (d.name, str(d.document_uid)))
    ]

    # Reserve room for the longest possible omitted-count line (its count can have
    # up to len(candidate_blocks)'s digit count), so the line we append always fits.
    max_omitted_line = len(
        f"... {len(candidate_blocks)} more item(s) at this level, {_FALLBACK_HINT}"
    )
    budget = max_chars - max_omitted_line - 1  # -1 for its leading newline

    lines: list[str] = []
    total = 0
    omitted = 0
    for i, block in enumerate(candidate_blocks):
        if total + len(block) + 1 > budget:
            omitted = len(candidate_blocks) - i
            break
        lines.append(block)
        total += len(block) + 1

    if omitted:
        lines.append(f"... {omitted} more item(s) at this level, {_FALLBACK_HINT}")
    return "\n".join(lines)
