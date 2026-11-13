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

it.each([20, 64])("shows every returned column across five preview rows with %i columns", (columnCount) => {
  const rows = Array.from({ length: 200 }, (_, row) =>
    Object.fromEntries(
      Array.from({ length: columnCount }, (_, column) => [`column_${column}`, `value_${row}_${column}`]),
    ),
  );
  act(() => root.render(<TraceDetailDrawer entry={queryEntry(rows)} onClose={() => {}} />));
  const preview = JSON.parse(container.querySelectorAll("pre code")[1].textContent ?? "[]");
  expect(preview).toEqual(rows.slice(0, 5));
  expect(container.textContent).not.toContain("value_5_0");
});

it("preserves distinct complete column names when their prefixes match", () => {
  const prefix = "long_column_name_".repeat(8);
  const rows = [{ [`${prefix}first`]: 1, [`${prefix}second`]: 2 }];
  act(() => root.render(<TraceDetailDrawer entry={queryEntry(rows)} onClose={() => {}} />));
  const preview = JSON.parse(container.querySelectorAll("pre code")[1].textContent ?? "[]");
  expect(preview).toEqual(rows);
});

it("opens a wide query with visible SQL and bounded DOM work", () => {
  const rows = Array.from({ length: 200 }, (_, row) =>
    Object.fromEntries(Array.from({ length: 64 }, (_, column) => [`column_${column}`, `value_${row}_${column}`])),
  );
  act(() => root.render(<TraceDetailDrawer entry={queryEntry(rows)} onClose={() => {}} />));
  expect(container.textContent).toContain("SELECT");
  const previewNodeCount = container.querySelectorAll("pre")[1].querySelectorAll("*").length;
  expect(container.textContent).toContain("value_0_0");
  expect(container.textContent).not.toContain("value_5_0");
  expect(container.textContent).toContain("value_0_63");
  act(() => root.render(<TraceDetailDrawer entry={queryEntry(rows.slice(0, 5))} onClose={() => {}} />));
  expect(container.querySelectorAll("pre")[1].querySelectorAll("*").length).toBe(previewNodeCount);
});

async function copyBlock(index: number) {
  const buttons = [...container.querySelectorAll<HTMLButtonElement>("button")].filter(
    (button) => button.getAttribute("aria-label") === i18next.t("common.copyCode"),
  );
  await act(async () => buttons[index].click());
}

it("retains the previous JSON syntax colors in the response preview", () => {
  act(() =>
    root.render(<TraceDetailDrawer entry={queryEntry([{ label: "Project Alpha", amount: 123 }])} onClose={() => {}} />),
  );
  const response = container.querySelectorAll("pre code")[1];
  const tokens = [...(response?.querySelectorAll<HTMLElement>("span[style]") ?? [])];
  const property = tokens.find((token) => token.textContent === '"label"');
  const value = tokens.find((token) => token.textContent === '"Project Alpha"');
  expect(property?.textContent).toContain("label");
  expect(value?.textContent).toContain("Project Alpha");
  expect(property?.style.color).toBeTruthy();
  expect(value?.style.color).toBeTruthy();
  expect(property?.style.color).not.toBe(value?.style.color);
});

