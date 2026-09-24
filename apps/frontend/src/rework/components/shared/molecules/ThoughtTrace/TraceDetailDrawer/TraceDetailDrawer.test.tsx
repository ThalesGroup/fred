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
    t: (key: string, options?: { count?: number; duration?: string; name?: string; number?: number }) => {
      if (key === "rework.chatTrace.sqlQuery") return "Query";
      if (key === "rework.chatTrace.sqlResponse") return "Response";
      if (key === "rework.chatTrace.tabular.keyword") return "Search term:";
      if (key === "rework.chatTrace.tabular.catalogForDocument")
        return `Reading the summary of document “${options?.name}”.`;
      if (key === "rework.chatTrace.tabular.catalogForWorkbook") return "Reading the workbook summary.";
      if (key === "rework.chatTrace.rows") return `${options?.count ?? 0} rows`;
      if (key === "rework.chatTrace.tables")
        return `${options?.count ?? 0} ${options?.count === 1 ? "table" : "tables"}`;
      if (key === "rework.chatTrace.tabular.tableNumber") return `Table ${options?.number ?? 0}`;
      if (key === "rework.chatTrace.toolLabels.readQuery") return "Reading query";
      if (key === "rework.chatTrace.toolLabels.documents") return "Listing tabular documents";
      if (key === "rework.chatTrace.toolLabels.markdown") return "Reading the workbook catalog";
      if (key === "rework.chatTrace.toolLabels.schemas") return "Reading tabular schemas";
      if (key === "rework.chatTrace.toolLabels.search") return "Searching tabular values";
      if (key === "rework.chatTrace.toolStatus.failure") return "Failed";
      if (key === "rework.chatTrace.toolStatus.success") return "Success";
      if (key === "rework.chatTrace.executionTime") return `Execution time: ${options?.duration ?? ""}`;
      return key;
    },
  }),
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

