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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { useToast, type ToastInput } from "@shared/molecules/Toast/ToastProvider";
import { writeRichClipboard } from "@rework/utils/clipboardUtils";
import { CodeBlock } from "../../CodeBlock/CodeBlock";
import { SourcesPanel } from "../../SourcesPanel/SourcesPanel";
import { InlineDrawer } from "../../InlineDrawer/InlineDrawer";
import { MarkdownRenderer } from "../../MarkdownRenderer/MarkdownRenderer";
import type { RagSearchResult, SqlQueryResult, TraceEntry } from "../../../../../utils/traceUtils";
import {
  PHASE_LABELS,
  asFailedSqlQueryResult,
  asRagSearchResult,
  asSqlQueryResult,
  detailTextForEntry,
  entryLabel,
  formatLatencyMs,
  genericToolPayload,
  isDocumentTreeTool,
  isSummarizeDocumentTool,
  parseToolResultContent,
  phaseKeyForEntry,
  sourceForEntry,
  statusForEntry,
  stripDocumentUids,
  thoughtExtras,
  toolCopyText,
  toolName,
  toolResultContent,
  toolResultLatencyMs,
  toolResultOk,
} from "../../../../../utils/traceUtils";
import phaseStyles from "../phaseBadge.module.css";
import { formatSqlForDisplay } from "./formatSqlForDisplay";
import styles from "./TraceDetailDrawer.module.css";

interface TraceDetailDrawerProps {
  /** The entry to inspect, or null when the panel is closed. */
  entry: TraceEntry | null;
  onClose: () => void;
}

/** Pretty, markdown-rendered view for reasoning / note text entries. */
function TextDetail({ entry }: { entry: TraceEntry }) {
  const extras = entry.kind === "solo" ? thoughtExtras(entry.message) : {};
  const phase = phaseKeyForEntry(entry);
  const source = sourceForEntry(entry);
  const title = extras.title ?? null;
  const conclusion = extras.conclusion ?? null;
  const durationMs = extras.duration_ms ?? null;
  const text = detailTextForEntry(entry);
  const isStreaming = statusForEntry(entry) === "streaming";

  return (
    <div className={styles.detail}>
      <div className={styles.meta}>
        {phase && (
          <span className={`${phaseStyles.phaseBadge} ${styles.phaseBadge}`} data-phase={phase}>
            {PHASE_LABELS[phase] ?? phase}
          </span>
        )}
        {source === "model_native" && <span className={styles.sourceChip}>Model</span>}
        {durationMs != null && <span className={styles.metaInfo}>{formatLatencyMs(durationMs)}</span>}
      </div>

      {title && <p className={styles.detailTitle}>{title}</p>}

      {/* Only reasoning steps carry text. Structural steps (auto-synthesised
          tool_use thoughts, etc.) have none — show no placeholder, just the
          header + conclusion. */}
      {text && (
        <div className={styles.markdown}>
          <MarkdownRenderer text={text} streaming={isStreaming} />
        </div>
      )}

      {conclusion && (
        <div className={styles.conclusion}>
          <span className={styles.conclusionLabel}>Conclusion</span>
          <span className={styles.conclusionText}>{conclusion}</span>
        </div>
      )}
    </div>
  );
}

/** Curated view for the tabular/SQL tool: the executed query plus a row preview. */
function SqlToolDetail({ data }: { data: SqlQueryResult }) {
  const { t } = useTranslation();
  const rowCount = t("rework.chatTrace.rows", { count: data.rows.length });
  const formattedQuery = formatSqlForDisplay(data.sql_query);

  return (
    <div className={styles.detail}>
      <div className={styles.toolSection}>
        <p className={styles.sectionLabel}>{t("rework.chatTrace.sqlQuery")}</p>
        <CodeBlock code={formattedQuery} copyText={data.sql_query} language="sql" />
      </div>
      <div className={styles.toolSection}>
        <div className={styles.sectionHeader}>
          <p className={styles.sectionLabel}>{t("rework.chatTrace.sqlResponse")}</p>
          {!data.error && <span className={styles.metaInfo}>{rowCount}</span>}
        </div>
        {data.error ? (
          <div className={styles.errorBox}>{data.error}</div>
        ) : (
          <CodeBlock code={JSON.stringify(data.rows.slice(0, 50), null, 2)} language="json" />
        )}
      </div>
    </div>
  );
}

/** Curated view for RAG/vector-search tools: the query plus retrieved sources. */
function RagToolDetail({ data }: { data: RagSearchResult }) {
  return (
    <div className={styles.detail}>
      <p className={styles.detailTitle}>{data.query}</p>
      <SourcesPanel sources={data.hits} />
    </div>
  );
}

