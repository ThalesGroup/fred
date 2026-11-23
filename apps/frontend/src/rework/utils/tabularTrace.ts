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

import type { TabularColumnDescription } from "src/slices/knowledgeFlow/knowledgeFlowOpenApi";

export type TabularToolKind = "documents" | "markdown" | "schemas" | "descriptions" | "search";

export type TabularTable = {
  query_alias: string;
  sheet?: string | null;
  title?: string | null;
  row_count?: number | null;
};

export type TabularDocument = {
  document_uid: string;
  document_name: string;
  kind: "csv" | "spreadsheet";
  tables: TabularTable[];
};

// Stored traces can contain older dtype labels and category metadata.
export type TabularColumn = Omit<TabularColumnDescription, "dtype"> & {
  dtype: string;
  is_categorical?: boolean | null;
  has_two_values?: boolean | null;
  sample_values?: string[] | null;
};

export type TabularSchemaDocument = Omit<TabularDocument, "tables"> & {
  tables: (TabularTable & { columns: TabularColumn[] })[];
};

export type TabularDescriptionDocument = TabularSchemaDocument & { markdown?: string | null };

export type TabularMatch = {
  document_uid: string;
  document_name: string;
  query_alias: string;
  sheet?: string | null;
  title?: string | null;
  matched_columns: string[];
  rows: Record<string, unknown>[];
  row_truncated: boolean;
};

export type TabularTraceResult =
  | { kind: "documents"; documents: TabularDocument[] }
  | { kind: "markdown"; documentUid: string; content: string }
  | { kind: "schemas"; documents: TabularSchemaDocument[] }
  | { kind: "descriptions"; documents: TabularDescriptionDocument[] }
  | { kind: "search"; keyword: string; matches: TabularMatch[]; tablesTruncated: boolean };

export const ROW_PREVIEW_COUNT = 5;
export const COLUMN_PREVIEW_COUNT = 8;
export const COLUMN_NAME_PREVIEW_CHARS = 80;
const CELL_PREVIEW_CHARS = 160;

export function clippedTabularText(text: string, limit: number): string {
  return text.length > limit ? `${text.slice(0, limit - 3)}...` : text;
}

export function previewTabularRows(
  rows: Record<string, unknown>[],
  { allColumns = false, rowLimit = ROW_PREVIEW_COUNT } = {},
) {
  let fieldsTruncated = false;
  const preview = rows.slice(0, rowLimit).map((row) => {
    const fields: [string, unknown][] = [];
    for (const name in row) {
      if (!Object.prototype.hasOwnProperty.call(row, name)) continue;
      if (!allColumns && fields.length === COLUMN_PREVIEW_COUNT) {
        fieldsTruncated = true;
        break;
      }
      const value = row[name];
      let display = value;
      if (typeof value === "string") display = clippedTabularText(value, CELL_PREVIEW_CHARS);
      else if (value !== null && typeof value === "object") display = "[...]";
      const columnName = allColumns ? name : clippedTabularText(name, COLUMN_NAME_PREVIEW_CHARS);
      if (display !== value || columnName !== name) fieldsTruncated = true;
      fields.push([columnName, display]);
    }
    return Object.fromEntries(fields);
  });
  return { rows: preview, fieldsTruncated };
}

const MCP_PREFIX = "mcp__knowledge_flow__";

export function isTabularQueryTool(rawName: string): boolean {
  return /^(?:mcp__knowledge_flow__)?read_query(?:_\d+)?$/.test(rawName);
}

