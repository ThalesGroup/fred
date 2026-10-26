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

"""Render a document listing as the budgeted indented tree read by the LLM.

Rendering only: `fred_core.documents.tree` decides which documents are visible.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from fred_core.documents.tree import DocumentListing, VisibleDocument

MIN_MAX_CHARS = 500
_FALLBACK_HINT = "use search_documents_using_vectorization or narrow working_directory"
# The listing was cut before rendering, so a narrower working_directory cannot help.
_INCOMPLETE_NOTE = (
    "... listing incomplete: more documents exist than could be listed,"
    " use search_documents_using_vectorization"
)


@dataclass
class _Node:
    name: str
    folder_id: str | None
    sort_key: tuple[int, str, str]
    children: dict[UUID, _Node] = field(default_factory=dict)
    docs: list[VisibleDocument] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def depth_of_deepest_branch(self) -> int:
        if not self.children:
            return 0
        return 1 + max(c.depth_of_deepest_branch() for c in self.children.values())


def render_listing(
    listing: DocumentListing,
    *,
    working_directory: str | None = None,
    max_chars: int = 20_000,
) -> tuple[str, bool]:
    """Return (text, truncated); a listing cut before rendering is truncated too."""
    if max_chars < MIN_MAX_CHARS:
        raise ValueError(f"max_chars must be at least {MIN_MAX_CHARS}")
    prefix = tuple(s for s in (working_directory or "").split("/") if s)
    root = _build_tree(listing, prefix)
    if not listing.truncated:
        return _render_tree(root, max_chars=max_chars)
    text, _ = _render_tree(root, max_chars=max_chars - len(_INCOMPLETE_NOTE) - 1)
    return f"{text}\n{_INCOMPLETE_NOTE}", True


def _build_tree(listing: DocumentListing, prefix: tuple[str, ...]) -> _Node:
    # Nodes are keyed by space or folder id: equal names never merge.
    spaces = {s.space_id: (i, s.name) for i, s in enumerate(listing.spaces)}
    root = _Node(name="", folder_id=None, sort_key=(0, "", ""))
    for doc in listing.documents:
        if doc.space_id not in spaces:
            raise ValueError(f"document {doc.document_uid} has no space label")
        index, space_name = spaces[doc.space_id]
        if (space_name, *doc.folder_names)[: len(prefix)] != prefix:
            continue
        node = _child(root, doc.space_id, space_name, None, (index, "", ""))
        for folder_id, folder_name in zip(
            doc.folder_ids, doc.folder_names, strict=True
        ):
            key = (0, folder_name, str(folder_id))
            node = _child(node, folder_id, folder_name, str(folder_id), key)
        node.docs.append(doc)
    return root


def _child(
    parent: _Node,
    key: UUID,
    name: str,
    folder_id: str | None,
    sort_key: tuple[int, str, str],
) -> _Node:
    node = parent.children.get(key)
    if node is None:
        node = _Node(name=name, folder_id=folder_id, sort_key=sort_key)
        parent.children[key] = node
    return node


def _children(node: _Node) -> list[_Node]:
    return sorted(node.children.values(), key=lambda c: c.sort_key)


def _leaves(node: _Node) -> list[VisibleDocument]:
    return sorted(node.docs, key=lambda d: (d.name, d.document_uid))


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _format_leaf(doc: VisibleDocument) -> str:
    # The Control Plane does not know file creation or modification dates.
    record: dict[str, str | None] = {
        "uid": doc.document_uid,
        "name": doc.name,
        "added_to_kb": _timestamp(doc.added_at),
        "created": None,
        "modified": None,
    }
    if doc.mime:
        record["mime_type"] = doc.mime
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def _format_folder(node: _Node) -> str:
    # JSON keeps newlines and punctuation in names on one tree line.
    record = {"folder": node.name}
    if node.folder_id:
        record["folder_id"] = node.folder_id
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def _render_tree(root: _Node, *, max_chars: int) -> tuple[str, bool]:
    """Prune the deepest level first until the text fits, then cut the top level."""
    text = _render(root, depth=0)
    if len(text) <= max_chars:
        return (text if text else "(empty)"), False

    # Each level is pruned once: re-pruning a placeholder level never shrinks the text.
    for depth in range(root.depth_of_deepest_branch(), 0, -1):
        _prune_deepest(root, depth)
        text = _render(root, depth=0)
        if len(text) <= max_chars:
            return text, True

    return _render_budgeted_root(root, max_chars=max_chars), True


def _render(node: _Node, *, depth: int) -> str:
    lines: list[str] = []
    indent = "  " * depth
    for child in _children(node):
        lines.append(f"{indent}{_format_folder(child)}")
        lines.append(_render(child, depth=depth + 1))
    lines.extend(f"{indent}{_format_leaf(doc)}" for doc in _leaves(node))
    lines.extend(f"{indent}{note}" for note in node.notes)
    return "\n".join(line for line in lines if line)


def _prune_deepest(node: _Node, target_depth: int, *, current_depth: int = 0) -> None:
    """Replace every child subtree exactly at `target_depth` with a placeholder."""
    if current_depth == target_depth - 1:
        for child in node.children.values():
            if child.children or child.docs:
                count = _count_items(child)
                child.children.clear()
                child.docs.clear()
                child.notes = [f"... {count} more item(s) below, {_FALLBACK_HINT}"]
        return
    for child in node.children.values():
        _prune_deepest(child, target_depth, current_depth=current_depth + 1)


def _count_items(node: _Node) -> int:
    total = len(node.docs)
    for child in node.children.values():
        total += 1 + _count_items(child)
    return total


def _render_budgeted_root(root: _Node, *, max_chars: int) -> str:
    """Keep whole top-level blocks (header plus its already-pruned content) that fit.

    Measuring the full block means pruned content is either shown or counted as
    omitted, never silently dropped between the two passes.
    """
    blocks = [
        f"{_format_folder(child)}\n{_render(child, depth=1)}".rstrip()
        for child in _children(root)
    ]
    # Reserve room for the longest possible omitted-count line.
    omitted_line = f"... {len(blocks)} more item(s) at this level, {_FALLBACK_HINT}"
    budget = max_chars - len(omitted_line) - 1

    lines: list[str] = []
    total = 0
    omitted = 0
    for i, block in enumerate(blocks):
        if total + len(block) + 1 > budget:
            omitted = len(blocks) - i
            break
        lines.append(block)
        total += len(block) + 1

    if omitted:
        lines.append(f"... {omitted} more item(s) at this level, {_FALLBACK_HINT}")
    return "\n".join(lines)
