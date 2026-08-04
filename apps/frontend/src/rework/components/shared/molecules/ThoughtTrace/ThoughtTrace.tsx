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
import Icon from "@shared/atoms/Icon/Icon";
import type { ChatMessage } from "../../../../../slices/agentic/agenticOpenApi";
import type { TraceSummary } from "../../../../utils/traceUtils";
import {
  formatLatencyMs,
  groupTraceEntries,
  splitTraceEntries,
  traceEntryKey,
  traceSummary,
} from "../../../../utils/traceUtils";
import { useTraceExpansion } from "../../../../core/hooks/useTraceExpansion";
import { ReasoningBlock } from "./ReasoningBlock/ReasoningBlock";
import { TraceEntryRow } from "./TraceEntryRow/TraceEntryRow";
import styles from "./ThoughtTrace.module.css";

interface ThoughtTraceProps {
  messages: ChatMessage[];
  // False while the turn is still streaming; the trace auto-collapses once true.
  done?: boolean;
  /** call_ids of every tool call currently gated behind an unanswered HITL prompt, if any — see statusForEntry(). */
  pendingToolCallIds?: readonly string[] | null;
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

export function ThoughtTrace({ messages, done = false, pendingToolCallIds }: ThoughtTraceProps) {
  const { t } = useTranslation();
  const entries = groupTraceEntries(messages);
  const { reasoning, steps } = splitTraceEntries(entries);
  const summary = traceSummary(entries, pendingToolCallIds);
  const label = useSummaryLabel(summary);
  const { expanded, toggle } = useTraceExpansion(done);

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

      {expanded && (
        <div className={styles.body}>
          <ReasoningBlock entries={reasoning} continues={steps.length > 0} />

          {/* No section header: the step numbers already say what this list is,
              and the header text was pure visual weight. */}
          {steps.length > 0 && (
            <div className={`${styles.entries} ${reasoning.length === 0 ? styles.entriesLeading : ""}`}>
              {steps.map(({ entry, index }) => (
                <TraceEntryRow
                  key={traceEntryKey(entry)}
                  entry={entry}
                  index={index}
                  pendingToolCallIds={pendingToolCallIds}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