/** Accept current and historical tabular tool names and their MCP forms. */
export function tabularToolKind(rawName: string): TabularToolKind | null {
  if (rawName.startsWith("mcp__") && !rawName.startsWith(MCP_PREFIX)) return null;
  const name = (rawName.startsWith(MCP_PREFIX) ? rawName.slice(MCP_PREFIX.length) : rawName).replace(/_\d+$/, "");
  switch (name) {
    case "list_tabular_documents":
      return "documents";
    case "get_tabular_document_markdown":
      return "markdown";
    case "get_tabular_documents_schemas":
      return "schemas";
    case "describe_tabular_documents":
      return "descriptions";
    case "search_tabular_values":
      return "search";
    default:
      return null;
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isOptionalString(value: unknown): boolean {
  return value == null || typeof value === "string";
}

function isOptionalRowCount(value: unknown): boolean {
  return value == null || (typeof value === "number" && Number.isFinite(value) && value >= 0);
}

function isTable(value: unknown): value is TabularTable {
  return (
    isObject(value) &&
    typeof value.query_alias === "string" &&
    isOptionalString(value.sheet) &&
    isOptionalString(value.title) &&
    isOptionalRowCount(value.row_count)
  );
}

function parseDocument(value: unknown): TabularDocument | null {
  if (!isObject(value) || typeof value.document_uid !== "string" || typeof value.document_name !== "string") {
    return null;
  }
  if (value.kind !== undefined && value.kind !== "csv" && value.kind !== "spreadsheet") return null;
  if (value.tables !== undefined && (!Array.isArray(value.tables) || !value.tables.every(isTable))) return null;
  if (value.kind !== undefined && value.tables === undefined) return null;

  const kind: TabularDocument["kind"] =
    value.kind === "csv" || value.kind === "spreadsheet"
      ? value.kind
      : value.tables === undefined
        ? "csv"
        : "spreadsheet";

  return {
    document_uid: value.document_uid,
    document_name: value.document_name,
    kind,
    tables: (value.tables as TabularTable[] | undefined) ?? [],
  };
}

function isColumn(value: unknown): value is TabularColumn {
  return (
    isObject(value) &&
    typeof value.name === "string" &&
    typeof value.dtype === "string" &&
    (value.categorical_values == null ||
      (Array.isArray(value.categorical_values) &&
        value.categorical_values.every((category) => typeof category === "string"))) &&
    (value.is_categorical == null || typeof value.is_categorical === "boolean") &&
    (value.has_two_values == null || typeof value.has_two_values === "boolean") &&
    (value.sample_values == null ||
      (Array.isArray(value.sample_values) && value.sample_values.every((sample) => typeof sample === "string"))) &&
    (value.min_value == null || (typeof value.min_value === "number" && Number.isFinite(value.min_value))) &&
    (value.max_value == null || (typeof value.max_value === "number" && Number.isFinite(value.max_value)))
  );
}

function isSchemaTable(value: unknown): value is TabularTable & { columns: TabularColumn[] } {
  const columns = isObject(value) ? value.columns : null;
  return isTable(value) && Array.isArray(columns) && columns.every(isColumn);
}

function isSchemaDocument(value: unknown): value is TabularSchemaDocument {
  return (
    isObject(value) &&
    typeof value.document_uid === "string" &&
    typeof value.document_name === "string" &&
    (value.kind === "csv" || value.kind === "spreadsheet") &&
    Array.isArray(value.tables) &&
    value.tables.every(isSchemaTable)
  );
}

function isDescriptionDocument(value: unknown): value is TabularDescriptionDocument {
  if (!isSchemaDocument(value)) return false;
  const markdown = (value as Record<string, unknown>).markdown;
  return value.kind === "spreadsheet" ? typeof markdown === "string" : markdown == null;
}

function isMatch(value: unknown): value is TabularMatch {
  return (
    isObject(value) &&
    typeof value.document_uid === "string" &&
    typeof value.document_name === "string" &&
    typeof value.query_alias === "string" &&
    isOptionalString(value.sheet) &&
    isOptionalString(value.title) &&
    Array.isArray(value.matched_columns) &&
    value.matched_columns.every((column) => typeof column === "string") &&
    Array.isArray(value.rows) &&
    value.rows.every(isObject) &&
    typeof value.row_truncated === "boolean"
  );
}

/** Validate the response before any field crosses into the user-facing trace. */
export function parseTabularTraceResult(rawName: string, content: string): TabularTraceResult | null {
  const kind = tabularToolKind(rawName);
  if (!kind) return null;

  let parsed: unknown;
  try {
    parsed = JSON.parse(content);
  } catch {
    return null;
  }

  // MCP wraps non-object responses in a result envelope. Keep the payload validation below.
  if (isObject(parsed) && Object.keys(parsed).length === 1 && Array.isArray(parsed.result)) {
    parsed = parsed.result;
  }

  switch (kind) {
    case "documents": {
      if (!Array.isArray(parsed)) return null;
      const documents = parsed.map(parseDocument);
      return documents.every((document): document is TabularDocument => document !== null) ? { kind, documents } : null;
    }
    case "markdown":
      return isObject(parsed) && typeof parsed.document_uid === "string" && typeof parsed.content === "string"
        ? { kind, documentUid: parsed.document_uid, content: parsed.content }
        : null;
    case "schemas":
      return Array.isArray(parsed) && parsed.every(isSchemaDocument) ? { kind, documents: parsed } : null;
    case "descriptions":
      return Array.isArray(parsed) && parsed.every(isDescriptionDocument) ? { kind, documents: parsed } : null;
    case "search":
      return isObject(parsed) &&
        typeof parsed.keyword === "string" &&
        typeof parsed.normalized_keyword === "string" &&
        Array.isArray(parsed.matches) &&
        parsed.matches.every(isMatch) &&
        typeof parsed.tables_truncated === "boolean" &&
        Array.isArray(parsed.searched_dataset_uids) &&
        parsed.searched_dataset_uids.every((uid) => typeof uid === "string")
        ? { kind, keyword: parsed.keyword, matches: parsed.matches, tablesTruncated: parsed.tables_truncated }
        : null;
  }
}
