// Copyright Thales 2026
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

export type MindMapEvidence = {
  sourceIndex?: number;
  quote?: string;
};

export type MindMapNode = {
  id: string;
  name: string;
  summary?: string;
  detail?: string;
  evidence?: MindMapEvidence[];
  children?: MindMapNode[];
};

export type MindMapPayload = {
  version?: string;
  title: string;
  summary?: string;
  root: MindMapNode;
  presentation?: {
    initialDepth?: number;
    layout?: "orthogonal" | "radial";
    focusMode?: boolean;
  };
};

export type ParsedMindMap =
  | {
      ok: true;
      payload: MindMapPayload;
      nodeCount: number;
    }
  | {
      ok: false;
      error: string;
      raw: string;
    };

const MAX_NODE_COUNT = 200;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function normalizeEvidence(value: unknown): MindMapEvidence[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter(isRecord)
    .map((item) => ({
      sourceIndex: typeof item.sourceIndex === "number" ? item.sourceIndex : undefined,
      quote: typeof item.quote === "string" ? item.quote : undefined,
    }));
}

function normalizeNode(value: unknown, fallbackId: string): MindMapNode | null {
  if (!isRecord(value)) return null;
  const id = typeof value.id === "string" && value.id.trim() ? value.id.trim() : fallbackId;
  const name = typeof value.name === "string" ? value.name.trim() : "";
  if (!name) return null;

  const rawChildren = Array.isArray(value.children) ? value.children : [];
  const children = rawChildren
    .map((child, index) => normalizeNode(child, `${id}-${index + 1}`))
    .filter((child): child is MindMapNode => child !== null);

  return {
    id,
    name,
    summary: typeof value.summary === "string" ? value.summary : undefined,
    detail: typeof value.detail === "string" ? value.detail : undefined,
    evidence: normalizeEvidence(value.evidence),
    children,
  };
}

function countNodes(node: MindMapNode): number {
  return 1 + (node.children ?? []).reduce((total, child) => total + countNodes(child), 0);
}

export function parseMindMapPayload(code: string): ParsedMindMap {
  let parsed: unknown;
  try {
    parsed = JSON.parse(code);
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : "Invalid JSON payload.",
      raw: code,
    };
  }

  if (!isRecord(parsed)) {
    return { ok: false, error: "Mindmap payload must be a JSON object.", raw: code };
  }

  const title = typeof parsed.title === "string" ? parsed.title.trim() : "";
  if (!title) {
    return { ok: false, error: "Mindmap payload is missing a non-empty title.", raw: code };
  }

  const root = normalizeNode(parsed.root, "root");
  if (!root) {
    return {
      ok: false,
      error: "Mindmap payload is missing a valid root node with id and name.",
      raw: code,
    };
  }

  const nodeCount = countNodes(root);
  if (nodeCount > MAX_NODE_COUNT) {
    return {
      ok: false,
      error: `Mindmap payload is too large to render safely (${nodeCount} nodes, limit ${MAX_NODE_COUNT}).`,
      raw: code,
    };
  }

  return {
    ok: true,
    nodeCount,
    payload: {
      version: typeof parsed.version === "string" ? parsed.version : "1.0",
      title,
      summary: typeof parsed.summary === "string" ? parsed.summary : undefined,
      root,
      presentation: isRecord(parsed.presentation)
        ? {
            initialDepth:
              typeof parsed.presentation.initialDepth === "number" ? parsed.presentation.initialDepth : undefined,
            layout:
              parsed.presentation.layout === "radial" || parsed.presentation.layout === "orthogonal"
                ? parsed.presentation.layout
                : undefined,
            focusMode:
              typeof parsed.presentation.focusMode === "boolean" ? parsed.presentation.focusMode : undefined,
          }
        : undefined,
    },
  };
}

export function findNodeById(node: MindMapNode, id: string): MindMapNode | null {
  if (node.id === id) return node;
  for (const child of node.children ?? []) {
    const match = findNodeById(child, id);
    if (match) return match;
  }
  return null;
}

export function findPathToNode(node: MindMapNode, id: string): MindMapNode[] | null {
  if (node.id === id) return [node];
  for (const child of node.children ?? []) {
    const path = findPathToNode(child, id);
    if (path) return [node, ...path];
  }
  return null;
}

export function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
