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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatMessage } from "../../../../../slices/runtime/runtimeOpenApi";
import { toolCallId, type TraceEntry } from "../../../../utils/traceUtils";
import { ThoughtTrace } from "./ThoughtTrace";
import { ToolTraceGroup } from "./ToolTraceGroup/ToolTraceGroup";
import { TraceDrawerProvider } from "./traceDrawerContext";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) => {
      if (key === "rework.chatTrace.toolLabels.codeSandbox") return "Code in sandbox";
      if (key === "rework.chatTrace.toolGroups.commands")
        return `${values?.count} ${values?.count === 1 ? "command" : "commands"}`;
      if (key === "rework.chatTrace.toolGroups.pythonScript")
        return `Python script (${values?.count} ${values?.count === 1 ? "line" : "lines"})`;
      if (key === "rework.chatTrace.toolGroups.shellScript")
        return `Shell script (${values?.count} ${values?.count === 1 ? "line" : "lines"})`;
      if (key === "rework.chatTrace.toolGroups.pythonScriptUncounted") return "Python script";
      if (key === "rework.chatTrace.toolGroups.shellScriptUncounted") return "Shell script";
      if (key === "test.summaries") return `${values?.count} summaries`;
      return key;
    },
  }),
}));

vi.mock("@shared/atoms/Icon/Icon", () => ({
  default: ({ type }: { type: string }) => <span data-icon={type} />,
}));

function msg(channel: ChatMessage["channel"], parts: ChatMessage["parts"], rank: number): ChatMessage {
  return {
    session_id: "s",
    exchange_id: "e",
    rank,
    timestamp: "2026-01-01T00:00:00Z",
    role: "assistant",
    channel,
    parts,
  };
}

function call(id: string, name: string, code: string, rank: number): ChatMessage {
  return msg("tool_call", [{ type: "tool_call", call_id: id, name, args: { code } }], rank);
}

function result(id: string, rank: number): ChatMessage {
  return {
    ...msg("tool_result", [{ type: "tool_result", call_id: id, ok: true, content: "done" }], rank),
    role: "tool",
  };
}

const opened: string[] = [];
let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  localStorage.clear();
  opened.length = 0;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function renderTrace(messages: ChatMessage[], pendingToolCallIds?: readonly string[]) {
  act(() => {
    root.render(
      <TraceDrawerProvider
        value={{
          openTrace: (entry: TraceEntry) => opened.push(entry.kind === "combo" ? toolCallId(entry.call) : "reasoning"),
        }}
      >
        <ThoughtTrace messages={messages} done={false} pendingToolCallIds={pendingToolCallIds} />
      </TraceDrawerProvider>,
    );
  });
}

function groups(): HTMLButtonElement[] {
  return [...container.querySelectorAll<HTMLButtonElement>("button[aria-expanded]")].filter((button) =>
    button.textContent?.includes("Code in sandbox"),
  );
}

