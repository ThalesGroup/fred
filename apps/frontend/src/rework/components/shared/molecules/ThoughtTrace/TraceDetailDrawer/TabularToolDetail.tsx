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

import { useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Icon from "@shared/atoms/Icon/Icon";
import type { TabularDocument, TabularTable, TabularTraceResult } from "../../../../../utils/tabularTrace";
import { CodeBlock } from "../../CodeBlock/CodeBlock";
import { MarkdownRenderer } from "../../MarkdownRenderer/MarkdownRenderer";
import styles from "./TraceDetailDrawer.module.css";
import tabularStyles from "./TabularToolDetail.module.css";

const PAGE_SIZE = 10;
const CATALOG_PAGE_LINES = 20;
const ROW_PREVIEW_COUNT = 5;
const COLUMN_PREVIEW_COUNT = 8;
const CELL_PREVIEW_CHARS = 160;
const COLUMN_NAME_PREVIEW_CHARS = 80;

function clipped(text: string, limit: number): string {
  return text.length > limit ? `${text.slice(0, limit)}…` : text;
}

function previewRows(rows: Record<string, unknown>[]): { rows: Record<string, unknown>[]; fieldsTruncated: boolean } {
  let fieldsTruncated = false;
  const preview = rows.slice(0, ROW_PREVIEW_COUNT).map((row) => {
    const fields = Object.entries(row);
    if (fields.length > COLUMN_PREVIEW_COUNT) fieldsTruncated = true;
    return Object.fromEntries(
      fields.slice(0, COLUMN_PREVIEW_COUNT).map(([name, value]) => {
        if (name.length > COLUMN_NAME_PREVIEW_CHARS) fieldsTruncated = true;
        const serialized = typeof value === "string" ? value : (JSON.stringify(value) ?? "");
        if (serialized.length > CELL_PREVIEW_CHARS) fieldsTruncated = true;
        return [
          clipped(name, COLUMN_NAME_PREVIEW_CHARS),
          serialized.length > CELL_PREVIEW_CHARS ? clipped(serialized, CELL_PREVIEW_CHARS) : value,
        ];
      }),
    );
  });
  return { rows: preview, fieldsTruncated };
}

function PagedItems<T>({ items, renderItem }: { items: T[]; renderItem: (item: T, index: number) => ReactNode }) {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(PAGE_SIZE);
  return (
    <>
      {items.slice(0, visible).map(renderItem)}
      {visible < items.length && (
        <Button
          className={tabularStyles.showMore}
          color="primary"
          variant="text"
          size="2xs"
          type="button"
          onClick={() => setVisible((count) => count + PAGE_SIZE)}
        >
          {t("rework.chatTrace.tabular.showMore", { count: Math.min(PAGE_SIZE, items.length - visible) })}
        </Button>
      )}
    </>
  );
}

function tableName(table: TabularTable, unnamed: string): string {
  return table.title || table.sheet || unnamed;
}

function TableHeading({ table, index }: { table: TabularTable; index: number }) {
  const { t } = useTranslation();
  return (
    <div className={tabularStyles.tabularHeading}>
      <strong>{tableName(table, t("rework.chatTrace.tabular.tableNumber", { number: index + 1 }))}</strong>
      {table.title && table.sheet && table.title !== table.sheet && (
        <span className={styles.metaInfo}>{table.sheet}</span>
      )}
      {table.row_count != null && (
        <span className={styles.metaInfo}>{t("rework.chatTrace.rows", { count: table.row_count })}</span>
      )}
    </div>
  );
}

function DocumentTables({ document }: { document: TabularDocument }) {
  const { t } = useTranslation();
  const groups = new Map<string | null, TabularTable[]>();

  document.tables.forEach((table) => {
    const sheet = document.kind === "spreadsheet" ? table.sheet || null : null;
    const group = groups.get(sheet) ?? [];
    group.push(table);
    groups.set(sheet, group);
  });
  const sheetGroups = [...groups].filter((group): group is [string, TabularTable[]] => group[0] !== null);
  const ungroupedTables = groups.get(null) ?? [];

  const tableRow = (table: TabularTable, index: number, sheet: string | null) => (
    <li className={tabularStyles.treeTable} key={table.query_alias}>
      <span className={tabularStyles.treeTableName}>
        {table.title && table.title !== sheet
          ? table.title
          : t("rework.chatTrace.tabular.tableNumber", { number: index + 1 })}
      </span>
      {table.row_count != null && (
        <span className={tabularStyles.treeCount}>{t("rework.chatTrace.rows", { count: table.row_count })}</span>
      )}
    </li>
  );

  return (
    <ul className={tabularStyles.documentTree}>
      {sheetGroups.map(([sheet, tables]) => (
        <li key={sheet}>
          <div className={tabularStyles.treeSheetName}>
            <span className={tabularStyles.sheetIcon}>
              <Icon category="outlined" type="table_chart" />
            </span>
            <strong>{sheet}</strong>
            {tables.length === 1 && (
              <>
                <span className={tabularStyles.treeSingleTable}>
                  {tables[0].title && tables[0].title !== sheet
                    ? tables[0].title
                    : t("rework.chatTrace.tabular.tableNumber", { number: 1 })}
                </span>
                {tables[0].row_count != null && (
                  <span className={tabularStyles.treeCount}>
                    {t("rework.chatTrace.rows", { count: tables[0].row_count })}
                  </span>
                )}
              </>
            )}
          </div>
          {tables.length > 1 && (
            <ul className={tabularStyles.treeTables}>{tables.map((table, index) => tableRow(table, index, sheet))}</ul>
          )}
        </li>
      ))}
      {ungroupedTables.map((table, index) => tableRow(table, index, null))}
    </ul>
  );
}

function DocumentsDetail({ data }: { data: Extract<TabularTraceResult, { kind: "documents" }> }) {
  const { t } = useTranslation();
  return (
    <div className={styles.detail}>
      {data.documents.length === 0 ? (
        <p className={styles.metaInfo}>{t("rework.chatTrace.tabular.noDocuments")}</p>
      ) : (
        <>
          <p className={styles.detailTitle}>
            {t("rework.chatTrace.tabular.identifiedDocuments", { count: data.documents.length })}
          </p>
          {data.documents.map((document) => (
            <section className={tabularStyles.documentCard} key={document.document_uid}>
              <h3 className={tabularStyles.documentName}>{document.document_name}</h3>
              {document.kind === "spreadsheet" && document.tables.length === 0 && (
                <p className={styles.metaInfo}>{t("rework.chatTrace.tabular.noTables")}</p>
              )}
              {document.kind === "spreadsheet" && document.tables.length > 0 && <DocumentTables document={document} />}
            </section>
          ))}
        </>
      )}
    </div>
  );
}

function CatalogContent({ content: fullContent, documentName }: { content: string; documentName?: string | null }) {
  const { t } = useTranslation();
  const [showAll, setShowAll] = useState(false);
  const lines = useMemo(() => {
    const result = fullContent.split(/\r?\n/);
    if (result[result.length - 1] === "") result.pop();
    return result;
  }, [fullContent]);
  const canCollapse = lines.length > CATALOG_PAGE_LINES;
  const content = (showAll ? lines : lines.slice(0, CATALOG_PAGE_LINES)).join("\n");
  return (
    <>
      <p className={styles.detailTitle}>
        {documentName
          ? t("rework.chatTrace.tabular.catalogForDocument", { name: documentName })
          : t("rework.chatTrace.tabular.catalogForWorkbook")}
      </p>
      {content.trim() ? (
        <div className={tabularStyles.catalogMarkdown}>
          <MarkdownRenderer text={content} fullWidth compact />
        </div>
      ) : (
        <p className={styles.metaInfo}>{t("rework.chatTrace.tabular.emptyCatalog")}</p>
      )}
      {canCollapse && (
        <div className={tabularStyles.tabularPreviewNotice}>
          <span>
            {t(showAll ? "rework.chatTrace.tabular.catalogComplete" : "rework.chatTrace.tabular.catalogPreview", {
              shown: showAll ? lines.length : CATALOG_PAGE_LINES,
              total: lines.length,
            })}
          </span>
          <Button
            className={tabularStyles.showMore}
            color="primary"
            variant="text"
            size="2xs"
            type="button"
            onClick={() => setShowAll((current) => !current)}
          >
            {t(showAll ? "rework.chatTrace.tabular.showCatalogPreview" : "rework.chatTrace.tabular.showFullCatalog")}
          </Button>
        </div>
      )}
    </>
  );
}

function MarkdownDetail({
  data,
  documentName,
}: {
  data: Extract<TabularTraceResult, { kind: "markdown" }>;
  documentName?: string | null;
}) {
  return (
    <div className={styles.detail}>
      <CatalogContent content={data.content} documentName={documentName} />
    </div>
  );
}

function SchemasDetail({ data }: { data: Extract<TabularTraceResult, { kind: "schemas" | "descriptions" }> }) {
  const { t } = useTranslation();
  return (
    <div className={styles.detail}>
      {data.documents.length === 0 ? (
        <p className={styles.metaInfo}>{t("rework.chatTrace.tabular.noSchemas")}</p>
      ) : (
        <PagedItems
          items={data.documents}
          renderItem={(document) => (
            <section
              className={`${tabularStyles.documentCard} ${tabularStyles.schemaDocument}`}
              key={document.document_uid}
            >
              <div className={tabularStyles.tabularHeading}>
                <h3 className={tabularStyles.documentName}>{document.document_name}</h3>
                <span className={styles.metaInfo}>{t(`rework.chatTrace.tabular.kind.${document.kind}`)}</span>
              </div>
              <div className={tabularStyles.schemaDocumentContent}>
                {"markdown" in document && typeof document.markdown === "string" && (
                  <div className={tabularStyles.catalogSection}>
                    <CatalogContent content={document.markdown} documentName={document.document_name} />
                  </div>
                )}
                {document.tables.length === 0 ? (
                  <p className={styles.metaInfo}>{t("rework.chatTrace.tabular.noTables")}</p>
                ) : (
                  <div className={tabularStyles.schemaTables}>
                    <h4 className={tabularStyles.schemaTablesTitle}>
                      {t("rework.chatTrace.tabular.tablesHeading", { count: document.tables.length })}
                    </h4>
                    <PagedItems
                      items={document.tables}
                      renderItem={(table, tableIndex) => (
                        <section className={tabularStyles.tabularTable} key={table.query_alias}>
                          <TableHeading table={table} index={tableIndex} />
                          {table.columns.length === 0 ? (
                            <p className={styles.metaInfo}>{t("rework.chatTrace.tabular.noColumns")}</p>
                          ) : (
                            <div className={tabularStyles.tabularNested}>
                              <PagedItems
                                items={table.columns}
                                renderItem={(column, columnIndex) => {
                                  const label = column.is_categorical
                                    ? t("rework.chatTrace.tabular.categorical")
                                    : column.dtype;
                                  const isNumeric = column.dtype === "integer" || column.dtype === "float";
                                  const hasValues = !isNumeric && Boolean(column.sample_values?.length);
                                  const summary = (
                                    <>
                                      <span>{column.name}</span>
                                      <code>{label}</code>
                                    </>
                                  );
                                  return (
                                    <div className={tabularStyles.tabularColumn} key={`${column.name}-${columnIndex}`}>
                                      {hasValues || isNumeric ? (
                                        <details className={tabularStyles.columnDisclosure}>
                                          <summary className={tabularStyles.columnSummary}>{summary}</summary>
                                          <code className={tabularStyles.columnDetails}>
                                            {hasValues
                                              ? column.sample_values?.join(" / ")
                                              : `min ${column.min_value ?? "—"} · max ${column.max_value ?? "—"}`}
                                          </code>
                                        </details>
                                      ) : (
                                        <div className={tabularStyles.columnSummary}>{summary}</div>
                                      )}
                                    </div>
                                  );
                                }}
                              />
                            </div>
                          )}
                        </section>
                      )}
                    />
                  </div>
                )}
              </div>
            </section>
          )}
        />
      )}
    </div>
  );
}

function SearchDetail({ data }: { data: Extract<TabularTraceResult, { kind: "search" }> }) {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(PAGE_SIZE);
  const matches = data.matches.slice(0, visible);
  let fieldsTruncated = false;
  const response = matches.map((match, index) => {
    const preview = previewRows(match.rows);
    fieldsTruncated ||= preview.fieldsTruncated;
    return {
      document: match.document_name,
      table: tableName(match, t("rework.chatTrace.tabular.tableNumber", { number: index + 1 })),
      matched_columns: match.matched_columns
        .slice(0, COLUMN_PREVIEW_COUNT)
        .map((column) => clipped(column, COLUMN_NAME_PREVIEW_CHARS)),
      rows: preview.rows,
    };
  });
  return (
    <div className={styles.detail}>
      <div className={styles.toolSection}>
        <p className={styles.sectionLabel}>
          {t("rework.chatTrace.tabular.keyword")} <strong>{data.keyword}</strong>
        </p>
      </div>
      <div className={styles.toolSection}>
        <p className={styles.sectionLabel}>{t("rework.chatTrace.sqlResponse")}</p>
        <CodeBlock code={JSON.stringify(response, null, 2)} language="json" />
        {data.matches.length === 0 && <p className={styles.metaInfo}>{t("rework.chatTrace.tabular.noMatches")}</p>}
        {visible < data.matches.length && (
          <Button
            className={tabularStyles.showMore}
            color="primary"
            variant="text"
            size="2xs"
            type="button"
            onClick={() => setVisible((count) => count + PAGE_SIZE)}
          >
            {t("rework.chatTrace.tabular.showMore", { count: Math.min(PAGE_SIZE, data.matches.length - visible) })}
          </Button>
        )}
        {matches.some((match) => match.row_truncated) && (
          <p className={tabularStyles.tabularWarning}>{t("rework.chatTrace.tabular.rowsTruncated")}</p>
        )}
        {matches.some((match) => match.rows.length > ROW_PREVIEW_COUNT) && (
          <p className={styles.metaInfo}>{t("rework.chatTrace.tabular.rowsPreview", { count: ROW_PREVIEW_COUNT })}</p>
        )}
        {(fieldsTruncated || matches.some((match) => match.matched_columns.length > COLUMN_PREVIEW_COUNT)) && (
          <p className={styles.metaInfo}>{t("rework.chatTrace.tabular.fieldsPreview")}</p>
        )}
        {data.tablesTruncated && (
          <p className={tabularStyles.tabularWarning}>{t("rework.chatTrace.tabular.tablesTruncated")}</p>
        )}
      </div>
    </div>
  );
}

export function TabularToolDetail({ data, documentName }: { data: TabularTraceResult; documentName?: string | null }) {
  switch (data.kind) {
    case "documents":
      return <DocumentsDetail data={data} />;
    case "markdown":
      return <MarkdownDetail data={data} documentName={documentName} />;
    case "schemas":
    case "descriptions":
      return <SchemasDetail data={data} />;
    case "search":
      return <SearchDetail data={data} />;
  }
}
