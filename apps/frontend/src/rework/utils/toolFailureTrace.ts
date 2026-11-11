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
  toolResultFailure,
  toolSlug,
  type TraceEntry,
} from "./traceUtils";
import { tabularToolKind } from "./tabularTrace";
import { isLocalExchangeId } from "../core/hooks/chatSseUtils";

const ARGUMENTS: Record<string, string[]> = {
  read_conversation_file: ["document_id", "workspace_path"],
  publish_conversation_file: ["workspace_path", "path", "expected_content_id", "request_key"],
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

/** Project the recorded failure code, business arguments and safe diagnoses.
 *
 * The message comes only from `failure.code`; the result text guides the model
 * and never classifies the failure. It is shown only where its producer owns it.
 */
export function toolFailureDetail(entry: Extract<TraceEntry, { kind: "combo" }>) {
  const failure = entry.result ? toolResultFailure(entry.result) : null;
  if (!entry.result || !failure) return null;
  const name = toolName(entry.call);
  const slug = toolSlug(name);
  const query = /^(?:mcp__knowledge_flow__)?query_tabular_documents(?:_\d+)?$/.test(name);
  const tabular = query || tabularToolKind(name) !== null;
  const conversationFile = ["read_conversation_file", "publish_conversation_file"].includes(name);
  const args = toolArgs(entry.call);
  const budget = { remaining: 20000 };
  const displayed =
    tabular || conversationFile
      ? Object.fromEntries(
          (ARGUMENTS[slug] ?? []).filter((key) => key in args).map((key) => [key, displayArgument(args[key], budget)]),
        )
      : null;
  const sqlFailure = query ? asFailedSqlQueryResult(entry) : null;
  // A refusal by the person is a decision, not an incident to report.
  const declined = failure.code === "not_approved";
  return {
    arguments: displayed,
    errorKey: `rework.chatTrace.failure.${failure.code}`,
    status: failure.status ?? null,
    declined,
    // Only the runtime's exchange_id is in the logs; a browser-made one is not.
    reference: declined || isLocalExchangeId(entry.result.exchange_id) ? null : entry.result.exchange_id,
    // Conversation-file failures carry Fred's own recovery sentence; an
    // unexpected one may carry an uncaught exception text instead.
    error: sqlFailure?.error
      ? String(displayArgument(sqlFailure.error))
      : conversationFile && failure.code !== "unexpected"
        ? String(displayArgument(toolResultContent(entry.result).trim()))
        : null,
  };
}

export type ToolFailureDetail = NonNullable<ReturnType<typeof toolFailureDetail>>;

/** Current runtime failures carry a safe explanation and a server diagnostic reference.
 * Older provider dumps must not become visible when expanding inline errors. */
export function executionFailureText(text: string): string | null {
  return /^[^\r\n]+ Contact support with reference [a-f0-9]{32}\.$/.test(text.trim())
    ? String(displayArgument(text.trim()))
    : null;
}