describe("ThoughtTrace code groups", () => {
  it("keeps reasoning between code calls and starts a new group after another tool", () => {
    renderTrace([
      call("c1", "execute_code", "find /inputs -name '*.txt'", 1),
      result("c1", 2),
      msg("thought", [{ type: "text", text: "Search the matching file next" }], 3),
      call("c2", "execute_code", "python -c 'print(42)'", 4),
      result("c2", 5),
      call("s1", "summarize_document", "", 6),
      result("s1", 7),
      call("c3", "execute_code", "python analyze.py", 8),
      result("c3", 9),
    ]);

    expect(groups()).toHaveLength(2);
    expect(groups()[0].textContent).toContain("2 commands");
    expect(groups()[1].textContent).toContain("1 command");
    expect(groups()[0].getAttribute("aria-label")).toMatch(/^1\. /);
    expect(groups()[1].getAttribute("aria-label")).toMatch(/^3\. /);
    const summary = [...container.querySelectorAll('[role="button"]')].find((node) =>
      node.getAttribute("aria-label")?.includes("Summarize Document"),
    );
    expect(summary).toBeDefined();
    expect(groups()[0].compareDocumentPosition(summary!)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(summary!.compareDocumentPosition(groups()[1])).toBe(Node.DOCUMENT_POSITION_FOLLOWING);

    act(() => groups()[0].click());
    expect(container.textContent).toContain("Search the matching file next");
    const secondCommand = container.querySelector<HTMLButtonElement>('button[aria-label^="python -c"]');
    expect(secondCommand).toBeDefined();
    expect(secondCommand!.textContent).not.toContain("Command 2");
    expect(secondCommand!.textContent).not.toContain("toolStatus.success");
    expect(secondCommand!.getAttribute("aria-label")).toContain("python -c 'print(42)'");
    expect(secondCommand!.getAttribute("aria-label")).toContain("toolStatus.success");
    act(() => secondCommand!.click());
    expect(opened).toEqual(["c2"]);
  });

  it("keeps a group open and previews the current command as streaming calls arrive", () => {
    const first = call("c1", "execute_code", "find /inputs -name '*.csv'\necho hidden", 1);
    renderTrace([first]);
    const group = groups()[0];
    expect(group.textContent).toContain("find /inputs -name '*.csv'");
    expect(group.textContent).toContain("find /inputs -name '*.csv' ...");
    expect(group.textContent).not.toContain("echo hidden");
    act(() => group.click());

    const second = call("c2", "execute_code", "grep -Fi phrase /inputs/table.csv", 3);
    renderTrace([first, result("c1", 2), second]);
    expect(groups()).toHaveLength(1);
    expect(groups()[0]).toBe(group);
    expect(group.getAttribute("aria-expanded")).toBe("true");
    expect(group.textContent).toContain("grep -Fi phrase /inputs/table.csv");
    const firstCommand = [...container.querySelectorAll("button")].find((button) =>
      button.textContent?.includes("find /inputs -name '*.csv' ..."),
    );
    act(() => firstCommand!.click());
    expect(opened).toEqual(["c1"]);
  });

  it("bounds a long command preview and keeps it on one line", () => {
    renderTrace([call("c1", "execute_code", `grep ${"x".repeat(200)}\necho later`, 1)]);
    const text = groups()[0].textContent ?? "";
    expect(text).toContain("...");
    expect(text).not.toContain("echo later");
    expect(text).not.toContain("\n");
    act(() => groups()[0].click());
    const child = [...container.querySelectorAll("button")].find((button) => button.textContent?.startsWith("grep "));
    expect(child?.textContent).toContain("...");
    expect(child?.textContent).not.toContain("echo later");
  });

  it("hides an unlabeled Python heredoc launcher behind a neutral script label", () => {
    renderTrace([
      call(
        "c1",
        "execute_code",
        "python - <<'PY'\nfrom pypdf import PdfReader\nfor page in reader.pages:\n    print(page)\nPY",
        1,
      ),
    ]);
    expect(groups()[0].textContent).toContain("Python script (3 lines)");
    expect(groups()[0].textContent).not.toContain("<<'PY'");
    expect(groups()[0].textContent).not.toContain("from pypdf import PdfReader");
    act(() => groups()[0].click());
    const child = [...container.querySelectorAll("button")].find((button) =>
      button.textContent?.includes("Python script (3 lines)"),
    );
    expect(child?.textContent).not.toContain("from pypdf");
    expect(child?.getAttribute("aria-label")).toContain("Python script (3 lines)");
  });

  it("uses a leading intent comment without guessing a Python body line", () => {
    renderTrace([
      call(
        "c1",
        "execute_code",
        "# Search HELIOS-4821 in the attached PDF\npython - <<'PY'\nfrom pypdf import PdfReader\nif \"HELIOS-4821\" in text:\n    print(text)\nPY",
        1,
      ),
    ]);
    expect(groups()[0].textContent).toContain("Search HELIOS-4821 in the attached PDF");
    expect(groups()[0].textContent).not.toContain("<<'PY'");
    expect(groups()[0].textContent).not.toContain('if "HELIOS-4821"');
  });

  it("keeps the command count and current intent in the group heading", () => {
    renderTrace([
      call("c1", "execute_code", "# Locate the workbook\nfind /inputs -name '*.xlsx'", 1),
      result("c1", 2),
      call("c2", "execute_code", "# Calculate the Lyon margin\npython - <<'PY'\nprint(41.22)\nPY", 3),
    ]);
    expect(groups()[0].textContent).toContain("2 commands");
    expect(groups()[0].textContent).toContain("Calculate the Lyon margin");
    expect(groups()[0].textContent).not.toContain("Locate the workbook");
    act(() => groups()[0].click());
    expect(container.textContent).toContain("Locate the workbook");
    expect(container.textContent).toContain("Calculate the Lyon margin");
  });

  it("uses a neutral shell label for another heredoc", () => {
    renderTrace([call("c1", "execute_code", "cat <<EOF\nhello\nEOF", 1)]);
    expect(groups()[0].textContent).toContain("Shell script (1 line)");
    expect(groups()[0].textContent).not.toContain("<<EOF");
  });

  it.each([
    "python <<'PY'",
    "python3 -u - <<'PY'",
    "/usr/bin/python3.12 <<'PY'",
    "python<<'PY'",
    "python - <<'PY' # calculate answer",
  ])("recognizes a Python heredoc launched with %s", (launcher) => {
    renderTrace([call("c1", "execute_code", `${launcher}\nprint(42)\nPY`, 1)]);
    expect(groups()[0].textContent).toContain("Python script (1 line)");
  });

  it("does not claim a source line count for an unfinished heredoc", () => {
    renderTrace([call("c1", "execute_code", "python <<'PY'\nprint(42)", 1)]);
    expect(groups()[0].textContent).toContain("Python script");
    expect(groups()[0].textContent).not.toContain("lines");
    expect(groups()[0].textContent).not.toContain("<<'PY'");
  });

  it("keeps an unfamiliar heredoc launcher out of the preview", () => {
    renderTrace([call("c1", "execute_code", "python - <<'PY' > /tmp/out\nprint(42)\nPY", 1)]);
    expect(groups()[0].textContent).toContain("Python script");
    expect(groups()[0].textContent).not.toContain("<<'PY'");
    expect(groups()[0].textContent).not.toContain("lines");
  });

  it("recognizes an intent comment after a shell shebang", () => {
    renderTrace([
      call("c1", "execute_code", "#!/bin/bash\n# Search the mounted corpus\ngrep -Fi term /inputs/corpus/file", 1),
    ]);
    expect(groups()[0].textContent).toContain("Search the mounted corpus");
    expect(groups()[0].textContent).not.toContain("#!/bin/bash");
  });

  it("splits groups at a write_todos call that the ordinary trace hides", () => {
    renderTrace([
      call("c1", "execute_code", "echo first", 1),
      result("c1", 2),
      msg(
        "tool_call",
        [
          {
            type: "tool_call",
            call_id: "todo",
            name: "write_todos",
            args: { todos: [{ content: "Inspect", status: "pending" }] },
          },
        ],
        3,
      ),
      result("todo", 4),
      call("c2", "execute_code", "echo second", 5),
      result("c2", 6),
    ]);
    expect(groups()).toHaveLength(2);
    expect(groups().map((group) => group.textContent)).toEqual([
      expect.stringContaining("echo first"),
      expect.stringContaining("echo second"),
    ]);
  });

  it("shows cancellation rather than an execution failure in a grouped child", () => {
    const cancelled = {
      ...result("c1", 2),
      parts: [{ type: "tool_result" as const, call_id: "c1", ok: false, content: "cancelled" }],
      metadata: { extras: { cancelled_by_user: true } },
    };
    renderTrace([call("c1", "execute_code", "echo first", 1), cancelled]);
    act(() => groups()[0].click());
    expect(container.textContent).toContain("rework.chatTrace.cancelledByUser");
    expect(container.textContent).not.toContain("rework.chatTrace.toolStatus.failure");
  });

  it("takes the group count label from a different tool family's rule", () => {
    act(() => {
      root.render(
        <ToolTraceGroup
          group={{
            kind: "group",
            key: "summaries:s1",
            rows: [],
            count: 2,
            index: 1,
            rule: {
              id: "summaries",
              titleKey: "test.title",
              countKey: "test.summaries",
              matches: () => false,
              itemLabel: () => "Summary",
              preview: () => "",
            },
          }}
        />,
      );
    });
    expect(container.textContent).toContain("2 summaries");
    expect(container.textContent).not.toContain("2 commands");
  });

  it.each([
    { state: "running", result: false, awaiting: false, expected: "rework.chatTrace.toolStatus.running" },
    { state: "awaiting", result: false, awaiting: true, expected: "rework.chatTrace.awaitingConfirmation" },
    { state: "failed", result: true, awaiting: false, expected: "rework.chatTrace.toolStatus.failure" },
  ])("announces a collapsed $state group to assistive technology", ({ result: hasResult, awaiting, expected }) => {
    const failed = {
      ...result("c1", 2),
      parts: [{ type: "tool_result" as const, call_id: "c1", ok: false, content: "failed" }],
    };
    renderTrace([call("c1", "execute_code", "echo first", 1), ...(hasResult ? [failed] : [])], awaiting ? ["c1"] : []);
    expect(groups()[0].getAttribute("aria-label")).toContain(expected);
  });
});
