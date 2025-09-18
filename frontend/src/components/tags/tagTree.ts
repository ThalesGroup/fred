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

import { TagWithItemsId } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";

// ---------- Types ----------
export type TagNode = {
  name: string;      // path segment (e.g., "SIX")
  full: string;      // full path (e.g., "SIX/DEV")
  children: Map<string, TagNode>;
  tagsHere: TagWithItemsId[]; // tags that end exactly at this node
};

// ---------- Path helpers ----------
export function fullPath(t: Pick<TagWithItemsId, "name" | "path">): string {
  return t.path && t.path.trim() ? `${t.path}/${t.name}` : t.name;
}

// ---------- Tree building ----------
export function buildTree(tags: TagWithItemsId[]): TagNode {
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

export function countUniqueDocs(node: TagNode): number {
  const docIds = new Set<string>();
  function dfs(n: TagNode) {
    n.tagsHere.forEach((t) => (t.item_ids || []).forEach((id) => docIds.add(id)));
    n.children.forEach((child) => dfs(child));
  }
  dfs(node);
  return docIds.size;
}