it("bounds long cells and nested values while copying the entire recorded response", async () => {
  const entry = queryEntry([
    { description: "long-cell-".repeat(2000), nested: { payload: "nested-".repeat(2000) }, amount: 0, missing: null },
  ]);
  act(() => root.render(<TraceDetailDrawer entry={entry} onClose={() => {}} />));
  expect(container.textContent.length).toBeLessThan(3000);
  expect(container.textContent).toContain("some values shortened");
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

it.each(["en", "fr"])("does not invent token counts from the payload in %s", async (language) => {
  await i18next.changeLanguage(language);
  act(() => root.render(<TraceDetailDrawer entry={queryEntry([{ amount: 123 }])} onClose={() => {}} />));
  const header = container.querySelector("aside")?.firstElementChild?.firstElementChild;
  expect(header?.textContent).not.toContain("~");
  expect(header?.textContent).not.toMatch(/tokens|indisponible|unavailable/i);
  expect(header?.textContent).toContain("390ms");
});

it("keeps running and failure status without guessing token usage", () => {
  const entry = queryEntry([]);
  act(() => root.render(<TraceDetailDrawer entry={{ ...entry, result: undefined }} onClose={() => {}} />));
  expect(container.querySelector("[data-status='running']")).not.toBeNull();
  const result = {
    ...entry.result,
    parts: [{ type: "tool_result" as const, call_id: "SELECT * FROM d_table", content: "", ok: false, latency_ms: 1 }],
  };
  act(() => root.render(<TraceDetailDrawer entry={{ ...entry, result }} onClose={() => {}} />));
  expect(container.textContent).not.toContain("~0 tokens");
  expect(container.querySelector("[data-status='failure']")).not.toBeNull();
});

it.each(["en", "fr"])(
  "retains one compact preview sentence without model token attribution in %s",
  async (language) => {
    await i18next.changeLanguage(language);
    const entry = queryEntry(
      Array.from({ length: 200 }, () => Object.fromEntries(Array.from({ length: 60 }, (_, i) => [`column${i}`, i]))),
    );
    entry.call.metadata = { model_call_usage: { input_tokens: 20077, output_tokens: 644, tool_call_count: 2 } };
    entry.result!.metadata = { model_call_usage: { input_tokens: 103991, output_tokens: 2956 } };
    act(() => root.render(<TraceDetailDrawer entry={entry} onClose={() => {}} />));
    const header = container.querySelector("aside")?.firstElementChild?.firstElementChild;
    expect(header?.textContent).not.toMatch(/tokens|103.?991|2.?956/i);
    expect(container.textContent).not.toMatch(/Mesures API|API measurements/);
    const notices = [...container.querySelectorAll("p")].filter((p) =>
      p.textContent?.includes(language === "fr" ? "Aperçu de" : "Preview of"),
    );
    expect(notices).toHaveLength(1);
    expect(notices[0].textContent).toContain(language === "fr" ? "5 lignes sur 200" : "5 rows out of 200");
    expect(notices[0].textContent).toContain(
      language === "fr" ? "réponse enregistrée complète" : "complete recorded response",
    );
    expect(notices[0].textContent?.match(/\./g)).toHaveLength(1);
  },
);

it("does not present model zero or missing usage as a tool token count", () => {
  const entry = queryEntry([]);
  entry.result!.metadata = { model_call_usage: { input_tokens: 0 } };
  act(() => root.render(<TraceDetailDrawer entry={entry} onClose={() => {}} />));
  const header = container.querySelector("aside")?.firstElementChild?.firstElementChild;
  expect(header?.textContent).not.toMatch(/tokens|unavailable/i);
  expect(container.querySelector("[data-status='success']")).not.toBeNull();
});

it("keeps global API usage out of one-row tool details during streaming and reload", () => {
  const entry = queryEntry([{ id: 7, valeur: "site", regle_enfreinte: "REG-019" }]);
  entry.call.metadata = { model_call_usage: { input_tokens: 58774, output_tokens: 228 } };
  const final: ChatMessage = {
    ...entry.call,
    rank: 4,
    channel: "final",
    parts: [{ type: "text", text: "done" }],
    metadata: { model_call_usage: { input_tokens: 59260, output_tokens: 12426, tool_call_count: 0 } },
  };
  const render = (selected: TraceEntry, messages: ChatMessage[]) =>
    act(() => root.render(<TraceDetailDrawer entry={selected} messages={messages} onClose={() => {}} />));
  const assertToolScope = () => {
    const header = container.querySelector("aside")?.firstElementChild?.firstElementChild;
    expect(header?.textContent?.replace(/[\s,]/g, "")).not.toMatch(/59260|12426|58774|tokens|unavailable/i);
    expect(container.textContent).not.toContain("API measurements for the LLM exchange");
    expect(header?.textContent).toContain("390ms");
    expect(container.textContent).toContain("REG-019");
  };
  render(entry, [entry.call, entry.result!]);
  assertToolScope();
  const query = container.querySelector("pre");
  const messages = [entry.call, entry.result!, final];
  render(entry, messages);
  assertToolScope();
  expect(container.querySelector("pre")).toBe(query);
  render(JSON.parse(JSON.stringify(entry)), JSON.parse(JSON.stringify(messages)));
  assertToolScope();
});

it("does not expose full-context usage on failed or unknown tools", () => {
  const entry = queryEntry([]);
  entry.result!.metadata = { model_call_usage: { input_tokens: 59260, output_tokens: 12426 } };
  entry.result!.parts = [{ type: "tool_result", call_id: "c", content: "", ok: false }];
  act(() => root.render(<TraceDetailDrawer entry={entry} onClose={() => {}} />));
  expect(container.querySelector("[data-status='failure']")).not.toBeNull();
  expect(container.querySelector("aside")?.firstElementChild?.textContent).not.toMatch(/tokens|59.?260/i);
  entry.call.parts = [{ type: "tool_call", name: "custom_tool", call_id: "c", args: {} }];
  act(() => root.render(<TraceDetailDrawer entry={{ ...entry, call: { ...entry.call } }} onClose={() => {}} />));
  expect(container.querySelector("aside")?.firstElementChild?.textContent).not.toMatch(/tokens|59.?260/i);
});