vi.mock("../../MarkdownRenderer/MarkdownRenderer", () => ({
  MarkdownRenderer: ({ text }: { text: string }) => <article>{text}</article>,
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

function tabularEntry(
  name: string,
  content: unknown,
  ok = true,
  callId = "tabular-1",
): Extract<TraceEntry, { kind: "combo" }> {
  return {
    kind: "combo",
    call: message({
      channel: "tool_call",
      parts: [{ type: "tool_call", call_id: callId, name, args: {} }],
    }),
    result: message({
      channel: "tool_result",
      role: "tool",
      parts: [{ type: "tool_result", call_id: callId, ok, content: JSON.stringify(content), latency_ms: 18 }],
    }),
  };
}

describe("TraceDetailDrawer tabular tools", () => {
  it("groups CSV and workbook tables under readable document names", () => {
    const entry = tabularEntry("mcp__knowledge_flow__list_tabular_documents", [
      {
        document_uid: "uid-csv",
        document_name: "Sales.csv",
        kind: "csv",
        tables: [{ query_alias: "d_secret_csv", row_count: 12 }],
      },
      {
        document_uid: "uid-book",
        document_name: "Budget.xlsx",
        kind: "spreadsheet",
        tables: [
          { query_alias: "d_secret_q1", sheet: "Q1", title: "Revenue", row_count: 24 },
          { query_alias: "d_secret_q1_second", sheet: "Q1", title: "Q1", row_count: 7 },
          { query_alias: "d_secret_q1_margin", sheet: "Q1", title: "Margin", row_count: 10 },
          { query_alias: "d_secret_q2", sheet: "Q2", title: "Costs", row_count: 8 },
          { query_alias: "d_secret_history", sheet: "History", row_count: 12 },
        ],
      },
    ]);
    const html = renderToStaticMarkup(<TraceDetailDrawer entry={entry} onClose={() => undefined} />);
    expect(html).toContain("Listing tabular documents");
    expect(html).toContain("Sales.csv");
    expect(html).toContain("Budget.xlsx");
    expect(html).toContain("Revenue");
    expect(html).toContain("Margin");
    expect(html).toContain("Costs");
    expect(html).toContain("Table 2");
    expect(html).toContain("Table 1");
    expect(html.match(/<strong>Q1<\/strong>/g)).toHaveLength(1);
    expect(html.match(/<strong>Q2<\/strong>/g)).toHaveLength(1);
    expect(html.match(/History/g)).toHaveLength(1);
    expect(html).not.toContain("<details");
    expect(html).not.toContain("d_secret");
    expect(html).not.toContain("uid-csv");
  });

  it("shows every sheet and table in a workbook without an expand action", () => {
    const entry = tabularEntry("list_tabular_documents", [
      {
        document_uid: "uid-book",
        document_name: "Budget.xlsx",
        kind: "spreadsheet",
        tables: Array.from({ length: 12 }, (_, index) => ({
          query_alias: `d_secret_${index}`,
          sheet: `Sheet ${index + 1}`,
          row_count: index + 1,
        })),
      },
    ]);
    const html = renderToStaticMarkup(<TraceDetailDrawer entry={entry} onClose={() => undefined} />);
    expect(html).toContain("Sheet 12");
    expect(html).toContain("12 rows");
    expect(html).not.toContain("rework.chatTrace.tabular.showMore");
  });

  it("shows a compact MCP list without technical identifiers or CSV table details", () => {
    const entry = tabularEntry("list_tabular_documents", [
      { document_uid: "csv-uid", document_name: "Sales.csv" },
      {
        document_uid: "excel-uid",
        document_name: "Budget.xlsx",
        tables: [{ query_alias: "private-q1", sheet: "Q1", title: "Revenue" }],
      },
    ]);
    const html = renderToStaticMarkup(<TraceDetailDrawer entry={entry} onClose={() => undefined} />);
    expect(html).toContain("Sales.csv");
    expect(html).toContain("Budget.xlsx");
    expect(html).toContain("Q1");
    expect(html).toContain("Revenue");
    expect(html).not.toContain("csv-uid");
    expect(html).not.toContain("excel-uid");
    expect(html).not.toContain("private-q1");
    expect(html).not.toContain("0 rows");
  });

  it("renders a bounded catalog preview and an explicit full-catalog action", () => {
    const content = `# Workbook\n${"a".repeat(13000)}\nTAIL`;
    const entry = tabularEntry("get_tabular_document_markdown", { document_uid: "uid-book", content });
    const list = tabularEntry(
      "list_tabular_documents",
      [{ document_uid: "uid-book", document_name: "Budget.xlsx", kind: "spreadsheet", tables: [] }],
      true,
      "list-1",
    );
    const laterList = tabularEntry(
      "list_tabular_documents",
      [{ document_uid: "uid-book", document_name: "Renamed.xlsx", kind: "spreadsheet", tables: [] }],
      true,
      "list-2",
    );
    const html = renderToStaticMarkup(
      <TraceDetailDrawer
        entry={entry}
        messages={[list.call, list.result!, entry.call, entry.result!, laterList.call, laterList.result!]}
        onClose={() => undefined}
      />,
    );
    expect(html).toContain("Reading the workbook catalog");
    expect(html).toContain("Reading the summary of document “Budget.xlsx”.");
    expect(html).not.toContain("Renamed.xlsx");
    expect(html).toContain("Workbook");
    expect(html).toContain("rework.chatTrace.tabular.catalogPreview");
    expect(html).toContain("rework.chatTrace.tabular.showFullCatalog");
    expect(html).not.toContain("TAIL");
    expect(html).not.toContain("uid-book");

    const withoutDocumentName = renderToStaticMarkup(<TraceDetailDrawer entry={entry} onClose={() => undefined} />);
    expect(withoutDocumentName).toContain("Reading the workbook summary.");
  });

  it("shows table columns and sample values without leaking aliases", () => {
    const entry = tabularEntry("get_tabular_documents_schemas", [
      {
        document_uid: "uid-book",
        document_name: "Budget.xlsx",
        kind: "spreadsheet",
        tables: [
          {
            query_alias: "d_secret_q1",
            sheet: "Q1",
            title: "Revenue",
            columns: [{ name: "amount", dtype: "DOUBLE", sample_values: ["10", "20"] }],
          },
          { query_alias: "d_secret_q2", sheet: "Q2", title: "Costs", columns: [] },
        ],
      },
    ]);
    const html = renderToStaticMarkup(<TraceDetailDrawer entry={entry} onClose={() => undefined} />);
    expect(html).toContain("Reading tabular schemas");
    expect(html).toContain("Revenue");
    expect(html).toContain("Costs");
    expect(html).toContain("amount");
    expect(html).toContain("DOUBLE");
    expect(html).toContain("10, 20");
    expect(html).not.toContain("d_secret");
  });

  it("shows search matches and both partial-result warnings", () => {
    const entry = tabularEntry("search_tabular_values", {
      keyword: "Acme",
      normalized_keyword: "acme",
      matches: [
        {
          document_uid: "uid-book",
          document_name: "Budget.xlsx",
          query_alias: "d_secret_q1",
          sheet: "Q1",
          title: "Revenue",
          matched_columns: ["customer"],
          rows: [{ customer: "Acme" }],
          row_truncated: true,
        },
      ],
      tables_truncated: true,
      searched_dataset_uids: ["uid-book"],
    });
    const html = renderToStaticMarkup(<TraceDetailDrawer entry={entry} onClose={() => undefined} />);
    expect(html).toContain("Searching tabular values");
    expect(html).toContain("Search term: <strong>Acme</strong>");
    expect(html).toContain("Response");
    expect(html.match(/data-language="json"/g)).toHaveLength(1);
    expect(html).toContain("Budget.xlsx");
    expect(html).toContain("Revenue");
    expect(html).toContain("customer");
    expect(html).toContain("rework.chatTrace.tabular.tablesTruncated");
    expect(html).toContain("rework.chatTrace.tabular.rowsTruncated");
    expect(html).not.toContain("d_secret_q1");
  });

  it("bounds search row previews by row, column and cell size", () => {
    const row = Object.fromEntries(Array.from({ length: 9 }, (_, index) => [`column_${index}`, "x".repeat(300)]));
    const entry = tabularEntry("search_tabular_values", {
      keyword: "x",
      normalized_keyword: "x",
      matches: [
        {
          document_uid: "uid-book",
          document_name: "Budget.xlsx",
          query_alias: "d_secret_q1",
          matched_columns: ["column_0"],
          rows: Array.from({ length: 6 }, () => row),
          row_truncated: false,
        },
      ],
      tables_truncated: false,
      searched_dataset_uids: ["uid-book"],
    });
    const html = renderToStaticMarkup(<TraceDetailDrawer entry={entry} onClose={() => undefined} />);
    expect(html).toContain("rework.chatTrace.tabular.rowsPreview");
    expect(html).toContain("rework.chatTrace.tabular.fieldsPreview");
    expect(html).not.toContain("column_8");
    expect(html).not.toContain("x".repeat(300));
  });

  it("shows accurate empty states and keeps failed or malformed responses redacted", () => {
    const emptyList = renderToStaticMarkup(
      <TraceDetailDrawer entry={tabularEntry("list_tabular_documents", [])} onClose={() => undefined} />,
    );
    expect(emptyList).toContain("rework.chatTrace.tabular.noDocuments");
    const emptySchemas = renderToStaticMarkup(
      <TraceDetailDrawer entry={tabularEntry("get_tabular_documents_schemas", [])} onClose={() => undefined} />,
    );
    expect(emptySchemas).toContain("rework.chatTrace.tabular.noSchemas");
    const emptySearch = renderToStaticMarkup(
      <TraceDetailDrawer
        entry={tabularEntry("search_tabular_values", {
          keyword: "none",
          normalized_keyword: "none",
          matches: [],
          tables_truncated: false,
          searched_dataset_uids: [],
        })}
        onClose={() => undefined}
      />,
    );
    expect(emptySearch).toContain("rework.chatTrace.tabular.noMatches");

    const opaque = { sql_query: "SELECT secret", rows: [{ secret: "private" }] };
    for (const entry of [
      tabularEntry("list_tabular_documents", opaque),
      tabularEntry("list_tabular_documents", opaque, false),
    ]) {
      const html = renderToStaticMarkup(<TraceDetailDrawer entry={entry} onClose={() => undefined} />);
      expect(html).not.toContain("private");
      expect(html).not.toContain("SELECT secret");
      expect(html).toContain("action");
    }
    const failed = renderToStaticMarkup(
      <TraceDetailDrawer entry={tabularEntry("list_tabular_documents", opaque, false)} onClose={() => undefined} />,
    );
    expect(failed).toContain("Failed");
  });
});
