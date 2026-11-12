// @vitest-environment happy-dom
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

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ChatMessage } from "src/slices/runtime/runtimeOpenApi";
import type { TraceEntry } from "@rework/utils/traceUtils";
import { TraceDetailDrawer } from "./TraceDetailDrawer";
import i18next from "i18next";
import en from "src/locales/en/translation.json";
import fr from "src/locales/fr/translation.json";
import { writeRichClipboard } from "@rework/utils/clipboardUtils";
import * as sqlFormatting from "./formatSqlForDisplay";
import { toolResultContent } from "@rework/utils/traceUtils";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: i18next.t.bind(i18next), i18n: i18next }) }));
vi.mock("../../SourcesPanel/SourcesPanel", () => ({ SourcesPanel: () => null }));
vi.mock("../../MarkdownRenderer/MarkdownRenderer", () => ({ MarkdownRenderer: () => null }));
vi.mock("@rework/utils/clipboardUtils", () => ({ writeRichClipboard: vi.fn().mockResolvedValue(true) }));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;
beforeEach(async () => {
  vi.clearAllMocks();
  await i18next.init({ lng: "en", resources: { en: { translation: en }, fr: { translation: fr } } });
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

function queryEntry(
  rows: Record<string, unknown>[],
  sql = "SELECT * FROM d_table",
): Extract<TraceEntry, { kind: "combo" }> {
  const base: ChatMessage = {
    session_id: "session",
    exchange_id: "exchange",
    rank: 1,
    timestamp: "2026-01-01T00:00:00Z",
    role: "assistant",
    channel: "tool_call",
    parts: [],
  };
  return {
    kind: "combo",
    call: { ...base, parts: [{ type: "tool_call", name: "read_query", call_id: sql, args: { sql } }] },
    result: {
      ...base,
      role: "tool",
      channel: "tool_result",
      rank: 2,
      parts: [
        {
          type: "tool_result",
          call_id: sql,
          ok: true,
          content: JSON.stringify({ sql_query: sql, rows, error: null }),
          latency_ms: 390,
        },
      ],
    },
  };
}

it("opens a wide query with visible SQL and bounded DOM work", () => {
  const rows = Array.from({ length: 200 }, (_, row) =>
    Object.fromEntries(Array.from({ length: 64 }, (_, column) => [`column_${column}`, `value_${row}_${column}`])),
  );
  act(() => root.render(<TraceDetailDrawer entry={queryEntry(rows)} onClose={() => {}} />));
  expect(container.textContent).toContain("SELECT");
  expect(container.querySelectorAll("*").length).toBeLessThan(2500);
  expect(container.textContent).toContain("value_0_0");
  expect(container.textContent).not.toContain("value_5_0");
  expect(container.textContent).not.toContain("value_0_8");
});

async function copyBlock(index: number) {
  const buttons = [...container.querySelectorAll<HTMLButtonElement>("button")].filter(
    (button) => button.getAttribute("aria-label") === i18next.t("common.copyCode"),
  );
  await act(async () => buttons[index].click());
}

it("bounds long cells and nested values while copying the entire recorded response", async () => {
  const entry = queryEntry([
    { description: "long-cell-".repeat(2000), nested: { payload: "nested-".repeat(2000) }, amount: 0, missing: null },
  ]);
  act(() => root.render(<TraceDetailDrawer entry={entry} onClose={() => {}} />));
  expect(container.textContent.length).toBeLessThan(3000);
  expect(container.textContent).toContain("some columns or values are shortened");
  expect(container.textContent).not.toContain("nested-".repeat(10));
  await copyBlock(1);
  expect(writeRichClipboard).toHaveBeenLastCalledWith("", toolResultContent(entry.result));
});

it("bounds oversized SQL without formatting it and copies the complete original", async () => {
  const format = vi.spyOn(sqlFormatting, "formatSqlForDisplay");
  const sql = "SELECT " + "column_name, ".repeat(2000) + "last_column FROM d_table";
  act(() => root.render(<TraceDetailDrawer entry={queryEntry([], sql)} onClose={() => {}} />));
  expect(format).not.toHaveBeenCalled();
  expect(container.textContent).toContain("Long query preview");
  expect(container.textContent).not.toContain("last_column");
  expect(container.querySelectorAll("*").length).toBeLessThan(2500);
  await copyBlock(0);
  expect(writeRichClipboard).toHaveBeenLastCalledWith("", sql);
});

it("preserves the selected query through streaming updates, switching and reopening", () => {
  const format = vi.spyOn(sqlFormatting, "formatSqlForDisplay");
  const first = queryEntry([{ first_value: "first" }], "SELECT first_value FROM first_table");
  const second = queryEntry([{ second_value: "second" }], "SELECT second_value FROM second_table");
  const render = (entry: TraceEntry | null, messages: ChatMessage[] = []) =>
    act(() => root.render(<TraceDetailDrawer entry={entry} messages={messages} onClose={() => {}} />));
  render(first);
  const queryNode = container.querySelector("pre");
  render(first, [{ ...first.call, channel: "thought", parts: [{ type: "text", text: "streaming update" }] }]);
  expect(format).toHaveBeenCalledTimes(1);
  expect(container.querySelector("pre")).toBe(queryNode);
  render(second);
  expect(container.textContent).toContain("second_table");
  expect(container.textContent).not.toContain("first_table");
  render(null);
  render(first);
  expect(container.textContent).toContain("first_table");
  expect(container.textContent).not.toContain("second_table");
});

it.each(["en", "fr"])("labels payload estimates in %s and preserves them after reload", async (language) => {
  await i18next.changeLanguage(language);
  const entry = queryEntry(Array.from({ length: 20 }, () => ({ amount: 123 })));
  const render = (item: TraceEntry) => act(() => root.render(<TraceDetailDrawer entry={item} onClose={() => {}} />));
  render(entry);
  const inputLabel = i18next.t("rework.chatTrace.tokenEstimates.input", {
    value: Math.ceil(JSON.stringify({ sql: "SELECT * FROM d_table" }).length / 4).toLocaleString(language),
  });
  const outputLabel = i18next.t("rework.chatTrace.tokenEstimates.output", {
    value: Math.ceil(toolResultContent(entry.result).length / 4).toLocaleString(language),
  });
  expect(container.textContent).toContain(inputLabel);
  expect(container.textContent).toContain(outputLabel);
  expect(container.querySelectorAll("[tabindex='0']").length).toBeGreaterThanOrEqual(2);
  const before = container.textContent;
  render(JSON.parse(JSON.stringify(entry)));
  expect(container.textContent).toBe(before);
});

it("updates a pending output to an explicit empty output and keeps failure status", () => {
  const entry = queryEntry([]);
  act(() => root.render(<TraceDetailDrawer entry={{ ...entry, result: undefined }} onClose={() => {}} />));
  expect(container.textContent).toContain("Output unavailable");
  const result = {
    ...entry.result,
    parts: [{ type: "tool_result" as const, call_id: "SELECT * FROM d_table", content: "", ok: false, latency_ms: 1 }],
  };
  act(() => root.render(<TraceDetailDrawer entry={{ ...entry, result }} onClose={() => {}} />));
  expect(container.textContent).toContain("Output ~0 tokens");
  expect(container.querySelector("[data-status='failure']")).not.toBeNull();
});
