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
  asFailedSqlQueryResult,
  asRagSearchResult,
  asSqlQueryResult,
  detailTextForEntry,
  entryLabel,
  formatLatencyMs,
  findTabularDocumentName,
  genericToolPayload,
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
  toolSlug,
} from "../../../../../utils/traceUtils";
import { parseTabularTraceResult, tabularToolKind } from "../../../../../utils/tabularTrace";
import { parseWebResearchResult, webResearchTarget, webResearchToolKind } from "../../../../../utils/webResearchTrace";
import phaseStyles from "../phaseBadge.module.css";
import { formatSqlForDisplay } from "./formatSqlForDisplay";
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

const SANDBOX_ERROR_CODES = new Set([
  "unavailable",
  "unauthorized",
  "busy",
  "invalid_request",
  "runtime_unavailable",
  "policy_unavailable",
  "backend_failed",
  "invalid_response",
]);

type SandboxExecution = {
  exit_code: number | null;
  stdout: string;
  stderr: string;
  timed_out: boolean;
  truncated: boolean;
};

function isSandboxExecution(
  result: Record<string, unknown> | null,
): result is Record<string, unknown> & SandboxExecution {
  return (
    result !== null &&
    (typeof result.exit_code === "number" || result.exit_code === null) &&
    typeof result.stdout === "string" &&
    typeof result.stderr === "string" &&
    typeof result.timed_out === "boolean" &&
    typeof result.truncated === "boolean"
  );
}

type SandboxSearchOutput = {
  paths: string[];
  matches: { path: string; line: number; text: string }[];
  visited_files: number;
  visited_entries: number;
  truncated: boolean;
  scope_available: boolean;
};

function parseSandboxSearchOutput(stdout: string, scope: "inputs" | "skills"): SandboxSearchOutput | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(stdout);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
  const value = parsed as Record<string, unknown>;
  const validPath = (path: unknown): path is string =>
    typeof path === "string" && path.startsWith(`/${scope}/`) && path.length <= 512;
  if (
    !Array.isArray(value.paths) ||
    value.paths.length > 50 ||
    !value.paths.every(validPath) ||
    !Array.isArray(value.matches) ||
    value.matches.length > 20 ||
    !value.matches.every((match: unknown) => {
      if (!match || typeof match !== "object" || Array.isArray(match)) return false;
      const item = match as Record<string, unknown>;
      return (
        validPath(item.path) &&
        Number.isInteger(item.line) &&
        (item.line as number) > 0 &&
        typeof item.text === "string" &&
        item.text.length <= 240
      );
    }) ||
    !Number.isInteger(value.visited_files) ||
    (value.visited_files as number) < 0 ||
    (value.visited_files as number) > 1000 ||
    !Number.isInteger(value.visited_entries) ||
    (value.visited_entries as number) < 0 ||
    (value.visited_entries as number) > 10000 ||
    typeof value.truncated !== "boolean" ||
    typeof value.scope_available !== "boolean"
  ) {
    return null;
  }
  return {
    paths: value.paths,
    matches: value.matches,
    visited_files: value.visited_files,
    visited_entries: value.visited_entries,
    truncated: value.truncated,
    scope_available: value.scope_available,
  } as SandboxSearchOutput;
}

