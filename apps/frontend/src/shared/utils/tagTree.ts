// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { TagWithItemsId, TagWithPermissions } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";

// ---------- Types ----------
export type TagNode = {
  name: string; // path segment (e.g., "SIX")
  full: string; // full path (e.g., "SIX/DEV")
  children: Map<string, TagNode>;
  tagsHere: TagWithPermissions[]; // tags that end exactly at this node
};

// ---------- Path helpers ----------
export function fullPath(t: Pick<TagWithItemsId, "name" | "path">): string {
  return t.path && t.path.trim() ? `${t.path}/${t.name}` : t.name;
}

// ---------- Tree building ----------
export function buildTree(tags: TagWithPermissions[]): TagNode {
  const root: TagNode = { name: "", full: "", children: new Map(), tagsHere: [] };
  for (const t of tags) {
    const p = fullPath(t);
    const parts = p.split("/").filter(Boolean);
    let cur = root;
    parts.forEach((seg, i) => {
      if (!cur.children.has(seg)) {
        cur.children.set(seg, {
          name: seg,
          full: i === 0 ? seg : `${cur.full}/${seg}`,
          children: new Map(),
          tagsHere: [],
        });
      }
      cur = cur.children.get(seg)!;
    });
    cur.tagsHere.push(t);
  }
  return root;
}

// ---------- Navigation ----------
export function findNode(root: TagNode, path: string | undefined): TagNode {
  if (!path) return root;
  const parts = path.split("/").filter(Boolean);
  let cur = root;
  for (const seg of parts) {
    const next = cur.children.get(seg);
    if (!next) return root; // fallback to root for unknown paths
    cur = next;
  }
  return cur;
}

// ---------- Aggregations ----------
export function collectDescendantTagIds(node: TagNode): string[] {
  const ids: string[] = [];
  function dfs(n: TagNode) {
    n.tagsHere.forEach((t) => ids.push(t.id));
    n.children.forEach((child) => dfs(child));
  }
  dfs(node);
  return Array.from(new Set(ids));
}

/**
 * Every tag at-or-under `node` (the node's own `tagsHere` plus every descendant's).
 * Used to rename a whole folder: a folder is a path prefix, so renaming it must
 * rewrite the path of every tag beneath it, not just the one ending at the node.
 */
export function collectDescendantTags(node: TagNode): TagWithPermissions[] {
  const tags: TagWithPermissions[] = [];
  function dfs(n: TagNode) {
    n.tagsHere.forEach((t) => tags.push(t));
    n.children.forEach((child) => dfs(child));
  }
  dfs(node);
  return tags;
}

/**
 * The new `{ name, path }` for one tag when its containing folder is renamed from
 * `oldFull` to `newFull`. The tag's leading `oldFull` prefix is swapped for
 * `newFull`, then the result is split back into leaf name + parent path. `tag`
 * must be at-or-under the folder (`fullPath(tag)` equals `oldFull` or starts with
 * `oldFull + "/"`); callers get that set from `collectDescendantTags`.
 */
export function rewriteTagUnderFolder(
  tag: Pick<TagWithItemsId, "name" | "path">,
  oldFull: string,
  newFull: string,
): { name: string; path: string } {
  const nextFull = `${newFull}${fullPath(tag).slice(oldFull.length)}`;
  const seg = nextFull.lastIndexOf("/");
  return {
    name: seg >= 0 ? nextFull.slice(seg + 1) : nextFull,
    path: seg >= 0 ? nextFull.slice(0, seg) : "",
  };
}

/**
 * Every `document_uid` tagged under `node`, its sub-folders included — a tag's
 * own `item_ids` never cover nested tags, same reason `collectDescendantTagIds`
 * exists. Deduplicated: a document is tagged into exactly one folder, but the
 * DFS is written not to rely on that.
 *
 * Snapshot semantics: `item_ids` only refreshes when the tag list is refetched,
 * so this is fine for a transient indicator but NOT for a count the user acts on
 * (see #2173 — the folder-deletion dialog counts live totals instead).
 */
export function collectDescendantDocUids(node: TagNode): Set<string> {
  const docIds = new Set<string>();
  function dfs(n: TagNode) {
    n.tagsHere.forEach((t) => (t.item_ids || []).forEach((id) => docIds.add(id)));
    n.children.forEach((child) => dfs(child));
  }
  dfs(node);
  return docIds;
}
