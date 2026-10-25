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

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import type { ChatMessage } from "../../../../../slices/runtime/runtimeOpenApi";
import type { HitlAnswerSummary } from "@rework/utils/hitlAnswerSummary";
import type { TraceRow, TraceSummary } from "../../../../utils/traceUtils";
import {
  formatLatencyMs,
  groupTraceEntries,
  traceEntryKey,
  traceRows,
  traceSummary,
  toolArgs,
  toolCallId,
  toolName,
  toolSlug,
} from "../../../../utils/traceUtils";
import { groupTraceRows, type TraceGroupRule } from "../../../../utils/traceGrouping";
import { useTraceExpansion } from "../../../../core/hooks/useTraceExpansion";
import { ReasoningRow } from "./ReasoningRow/ReasoningRow";
import { TraceEntryRow } from "./TraceEntryRow/TraceEntryRow";
import { ToolTraceGroup } from "./ToolTraceGroup/ToolTraceGroup";
import styles from "./ThoughtTrace.module.css";

interface ThoughtTraceProps {
  messages: ChatMessage[];
  // False while the turn is still streaming; the trace auto-collapses once true.
  done?: boolean;
  /** call_ids of every tool call currently gated behind an unanswered HITL prompt, if any — see statusForEntry(). */
  pendingToolCallIds?: readonly string[] | null;
  hitlAnswerSummariesByCallId?: Record<string, HitlAnswerSummary>;
}

/**
 * Header text: "Reasoning 16.4s · 4 tools".
 *
 * Built from {@link traceSummary} rather than the old `thoughtSummaryLabel`,
 * which announced "Thought for 856ms" — the sum of *tool* latencies — directly
 * above a reasoning row reading 16.4s (#2172).
 */
function useSummaryLabel(summary: TraceSummary): string {
  const { t } = useTranslation();

  if (summary.awaitingConfirmation) return t("rework.chatTrace.awaitingConfirmation");
  if (summary.running) return t("rework.chatTrace.thinking");

  const parts: string[] = [];
  if (summary.reasoningMs !== null) {
    parts.push(t("rework.chatTrace.summaryReasoning", { duration: formatLatencyMs(summary.reasoningMs) }));
  }
  if (summary.toolCount > 0) {
    parts.push(t("rework.chatTrace.summaryTools", { count: summary.toolCount }));
    if (summary.reasoningMs === null && summary.toolMs > 0) parts.push(formatLatencyMs(summary.toolMs));
  }

  return parts.length > 0 ? parts.join(" · ") : t("rework.chatTrace.details");
}

/** Stable empty identity, so the collapsed memo never yields a new array. */
const EMPTY_ROWS: TraceRow[] = [];

function codePreview(code: string): { label: string; value: string } {
  const lines = code
    .split(/\r?\n/)
    .map((line) => line.trim().replace(/\s+/g, " "))
    .filter(Boolean);
  const firstIndex = lines[0]?.startsWith("#!") && lines.length > 1 ? 1 : 0;
  const visibleLines = lines.slice(firstIndex);
  const first = visibleLines[0] ?? "";
  const comment = first.startsWith("#") && !first.startsWith("#!") ? first.slice(1).trim() : "";
  const intent = comment.length > 60 ? `${comment.slice(0, 57)}...` : comment;
  const command = (comment ? visibleLines.slice(1) : visibleLines).join(" ");
  const value =
    command.length > 320 - intent.length ? `${command.slice(0, 317 - intent.length).trimEnd()}...` : command;
  return { label: intent, value };
}

const GROUP_RULES: TraceGroupRule[] = [
  {
    id: "code-sandbox",
    titleKey: "rework.chatTrace.toolLabels.codeSandbox",
    countKey: "rework.chatTrace.toolGroups.commands",
    itemIcon: "terminal",
    matches: (entry) => toolSlug(toolName(entry.call)) === "execute_code",
    itemLabel: () => "",
    preview: (entry) => {
      const code = toolArgs(entry.call).code;
      return typeof code === "string" ? codePreview(code) : "";
    },
  },
];

export function ThoughtTrace({
  messages,
  done = false,
  pendingToolCallIds,
  hitlAnswerSummariesByCallId,
}: ThoughtTraceProps) {
  const { t } = useTranslation();
  // Memoized: this fold runs on every streamed delta, and the page re-renders
  // for reasons of its own on top of that.
  const entries = useMemo(() => groupTraceEntries(messages), [messages]);
  const summary = useMemo(() => traceSummary(entries, pendingToolCallIds), [entries, pendingToolCallIds]);
  const label = useSummaryLabel(summary);
  const { expanded, toggle } = useTraceExpansion(done);
  // Only when open. `toThreadMessages` rebuilds every exchange's traceMessages
  // array on each streamed frame, so this memo is invalidated for the WHOLE
  // conversation on every token — and traceRows flattens markdown. Behind the
  // toggle, a long history's collapsed traces cost nothing per token.
  const rows = useMemo(() => (expanded ? traceRows(entries) : EMPTY_ROWS), [entries, expanded]);
  const displayItems = useMemo(() => groupTraceRows(rows, GROUP_RULES, messages), [rows, messages]);

  if (entries.length === 0) return null;

  return (
    <div className={styles.root} aria-label={t("rework.chatTrace.ariaLabel")}>
      <button
        type="button"
        className={styles.toggle}
        onClick={toggle}
        aria-expanded={expanded}
        title={t(expanded ? "rework.chatTrace.hide" : "rework.chatTrace.show")}
      >
        <span className={styles.chevron} aria-hidden="true">
          <Icon category="outlined" type={expanded ? "expand_less" : "expand_more"} />
        </span>
        <span className={`${styles.summary} ${summary.running ? styles.summaryStreaming : ""}`}>{label}</span>
      </button>

      {/* One sequence, in the order the turn actually unfolded: reasoning and
          tool steps alternate rather than being stacked into two lanes. */}
      {expanded && (
        <div className={styles.body}>
          {displayItems.map((item) => {
            if (item.kind === "group") {
              return <ToolTraceGroup key={item.key} group={item} pendingToolCallIds={pendingToolCallIds} />;
            }
            const { entry, lane, reasoningText, restated } = item.row;
            return lane === "reasoning" ? (
              <ReasoningRow key={traceEntryKey(entry)} entry={entry} text={reasoningText ?? ""} restated={restated} />
            ) : (
              <TraceEntryRow
                key={traceEntryKey(entry)}
                entry={entry}
                index={item.index}
                pendingToolCallIds={pendingToolCallIds}
                hitlAnswerSummary={
                  entry.kind === "combo" ? hitlAnswerSummariesByCallId?.[toolCallId(entry.call)] : undefined
                }
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
