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

import { stripDocumentUids } from "./traceUtils";

export interface TreeDocument {
  uid: string;
  name: string;
  addedToKb: string | null;
  created: string | null;
  modified: string | null;
  legacyUploaded?: string;
  title?: string;
  format?: string;
  mimeType?: string;
  language?: string;
  pageCount?: number;
  rowCount?: number;
  labels: string[];
  source?: string;
}

export interface TreeFolder {
  path: string;
  documents: TreeDocument[];
}

export interface DocumentTreeTrace {
  folders: TreeFolder[];
  truncated: boolean;
  documentCount: number;
  latestUid: string | null;
}

const INCOMPLETE_PREFIX = "Listing incomplete:";

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function optionalText(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function count(value: unknown): number | undefined {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : undefined;
}

function timestamp(value: unknown): string | null {
  if (typeof value !== "string" || !/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value)) return null;
  return Number.isFinite(Date.parse(value)) ? value : null;
}

function documentRecord(value: unknown): TreeDocument | null {
  if (!record(value) || !optionalText(value.uid) || !optionalText(value.name)) return null;
  return {
    uid: value.uid as string,
    name: value.name as string,
    addedToKb: timestamp(value.added_to_kb),
    created: timestamp(value.created),
    modified: timestamp(value.modified),
    title: optionalText(value.title),
    format: optionalText(value.file_type),
    mimeType: optionalText(value.mime_type),
    language: optionalText(value.language),
    pageCount: count(value.page_count),
    rowCount: count(value.row_count),
    labels: Array.isArray(value.labels)
      ? value.labels.filter((label): label is string => typeof label === "string")
      : [],
    source: optionalText(value.source),
  };
}

// Date.parse drops submillisecond precision; compare that remainder separately.
function later(left: string, right: string): boolean {
  const delta = Date.parse(left) - Date.parse(right);
  if (delta !== 0) return delta > 0;
  const fraction = (value: string) => (value.match(/\.(\d+)/)?.[1] ?? "").padEnd(9, "0").slice(3, 9);
  return fraction(left) > fraction(right);
}

function treeText(text: string): string {
  if (!text.trimStart().startsWith("{")) return text;
  try {
    const envelope: unknown = JSON.parse(text);
    if (record(envelope) && envelope.tool_ref === "list_document_tree" && Array.isArray(envelope.blocks)) {
      return envelope.blocks
        .filter((block) => record(block) && block.kind === "text" && typeof block.text === "string")
        .map((block) => block.text)
        .join("\n");
    }
  } catch {
    // A tree contains multiple JSON lines, so it is not a single JSON envelope.
  }
  return text;
}

export function parseDocumentTreeTrace(text: string): DocumentTreeTrace | null {
  const folders: TreeFolder[] = [];
  const paths: string[] = [];
  const unique = new Map<string, TreeDocument>();
  const parents = new Set<string>();
  let truncated = false;
  let latest: TreeDocument | null = null;
  let recognized = false;
  const byPath = new Map<string, TreeFolder>();
  function folderAt(path: string): TreeFolder {
    let folder = byPath.get(path);
    if (!folder) {
      folder = { path, documents: [] };
      byPath.set(path, folder);
      folders.push(folder);
      const separator = path.lastIndexOf("/");
      if (separator >= 0) parents.add(path.substring(0, separator));
    }
    return folder;
  }

  for (const line of treeText(text).split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    if (trimmed === "(empty)") {
      recognized = true;
      continue;
    }
    if (trimmed.startsWith(INCOMPLETE_PREFIX) || /^\.\.\. \d+ more item\(s\)/.test(trimmed)) {
      truncated = true;
      recognized = true;
      continue;
    }
    const depth = line.length - line.trimStart().length;
    if (depth % 2 !== 0 || depth / 2 > paths.length) return null;
    let document: TreeDocument | null = null;
    const legacyFolder = trimmed.match(/^(.*?)(?: \[(?:folder:)?[^\]]+\])?\/$/);
    if (legacyFolder) {
      paths.length = depth / 2;
      paths.push(legacyFolder[1]);
      folderAt(paths.join("/"));
      recognized = true;
      continue;
    }
    if (trimmed.startsWith("{")) {
      try {
        const value: unknown = JSON.parse(trimmed);
        if (record(value) && typeof value.folder === "string") {
          paths.length = depth / 2;
          paths.push(value.folder);
          folderAt(paths.join("/"));
          recognized = true;
          continue;
        }
        document = documentRecord(value);
      } catch {
        return null;
      }
      if (!document) return null;
    } else {
      const legacy = trimmed.match(/^(.*) \[([^\]]+)\] \(uploaded (\d{4}-\d{2}-\d{2}|unknown date)\)$/);
      if (legacy) {
        document = {
          uid: legacy[2],
          name: legacy[1],
          addedToKb: null,
          created: null,
          modified: null,
          legacyUploaded: legacy[3],
          labels: [],
        };
      }
    }
    if (document) {
      // Documents at a shallower depth belong to that ancestor, not the last child.
      const path = paths.slice(0, depth / 2).join("/");
      folderAt(path).documents.push(document);
      unique.set(document.uid, document);
      if (document.addedToKb && (!latest?.addedToKb || later(document.addedToKb, latest.addedToKb))) latest = document;
      recognized = true;
      continue;
    }
    return null;
  }
  return recognized
    ? {
        folders: folders.filter((folder) => folder.documents.length > 0 || !parents.has(folder.path)),
        truncated,
        documentCount: unique.size,
        latestUid: latest?.uid ?? null,
      }
    : null;
}

export function historicalDocumentTreeText(text: string): string | null {
  const content = treeText(text);
  if (/"(?:uid|folder|tool_ref)"\s*:/.test(content) || !/\(uploaded (?:\d{4}-\d{2}-\d{2}|unknown date)\)/.test(content))
    return null;
  return stripDocumentUids(content);
}
