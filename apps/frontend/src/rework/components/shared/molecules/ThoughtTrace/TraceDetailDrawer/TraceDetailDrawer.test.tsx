// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0

import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { ChatMessage } from "../../../../../../slices/runtime/runtimeOpenApi";
import type { TraceEntry } from "../../../../../utils/traceUtils";
import { TraceDetailDrawer } from "./TraceDetailDrawer";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { count?: number; duration?: string }) => {
      if (key === "rework.chatTrace.sqlQuery") return "Query";
      if (key === "rework.chatTrace.sqlResponse") return "Response";
      if (key === "rework.chatTrace.rows") return `${options?.count ?? 0} rows`;
      if (key === "rework.chatTrace.toolLabels.readQuery") return "Reading query";
      if (key === "rework.chatTrace.toolStatus.failure") return "Failed";
      if (key === "rework.chatTrace.toolStatus.success") return "Success";
      if (key === "rework.chatTrace.executionTime") return `Execution time: ${options?.duration ?? ""}`;
      return key;
    },
  }),
}));

vi.mock("@shared/atoms/IconButton/IconButton", () => ({
  default: ({ "aria-label": ariaLabel }: { "aria-label": string }) => <button aria-label={ariaLabel} />,
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn() }),
}));

vi.mock("../../CodeBlock/CodeBlock", () => ({
  CodeBlock: ({
    code,
    copyText,
    language,
    hideCopy,
  }: {
    code: string;
    copyText?: string;
    language?: string;
    hideCopy?: boolean;
  }) => (
    <div>
      <pre data-language={language} data-copy-text={copyText}>
        {code}
      </pre>
      {!hideCopy && <button aria-label="Copy code">Copy</button>}
    </div>
  ),
}));

vi.mock("../../InlineDrawer/InlineDrawer", () => ({
  InlineDrawer: ({
    title,
    titleAccessory,
    children,
  }: {
    title: string;
    titleAccessory?: ReactNode;
    children: ReactNode;
  }) => (
    <section aria-label={title}>
      <header>
        {title}
        {titleAccessory}
      </header>
      {children}
    </section>
  ),
}));

function message(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    session_id: "s1",
    exchange_id: "e1",
    rank: 0,
    timestamp: "2026-01-01T00:00:00.000Z",
    role: "assistant",
    channel: "final",
    parts: [],
    ...overrides,
  };
}

describe("TraceDetailDrawer read_query failure", () => {
  it("shows the submitted SQL and engine error without HTTP transport details", () => {
    const entry: TraceEntry = {
      kind: "combo",
      call: message({
        channel: "tool_call",
        parts: [
          {
            type: "tool_call",
            call_id: "call-1",
            name: "read_query",
            args: { sql: "SELECT amount_typo FROM d_sales" },
          },
        ],
      }),
      result: message({
        channel: "tool_result",
        role: "tool",
        parts: [
          {
            type: "tool_result",
            call_id: "call-1",
            ok: false,
            content:
              'Binder Error: Referenced column "amount_typo" not found in FROM clause!\n' +
              'Candidate bindings: "amount"\n\n' +
              "LINE 1: SELECT amount_typo FROM d_sales\n" +
              "                       ^",
            latency_ms: 42,
          },
        ],
      }),
    };

    const html = renderToStaticMarkup(<TraceDetailDrawer entry={entry} onClose={() => undefined} />);

    expect(html).toMatch(
      /<header>Reading query<span[^>]*>Failed<\/span><span[^>]*aria-label="Execution time: 42ms"[^>]*>42ms<\/span><\/header>/,
    );
    expect(html).toContain("Query");
    expect(html).toContain("SELECT\n  amount_typo\nFROM\n  d_sales");
    expect(html).toContain('data-copy-text="SELECT amount_typo FROM d_sales"');
    expect(html).toContain("Response");
    expect(html).toContain("Referenced column &quot;amount_typo&quot; not found in FROM clause!");
    expect(html).not.toContain("Binder Error");
    expect(html).not.toContain("Candidate bindings");
    expect(html).not.toContain("LINE 1");
    expect(html).not.toContain("HTTP 400");
    expect(html).not.toContain("0 row");
    expect(html.match(/aria-label="Copy code"/g)).toHaveLength(1);
  });

  it("always shows an explicit response block when the query returns zero rows", () => {
    const entry: TraceEntry = {
      kind: "combo",
      call: message({
        channel: "tool_call",
        parts: [
          {
            type: "tool_call",
            call_id: "call-2",
            name: "mcp__knowledge_flow__read_query",
            args: { sql: "SELECT * FROM d_sales WHERE 1 = 0" },
          },
        ],
      }),
      result: message({
        channel: "tool_result",
        role: "tool",
        parts: [
          {
            type: "tool_result",
            call_id: "call-2",
            ok: true,
            content: JSON.stringify({
              sql_query: "SELECT * FROM d_sales WHERE 1 = 0",
              rows: [],
              error: null,
            }),
            latency_ms: 12,
          },
        ],
      }),
    };

    const html = renderToStaticMarkup(<TraceDetailDrawer entry={entry} onClose={() => undefined} />);

    expect(html).toContain("Query");
    expect(html).toContain("SELECT\n  *\nFROM\n  d_sales\nWHERE\n  1 = 0");
    expect(html).toContain('data-copy-text="SELECT * FROM d_sales WHERE 1 = 0"');
    expect(html).toContain("Response");
    expect(html).toMatch(
      /<header>Reading query<span[^>]*>Success<\/span><span[^>]*aria-label="Execution time: 12ms"[^>]*>12ms<\/span><\/header>/,
    );
    expect(html).toContain("0 rows");
    expect(html).toContain('<pre data-language="json">[]</pre>');
    expect(html.match(/aria-label="Copy code"/g)).toHaveLength(2);
  });
});