/** Curated view for the on-demand document summarizer: the generated summary as prose. */
function SummarizeDocumentDetail({ text }: { text: string }) {
  return (
    <div className={styles.detail}>
      <div className={styles.markdown}>
        <MarkdownRenderer text={text} />
      </div>
    </div>
  );
}

/** Curated view for the document tree listing: indented tree text, with the
 *  bracketed internal document uids stripped (never shown to the end user). */
function DocumentTreeDetail({ text }: { text: string }) {
  return (
    <div className={styles.detail}>
      <CodeBlock code={stripDocumentUids(text)} />
    </div>
  );
}

/** Fallback: redacted {action, status, latency} view for unrecognized tools. */
function GenericToolDetail({ entry }: { entry: Extract<TraceEntry, { kind: "combo" }> }) {
  const payload = genericToolPayload(entry);
  return (
    <div className={styles.detail}>
      <CodeBlock code={JSON.stringify(payload, null, 2)} language="json" />
    </div>
  );
}

/** Dispatches a tool-result entry to the richest view its content shape supports. */
function ToolDetail({ entry }: { entry: Extract<TraceEntry, { kind: "combo" }> }) {
  const data = entry.result ? parseToolResultContent(entry.result) : null;
  const sqlResult = asSqlQueryResult(data);
  if (sqlResult) return <SqlToolDetail data={sqlResult} />;
  const failedSqlResult = asFailedSqlQueryResult(entry);
  if (failedSqlResult) return <SqlToolDetail data={failedSqlResult} />;
  const ragResult = asRagSearchResult(data);
  if (ragResult) return <RagToolDetail data={ragResult} />;
  const name = toolName(entry.call);
  if (entry.result && isSummarizeDocumentTool(name)) {
    return <SummarizeDocumentDetail text={toolResultContent(entry.result)} />;
  }
  if (entry.result && isDocumentTreeTool(name)) {
    return <DocumentTreeDetail text={toolResultContent(entry.result)} />;
  }
  return <GenericToolDetail entry={entry} />;
}

/** Detail view for a turn-crash error entry: the raw error message (the same
 *  text shown in the transient toast), in an error-styled block. */
function ErrorDetail({ entry }: { entry: TraceEntry }) {
  const text = detailTextForEntry(entry);
  return (
    <div className={styles.detail}>
      <div className={styles.errorDetailBox}>{text}</div>
    </div>
  );
}

/** Single copy affordance for the drawer header — copies the SQL query, the curated
 *  JSON payload, the raw error message, or nothing (RAG sources are browsed, not
 *  copied as text). `toast`, when set, confirms the copy with a success toast. */
function CopyHeaderAction({ text, toast }: { text: string; toast?: ToastInput }) {
  const [copied, setCopied] = useState(false);
  const { showSuccess } = useToast();

  const handleCopy = () => {
    writeRichClipboard("", text).then((ok) => {
      if (ok) {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
        if (toast) showSuccess(toast);
      }
    });
  };

  return (
    <IconButton
      variant="icon"
      size="small"
      icon={{ category: "outlined", type: copied ? "check_circle" : "content_copy" }}
      aria-label={copied ? "Copied" : "Copy"}
      onClick={handleCopy}
    />
  );
}

export function TraceDetailDrawer({ entry, onClose }: TraceDetailDrawerProps) {
  const { t } = useTranslation();
  const label = entry ? entryLabel(entry, (key) => t(key)) : "";
  const copyText = entry ? toolCopyText(entry) : null;
  const isError = entry?.kind === "solo" && statusForEntry(entry) === "error";
  const toolStatus =
    entry?.kind === "combo" ? (!entry.result ? "running" : toolResultOk(entry.result) ? "success" : "failure") : null;
  const toolLatency = entry?.kind === "combo" && entry.result ? formatLatencyMs(toolResultLatencyMs(entry.result)) : "";

  return (
    <InlineDrawer
      open={entry !== null}
      onClose={onClose}
      title={label}
      titleAccessory={
        toolStatus ? (
          <>
            <span className={styles.statusBadge} data-status={toolStatus}>
              {t(`rework.chatTrace.toolStatus.${toolStatus}`)}
            </span>
            {toolLatency && (
              <span
                className={styles.latencyBadge}
                aria-label={t("rework.chatTrace.executionTime", { duration: toolLatency })}
              >
                {toolLatency}
              </span>
            )}
          </>
        ) : undefined
      }
      headerActions={
        copyText ? (
          <CopyHeaderAction
            text={copyText}
            toast={isError ? { summary: t("rework.chatTrace.errorCopied") } : undefined}
            key={label}
          />
        ) : undefined
      }
      layout="overlay"
      width="720px"
    >
      {entry &&
        (isError ? (
          <ErrorDetail entry={entry} />
        ) : entry.kind === "combo" ? (
          <ToolDetail entry={entry} />
        ) : (
          <TextDetail entry={entry} />
        ))}
    </InlineDrawer>
  );
}
