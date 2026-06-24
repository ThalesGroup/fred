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

"""
Builds an indented text tree from a flat list of hierarchical document tags
(folders) plus their resolved document leaves.

Fred rationale:
- A document's tags are a list, so a document can sit under several folders at
  once (a DAG, not a strict tree). We render it as a leaf under each folder it
  belongs to -- the same way `tree`/`find` show a file reachable via more than
  one symlinked directory. No dedup needed.
- Returning a big flat JSON list of ids is hard for a caller (an LLM) to mentally
  reassemble into a filesystem shape, so we render readable indented text instead.
- When the rendering is too large for the caller's budget, we prune the deepest
  branches first rather than truncating the string mid-line, and tell the caller
  to use search or narrow `working_directory` instead of browsing everything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

_FALLBACK_HINT = "use search_documents_using_vectorization or narrow working_directory"


@dataclass
class DocLeaf:
    document_uid: str
    document_name: str
    created: Optional[datetime]


@dataclass
class TreeNode:
    """
    `notes` carries free-text lines rendered as-is alongside docs (e.g. pruning
    placeholders) -- kept separate from `docs` so every DocLeaf always represents
    a real document with a real uid; `_format_leaf` never has to handle a
    synthetic one.

    `tag_id` is the folder's tag id, rendered on the folder line so a caller can
    pass it back as a `document_library_tags_ids` / `tag_ids` filter. It is None
    for synthetic grouping nodes -- intermediate path segments that were never a
    real tag (e.g. "Sales" when only "Sales/HR" exists) have no id to filter on.
    """

    name: str
    full_path: str
    tag_id: Optional[str] = None
    children: Dict[str, "TreeNode"] = field(default_factory=dict)
    docs: List[DocLeaf] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def child(self, name: str, full_path: str) -> "TreeNode":
        if name not in self.children:
            self.children[name] = TreeNode(name=name, full_path=full_path)
        return self.children[name]

    def depth_of_deepest_branch(self) -> int:
        if not self.children:
            return 0
        return 1 + max(c.depth_of_deepest_branch() for c in self.children.values())


def build_tree(
    *,
    folders: List[Tuple],
    leaves_by_uid: Dict[str, Tuple[str, Optional[datetime]]],
) -> TreeNode:
    """
    `folders`: list of (full_path, item_ids) or (full_path, item_ids, tag_id)
    tuples, one per matched tag. The tag_id is optional for backward
    compatibility; when present it is attached to the matched folder node and
    rendered so callers can filter on it.
    `leaves_by_uid`: document_uid -> (document_name, created), resolved separately.

    Intermediate path segments that aren't themselves a real tag (e.g. "Sales" was
    never created but "Sales/HR" was) become synthetic grouping nodes with no docs
    of their own -- same as how a real filesystem tree shows an implied parent dir.
    Only the node whose full_path matches the tag gets the tag_id; synthesized
    ancestors keep tag_id=None.
    """
    root = TreeNode(name="", full_path="")
    for folder in folders:
        full_path, item_ids = folder[0], folder[1]
        tag_id = folder[2] if len(folder) > 2 else None
        segments = [s for s in full_path.split("/") if s]
        node = root
        acc: List[str] = []
        for seg in segments:
            acc.append(seg)
            node = node.child(seg, "/".join(acc))
        node.tag_id = tag_id
        for uid in item_ids:
            resolved = leaves_by_uid.get(uid)
            if resolved is None:
                continue
            name, created = resolved
            node.docs.append(DocLeaf(document_uid=uid, document_name=name, created=created))
    return root


def _format_leaf(doc: DocLeaf) -> str:
    when = doc.created.date().isoformat() if doc.created else "unknown date"
    return f"{doc.document_name} [{doc.document_uid}] (uploaded {when})"


def _format_folder(node: TreeNode) -> str:
    """Folder line: ``name/`` for synthetic grouping nodes, ``name [tag_id]/``
    for real tags -- the id is what a caller passes back as a tag filter."""
    if node.tag_id:
        return f"{node.name} [{node.tag_id}]/"
    return f"{node.name}/"


def render_tree(root: TreeNode, *, max_chars: int) -> Tuple[str, bool]:
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
    lines: List[str] = []
    indent = "  " * depth
    for child_name in sorted(node.children):
        child = node.children[child_name]
        lines.append(f"{indent}{_format_folder(child)}")
        lines.append(_render(child, depth=depth + 1))
    for doc in sorted(node.docs, key=lambda d: d.document_name):
        lines.append(f"{indent}{_format_leaf(doc)}")
    for note in node.notes:
        lines.append(f"{indent}{note}")
    return "\n".join(line for line in lines if line)


def _prune_deepest(node: TreeNode, target_depth: int, *, current_depth: int = 0) -> None:
    """Replace every child subtree exactly at `target_depth` with a placeholder."""
    if current_depth == target_depth - 1:
        for child in list(node.children.values()):
            if child.children or child.docs:
                count = _count_items(child)
                child.children.clear()
                child.docs.clear()
                child.notes = [f"... {count} more item(s) below, {_FALLBACK_HINT}"]
        return
    for child in node.children.values():
        _prune_deepest(child, target_depth, current_depth=current_depth + 1)


def _count_items(node: TreeNode) -> int:
    total = len(node.docs)
    for child in node.children.values():
        total += 1 + _count_items(child)
    return total


def _render_budgeted_root(node: TreeNode, *, max_chars: int) -> str:
    """Even the top level alone overflows: keep as many root-level lines as fit."""
    candidate_lines = [_format_folder(node.children[name]) for name in sorted(node.children)]
    candidate_lines += [_format_leaf(d) for d in sorted(node.docs, key=lambda d: d.document_name)]

    # Reserve room for the longest possible omitted-count line (its count can have
    # up to len(candidate_lines)'s digit count), so the line we append always fits.
    max_omitted_line = len(f"... {len(candidate_lines)} more item(s) at this level, {_FALLBACK_HINT}")
    budget = max_chars - max_omitted_line - 1  # -1 for its leading newline

    lines: List[str] = []
    total = 0
    for line in candidate_lines:
        if total + len(line) + 1 > budget:
            break
        lines.append(line)
        total += len(line) + 1

    omitted = len(candidate_lines) - len(lines)
    if omitted:
        lines.append(f"... {omitted} more item(s) at this level, {_FALLBACK_HINT}")
    return "\n".join(lines)
