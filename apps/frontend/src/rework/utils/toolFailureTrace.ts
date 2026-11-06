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

import {
  asFailedSqlQueryResult,
  toolArgs,
  toolName,
  toolResultContent,
  toolResultOk,
  toolSlug,
  type TraceEntry,
} from "./traceUtils";
import { tabularToolKind } from "./tabularTrace";

// These exact Fred-owned messages are the versioned text boundary used by history.
const ERROR_MESSAGES: Record<string, string> = {
  "INVALID_ARGUMENTS: The tool rejected its arguments. Check the tool schema before correcting the request.":
    "invalidArguments",
  "AUTHENTICATION_REQUIRED: Authentication was refused (HTTP 401). Authentication must be restored before retrying.":
    "authentication",
  "RESOURCE_UNAVAILABLE: The requested resource is unavailable in this access scope (HTTP 403). Use only authorized discovered references.":
    "unavailable",
  "RESOURCE_UNAVAILABLE: The requested resource could not be resolved (HTTP 404). Check the discovered references and resource readiness.":
    "unavailable",
  "INVALID_ARGUMENTS: The tool rejected the argument format (HTTP 422). Check the tool schema before correcting the request.":
    "invalidArguments",
  "RATE_LIMITED: The service is rate limited (HTTP 429). Avoid repeating requests while the limit applies.":
    "rateLimited",
  "SERVICE_BUSY: The service is temporarily unavailable or at capacity (HTTP 503). A later attempt may succeed.":
    "busy",
  "TOOL_TIMEOUT: The operation exceeded its time budget (HTTP 504). Narrow the request before retrying.": "timeout",
  "SERVICE_ERROR: The service could not complete this operation (HTTP 500). No further safe diagnostic is available.":
    "service",
};

const ARGUMENTS: Record<string, string[]> = {
  list_tabular_documents: [],
  describe_tabular_documents: ["document_uids", "table_names"],
  get_tabular_document_markdown: ["document_uid"],
  get_tabular_documents_schemas: ["document_uids"],
  query_tabular_documents: ["dataset_uids", "sql", "max_rows"],
  search_tabular_values: ["dataset_uids", "keyword", "max_rows_per_table", "max_matching_tables"],
};

function displayArgument(value: unknown, budget = { remaining: 20000 }): unknown {
  if (typeof value === "string") {
    const redacted = value
      .replace(/https?:\/\/[^\s'"<>]+/gi, "[URL redacted]")
      .replace(/Bearer\s+[^\s'"<>]+/gi, "Bearer [redacted]");
    const preview = redacted.slice(0, budget.remaining);
    budget.remaining -= preview.length;
    return redacted.length > preview.length ? `${preview} [truncated]` : preview;
  }
  if (Array.isArray(value)) {
    const preview: unknown[] = [];
    for (const item of value.slice(0, 1000)) {
      if (budget.remaining === 0) break;
      preview.push(typeof item === "string" ? displayArgument(item, budget) : "[invalid argument type]");
    }
    return value.length > preview.length ? [...preview, "[truncated]"] : preview;
  }
  return value === null || typeof value === "number" || typeof value === "boolean" ? value : "[invalid argument type]";
}

/** Project recorded business arguments and safe diagnoses without revealing provider content. */
export function toolFailureDetail(entry: Extract<TraceEntry, { kind: "combo" }>) {
  if (!entry.result || toolResultOk(entry.result)) return null;
  const name = toolName(entry.call);
  const slug = toolSlug(name);
  const query = /^(?:mcp__knowledge_flow__)?query_tabular_documents(?:_\d+)?$/.test(name);
  const tabular = query || tabularToolKind(name) !== null;
  const content = toolResultContent(entry.result).trim();
  const errorKey = Object.prototype.hasOwnProperty.call(ERROR_MESSAGES, content) ? ERROR_MESSAGES[content] : undefined;
  if (!tabular && !errorKey) return null;
  const args = toolArgs(entry.call);
  const budget = { remaining: 20000 };
  const displayed = tabular
    ? Object.fromEntries(
        (ARGUMENTS[slug] ?? []).filter((key) => key in args).map((key) => [key, displayArgument(args[key], budget)]),
      )
    : null;
  const sqlFailure =
    query &&
    !errorKey &&
    /^(?:(?:Binder|Parser|Catalog|Conversion|Invalid Input|Invalid Type|Out of Range|Type Mismatch|Syntax) Error:|Invalid SQL query:|Exactly one SQL statement is allowed|Unable to parse SQL query|Query exceeded the per-query memory budget|Reading this dataset exceeded the per-query memory budget|Query references|Query uses|Table functions|No authorized|Description references|Empty SQL|Only SELECT)/.test(
      content,
    )
      ? asFailedSqlQueryResult(entry)
      : null;
  return {
    arguments: displayed,
    errorKey: `rework.chatTrace.failure.${errorKey ?? "unknown"}`,
    error: sqlFailure?.error ? String(displayArgument(sqlFailure.error)) : null,
  };
}
