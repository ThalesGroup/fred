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

import { useTranslation } from "react-i18next";
import type { ChatMessage } from "../../../../../../slices/runtime/runtimeOpenApi";
import { CodeBlock } from "../../CodeBlock/CodeBlock";
import { SourcesPanel } from "../../SourcesPanel/SourcesPanel";
import { InlineDrawer } from "../../InlineDrawer/InlineDrawer";
import { HitlChoiceRecap } from "../../HitlAnswerSummary/HitlChoiceRecap";
import { hitlAnswerSummaryForTool } from "@rework/utils/hitlAnswerSummary";
import { MarkdownRenderer } from "../../MarkdownRenderer/MarkdownRenderer";
import type { RagSearchResult, SqlQueryResult, TraceEntry } from "../../../../../utils/traceUtils";
import {
  PHASE_LABELS,
  asRagSearchResult,
  asSqlQueryResult,
  detailTextForEntry,
  entryLabel,
  formatLatencyMs,
  findTabularDocumentName,
  genericToolPayload,
  inactiveHitlStatus,
  isDocumentTreeTool,
  isSummarizeDocumentTool,
  parseToolResultContent,
  phaseKeyForEntry,
  sourceForEntry,
  statusForEntry,
  thoughtExtras,
  toolArgs,
  toolCallId,
  toolName,
  toolResultContent,
  toolResultLatencyMs,
  toolResultOk,
} from "../../../../../utils/traceUtils";
import { parseTabularTraceResult, tabularToolKind } from "../../../../../utils/tabularTrace";
import { parseWebResearchResult, webResearchTarget, webResearchToolKind } from "../../../../../utils/webResearchTrace";
import phaseStyles from "../phaseBadge.module.css";
import { formatSqlForDisplay } from "./formatSqlForDisplay";
import { executionFailureText, toolFailureDetail, type ToolFailureDetail } from "../../../../../utils/toolFailureTrace";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { useCopyConfirmation } from "../../../../../core/hooks/useCopyConfirmation";
import { writeRichClipboard } from "../../../../../utils/clipboardUtils";
import { historicalDocumentTreeText, parseDocumentTreeTrace } from "../../../../../utils/documentTreeTrace";
import { DocumentTreeDetail } from "./DocumentTreeDetail";
import { TabularToolDetail } from "./TabularToolDetail";
import { WebResearchToolDetail } from "./WebResearchToolDetail";
import styles from "./TraceDetailDrawer.module.css";

