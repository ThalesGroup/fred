import { describe, expect, it } from "vitest";
import { parseTabularTraceResult, tabularToolKind } from "./tabularTrace";

const table = { query_alias: "d_private_alias", sheet: "Q1", title: "Sales", row_count: 42 };
const document = {
  document_uid: "private-uid",
  document_name: "Sales.xlsx",
  kind: "spreadsheet",
  tables: [table],
};

describe("tabular trace result validation", () => {
  it("recognizes bare and Knowledge Flow MCP tool names only", () => {
    expect(tabularToolKind("list_tabular_documents")).toBe("documents");
    expect(tabularToolKind("mcp__knowledge_flow__get_tabular_documents_schemas_2")).toBe("schemas");
    expect(tabularToolKind("mcp__other__list_tabular_documents")).toBeNull();
  });

  it("accepts document and schema arrays, including an empty array", () => {
    expect(parseTabularTraceResult("list_tabular_documents", JSON.stringify([document]))).toEqual({
      kind: "documents",
      documents: [document],
    });
    expect(parseTabularTraceResult("list_tabular_documents", "[]")).toEqual({ kind: "documents", documents: [] });
    expect(
      parseTabularTraceResult(
        "list_tabular_documents",
        JSON.stringify([
          { document_uid: "csv-uid", document_name: "Sales.csv" },
          {
            document_uid: "private-uid",
            document_name: "Sales.xlsx",
            tables: [{ query_alias: "d_private_alias", sheet: "Q1", title: "Sales" }],
          },
        ]),
      ),
    ).toEqual({
      kind: "documents",
      documents: [
        { document_uid: "csv-uid", document_name: "Sales.csv", kind: "csv", tables: [] },
        {
          document_uid: "private-uid",
          document_name: "Sales.xlsx",
          kind: "spreadsheet",
          tables: [{ query_alias: "d_private_alias", sheet: "Q1", title: "Sales" }],
        },
      ],
    });
    const schema = {
      ...document,
      tables: [{ ...table, columns: [{ name: "amount", dtype: "int64", sample_values: null }] }],
    };
    expect(parseTabularTraceResult("get_tabular_documents_schemas", JSON.stringify([schema]))).toEqual({
      kind: "schemas",
      documents: [schema],
    });
  });

  it("accepts a workbook catalog and a partial value search", () => {
    expect(
      parseTabularTraceResult(
        "get_tabular_document_markdown",
        JSON.stringify({ document_uid: "private-uid", content: "# Sales\nQ1" }),
      ),
    ).toEqual({ kind: "markdown", documentUid: "private-uid", content: "# Sales\nQ1" });

    const match = {
      document_uid: "private-uid",
      document_name: "Sales.xlsx",
      query_alias: "d_private_alias",
      sheet: "Q1",
      title: "Sales",
      matched_columns: ["customer"],
      rows: [{ customer: "Acme" }],
      row_truncated: true,
    };
    expect(
      parseTabularTraceResult(
        "mcp__knowledge_flow__search_tabular_values",
        JSON.stringify({
          keyword: "Acme",
          normalized_keyword: "acme",
          matches: [match],
          tables_truncated: true,
          searched_dataset_uids: ["private-uid"],
        }),
      ),
    ).toEqual({ kind: "search", keyword: "Acme", matches: [match], tablesTruncated: true });
  });

  it("rejects malformed and unrelated content instead of exposing its fields", () => {
    expect(parseTabularTraceResult("mcp__other__list_tabular_documents", JSON.stringify([document]))).toBeNull();
    expect(
      parseTabularTraceResult("list_tabular_documents", JSON.stringify([{ ...document, tables: ["bad"] }])),
    ).toBeNull();
    expect(
      parseTabularTraceResult(
        "list_tabular_documents",
        JSON.stringify([{ document_uid: "x", document_name: "x", tables: null }]),
      ),
    ).toBeNull();
    expect(parseTabularTraceResult("get_tabular_documents_schemas", JSON.stringify([document]))).toBeNull();
    expect(
      parseTabularTraceResult(
        "search_tabular_values",
        JSON.stringify({ keyword: "x", normalized_keyword: "x", matches: [], tables_truncated: "no" }),
      ),
    ).toBeNull();
    expect(parseTabularTraceResult("get_tabular_document_markdown", "not JSON")).toBeNull();
  });
});