function SandboxToolDetail({ entry }: { entry: Extract<TraceEntry, { kind: "combo" }> }) {
  const { t } = useTranslation();
  const args = toolArgs(entry.call);
  const language = args.language === "python" || args.language === "bash" ? args.language : null;
  const code = typeof args.code === "string" ? args.code : null;
  if (!language || code === null) return <GenericToolDetail entry={entry} />;

  const result = entry.result ? parseToolResultContent(entry.result) : null;
  const errorCode = result && typeof result.error_code === "string" ? result.error_code : null;
  const execution = isSandboxExecution(result) ? result : null;

  return (
    <div className={styles.detail}>
      <div className={styles.toolSection}>
        <p className={styles.sectionLabel}>{t("rework.chatTrace.sandbox.code")}</p>
        <CodeBlock code={code} language={language} />
      </div>
      <div className={styles.toolSection}>
        <p className={styles.sectionLabel}>{t("rework.chatTrace.sandbox.result")}</p>
        {!entry.result ? (
          <p className={styles.metaInfo}>{t("rework.chatTrace.toolStatus.running")}</p>
        ) : execution ? (
          <>
            <div className={styles.meta}>
              {execution.exit_code !== null && (
                <span className={styles.metaInfo}>
                  {t("rework.chatTrace.sandbox.exitCode", { code: execution.exit_code })}
                </span>
              )}
              {execution.timed_out && <span className={styles.metaInfo}>{t("rework.chatTrace.sandbox.timedOut")}</span>}
              {execution.truncated && (
                <span className={styles.metaInfo}>{t("rework.chatTrace.sandbox.truncated")}</span>
              )}
            </div>
            {execution.stdout && (
              <div className={styles.toolSection}>
                <p className={styles.sectionLabel}>{t("rework.chatTrace.sandbox.output")}</p>
                <CodeBlock code={execution.stdout} />
              </div>
            )}
            {execution.stderr && (
              <div className={styles.toolSection}>
                <p className={styles.sectionLabel}>{t("rework.chatTrace.sandbox.errors")}</p>
                <CodeBlock code={execution.stderr} />
              </div>
            )}
            {!execution.stdout && !execution.stderr && (
              <p className={styles.metaInfo}>{t("rework.chatTrace.sandbox.noOutput")}</p>
            )}
          </>
        ) : (
          <div className={styles.errorBox}>
            {t(
              `rework.chatTrace.sandbox.errorsByCode.${SANDBOX_ERROR_CODES.has(errorCode ?? "") ? errorCode : "unavailable"}`,
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function SandboxSearchDetail({ entry }: { entry: Extract<TraceEntry, { kind: "combo" }> }) {
  const { t } = useTranslation();
  const args = toolArgs(entry.call);
  if (
    (args.scope !== "inputs" && args.scope !== "skills" && args.scope !== undefined) ||
    (args.file_glob !== undefined && (typeof args.file_glob !== "string" || args.file_glob.length > 200)) ||
    (args.query !== undefined && (typeof args.query !== "string" || args.query.length > 200))
  ) {
    return <GenericToolDetail entry={entry} />;
  }

  const result = entry.result ? parseToolResultContent(entry.result) : null;
  const errorCode = result && typeof result.error_code === "string" ? result.error_code : null;
  const execution = isSandboxExecution(result) ? result : null;
  const scope = args.scope === "skills" ? "skills" : "inputs";
  const output = execution?.exit_code === 0 ? parseSandboxSearchOutput(execution.stdout, scope) : null;

  return (
    <div className={styles.detail}>
      <div className={styles.toolSection}>
        <p className={styles.sectionLabel}>{t("rework.chatTrace.sandbox.search")}</p>
        <CodeBlock
          code={JSON.stringify(
            { scope: args.scope ?? "inputs", file_glob: args.file_glob ?? "*", query: args.query ?? "" },
            null,
            2,
          )}
          language="json"
        />
      </div>
      <div className={styles.toolSection}>
        <p className={styles.sectionLabel}>{t("rework.chatTrace.sandbox.result")}</p>
        {!entry.result ? (
          <p className={styles.metaInfo}>{t("rework.chatTrace.toolStatus.running")}</p>
        ) : output ? (
          <>
            {execution?.truncated && <span className={styles.metaInfo}>{t("rework.chatTrace.sandbox.truncated")}</span>}
            <CodeBlock code={JSON.stringify(output, null, 2)} language="json" />
          </>
        ) : (
          <div className={styles.errorBox}>
            {t(
              `rework.chatTrace.sandbox.errorsByCode.${SANDBOX_ERROR_CODES.has(errorCode ?? "") ? errorCode : "unavailable"}`,
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/** Fallback: redacted {action, status, latency} view for unrecognized tools. */
function GenericToolDetail({ entry }: { entry: Extract<TraceEntry, { kind: "combo" }> }) {
  const { t } = useTranslation();
  const payload = genericToolPayload(
    entry,
    entryLabel(entry, (key) => t(key)),
  );
  return (
    <div className={styles.detail}>
      <CodeBlock code={JSON.stringify(payload, null, 2)} language="json" />
    </div>
  );
}

/** Dispatches a tool-result entry to the richest view its content shape supports. */
function ToolDetail({ entry, messages }: { entry: Extract<TraceEntry, { kind: "combo" }>; messages?: ChatMessage[] }) {
  if (toolSlug(toolName(entry.call)) === "execute_code") return <SandboxToolDetail entry={entry} />;
  if (toolSlug(toolName(entry.call)) === "search_files") return <SandboxSearchDetail entry={entry} />;
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
  const webKind = webResearchToolKind(toolName(entry.call));
  const webResult = webKind && entry.result ? parseWebResearchResult(toolResultContent(entry.result)) : null;
  // A bare-named MCP `web_search` with another payload shape keeps the generic view.
  if (webKind && (webResult || !entry.result)) {
    return (
      <WebResearchToolDetail
        kind={webKind}
        target={webResearchTarget(webKind, toolArgs(entry.call))}
        result={webResult}
      />
    );
  }
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

export function TraceDetailDrawer({ entry, messages, onClose }: TraceDetailDrawerProps) {
  const { t } = useTranslation();
  const label = entry ? entryLabel(entry, (key) => t(key)) : "";
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