interface TraceDetailDrawerProps {
  /** The entry to inspect, or null when the panel is closed. */
  entry: TraceEntry | null;
  messages?: ChatMessage[];
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
          <>
            {data.rows.length === 0 && <p>{t("rework.chatTrace.emptyQuerySuccess")}</p>}
            <CodeBlock code={JSON.stringify(data.rows.slice(0, 50), null, 2)} language="json" />
          </>
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

/** Fallback: redacted {action, status, latency} view for unrecognized tools. */
function GenericToolDetail({ entry }: { entry: Extract<TraceEntry, { kind: "combo" }> }) {
  const { t } = useTranslation();
  const payload = genericToolPayload(entry, (key) => t(key));
  return (
    <div className={styles.detail}>
      <CodeBlock code={JSON.stringify(payload, null, 2)} language="json" />
    </div>
  );
}

function FailedToolDetail({ detail }: { detail: ToolFailureDetail }) {
  const { t } = useTranslation();
  const { copied, confirmCopied } = useCopyConfirmation();
  const { sql, ...argumentsWithoutSql } = detail.arguments ?? {};
  const argumentsToDisplay = typeof sql === "string" ? argumentsWithoutSql : detail.arguments;
  return (
    <div className={styles.detail}>
      {typeof sql === "string" && (
        <div className={styles.toolSection}>
          <p className={styles.sectionLabel}>{t("rework.chatTrace.sqlQuery")}</p>
          <CodeBlock code={formatSqlForDisplay(sql)} copyText={sql} language="sql" />
        </div>
      )}
      {detail.arguments && (typeof sql !== "string" || Object.keys(argumentsWithoutSql).length > 0) && (
        <div className={styles.toolSection}>
          <p className={styles.sectionLabel}>{t("rework.chatTrace.failure.arguments")}</p>
          <CodeBlock code={JSON.stringify(argumentsToDisplay, null, 2)} language="json" />
        </div>
      )}
      <div className={styles.toolSection}>
        <p className={styles.sectionLabel}>{t("rework.chatTrace.failure.error")}</p>
        <div className={detail.declined ? styles.declinedBox : styles.errorBox}>
          {detail.error ?? t(detail.errorKey, detail.originKey ? { origin: t(detail.originKey) } : undefined)}
        </div>
        {detail.setting && (
          <p className={styles.failureMeta}>
            {t("rework.chatTrace.failure.setting")} <code className={styles.failureSetting}>{detail.setting}</code>{" "}
            {t("rework.chatTrace.failure.settingOwner")}
          </p>
        )}
        {detail.status !== null && (
          <p className={styles.failureMeta}>{t("rework.chatTrace.failure.httpStatus", { status: detail.status })}</p>
        )}
        {detail.reference && (
          <div className={styles.failureReference}>
            <span className={styles.failureMeta}>{t("rework.chatTrace.failure.reference")}</span>
            <code className={styles.failureReferenceValue}>{detail.reference}</code>
            <IconButton
              variant="icon"
              size="small"
              icon={{ category: "outlined", type: copied ? "check_circle" : "content_copy" }}
              aria-label={t(
                copied ? "rework.chatTrace.failure.referenceCopied" : "rework.chatTrace.failure.copyReference",
              )}
              onClick={() => {
                void writeRichClipboard("", detail.reference ?? "").then((ok) => {
                  if (ok) confirmCopied();
                });
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
}

/** Dispatches a tool-result entry to the richest view its content shape supports. */
function ToolDetail({ entry, messages }: { entry: Extract<TraceEntry, { kind: "combo" }>; messages?: ChatMessage[] }) {
  const failure = toolFailureDetail(entry);
  const webKind = webResearchToolKind(toolName(entry.call));
  const webResult = webKind && entry.result ? parseWebResearchResult(toolResultContent(entry.result)) : null;
  // A bare-named MCP `web_search` with another payload shape keeps the generic view.
  if (webKind && (webResult?.kind === "error" || (!failure && (webResult || !entry.result)))) {
    return (
      <WebResearchToolDetail
        kind={webKind}
        target={webResearchTarget(webKind, toolArgs(entry.call))}
        result={webResult}
      />
    );
  }
  if (failure) return <FailedToolDetail detail={failure} />;
  if (toolName(entry.call) === "ask_user") {
    const summary = messages ? hitlAnswerSummaryForTool(messages, entry.call) : null;
    if (summary) return <HitlChoiceRecap summary={summary} />;
  }
  if (tabularToolKind(toolName(entry.call))) {
    const tabular =
      entry.result && toolResultOk(entry.result)
        ? parseTabularTraceResult(toolName(entry.call), toolResultContent(entry.result))
        : null;
    return tabular ? (
      <TabularToolDetail
        key={toolCallId(entry.call)}
        data={tabular}
        documentName={
          tabular.kind === "markdown" && messages
            ? findTabularDocumentName(messages, tabular.documentUid, toolCallId(entry.call))
            : null
        }
      />
    ) : (
      <GenericToolDetail entry={entry} />
    );
  }
  const data = entry.result ? parseToolResultContent(entry.result) : null;
  const sqlResult = asSqlQueryResult(data);
  if (sqlResult) return <SqlToolDetail data={sqlResult} />;
  const ragResult = asRagSearchResult(data);
  if (ragResult) return <RagToolDetail data={ragResult} />;
  const name = toolName(entry.call);
  if (entry.result && isSummarizeDocumentTool(name)) {
    return <SummarizeDocumentDetail text={toolResultContent(entry.result)} />;
  }
  if (entry.result && isDocumentTreeTool(name) && toolResultOk(entry.result)) {
    const tree = parseDocumentTreeTrace(toolResultContent(entry.result));
    if (tree) return <DocumentTreeDetail key={toolCallId(entry.call)} data={tree} />;
    const historical = historicalDocumentTreeText(toolResultContent(entry.result));
    if (historical)
      return (
        <div className={styles.detail}>
          <CodeBlock code={historical} />
        </div>
      );
  }
  return <GenericToolDetail entry={entry} />;
}

/** Safe runtime explanation and support reference, preserved in history. */
function ErrorDetail({ entry }: { entry: TraceEntry }) {
  const { t } = useTranslation();
  const text = executionFailureText(detailTextForEntry(entry)) ?? t("rework.chatTrace.failure.unexpected");
  return (
    <div className={styles.detail}>
      <div className={styles.errorDetailBox}>{text}</div>
    </div>
  );
}

export function TraceDetailDrawer({ entry, messages, onClose }: TraceDetailDrawerProps) {
  const { t } = useTranslation();
  const label = entry ? entryLabel(entry, (key) => t(key)) : "";
  const isError = entry?.kind === "solo" && statusForEntry(entry) === "error";
  const toolStatus =
    entry?.kind === "combo"
      ? (inactiveHitlStatus(entry) ?? (!entry.result ? "running" : toolResultOk(entry.result) ? "success" : "failure"))
      : null;
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
      layout="overlay"
      width="720px"
    >
      {entry &&
        (isError ? (
          <ErrorDetail entry={entry} />
        ) : entry.kind === "combo" ? (
          <ToolDetail entry={entry} messages={messages} />
        ) : (
          <TextDetail entry={entry} />
        ))}
    </InlineDrawer>
  );
}
