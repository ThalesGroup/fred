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
import type { TraceEntry } from "../../../../../utils/traceUtils";
import {
  PHASE_LABELS,
  detailTextForEntry,
  formatLatencyMs,
  plainPreviewText,
  phaseKeyForEntry,
  sourceForEntry,
  statusForEntry,
  thoughtExtras,
  traceEntryKey,
} from "../../../../../utils/traceUtils";
import { useTraceDrawer } from "../traceDrawerContext";
import styles from "./ReasoningBlock.module.css";

interface ReasoningBlockProps {
  /** Reasoning entries only (thought / plan / observation) — see `splitTraceEntries`. */
  entries: TraceEntry[];
  /** True when tool steps follow, so the timeline rail must run on past the last card. */
  continues: boolean;
}

/**
 * One reasoning card. Deliberately NOT a `TraceEntryRow`: reasoning is not a
 * tool step (#2172). It gets its own card so it stops squatting the top of the
 * tool list — where, because the model-native block only closes when the answer
 * starts streaming, it looked like a tool stuck in "running" for the whole turn.
 */
function ReasoningCard({ entry, trailing }: { entry: TraceEntry; trailing: boolean }) {
  const { t } = useTranslation();
  const { openTrace } = useTraceDrawer();

  const extras = entry.kind === "solo" ? thoughtExtras(entry.message) : {};
  const phase = phaseKeyForEntry(entry);
  const phaseLabel = phase
    ? t(`rework.chatTrace.phase.${phase}`, { defaultValue: PHASE_LABELS[phase] ?? phase })
    : null;
  const isStreaming = statusForEntry(entry) === "streaming";
  const text = plainPreviewText(detailTextForEntry(entry));
  const durationMs = extras.duration_ms ?? null;

  // Model-native blocks carry a generic backend title ("Model reasoning") that
  // says nothing the phase label doesn't — showing both, plus a "Model" chip,
  // was three labels for one thing. Authored titles are author-written, so they
  // earn their place.
  const title = sourceForEntry(entry) === "model_native" ? null : extras.title;

  return (
    <button
      type="button"
      className={`${styles.card} ${trailing ? "" : styles.cardEnd}`}
      onClick={() => openTrace(entry)}
      aria-label={t("rework.chatTrace.openReasoning")}
    >
      <span className={styles.header}>
        <span className={`${styles.icon} ${isStreaming ? styles.iconLive : ""}`} aria-hidden="true">
          <Icon category="outlined" type="auto_awesome" />
        </span>

        {phaseLabel && <span className={styles.phase}>{phaseLabel}</span>}

        {title && <span className={styles.title}>{title}</span>}

        <span className={styles.spacer} />

        {durationMs != null && <span className={styles.duration}>{formatLatencyMs(durationMs)}</span>}
      </span>

      {/* Clamped preview only — the full markdown lives in the detail drawer. */}
      {text && <span className={styles.preview}>{text}</span>}

      {extras.conclusion && <span className={styles.conclusion}>{extras.conclusion}</span>}
    </button>
  );
}

/** The reasoning lane of a trace: zero or more reasoning cards, no tool steps. */
export function ReasoningBlock({ entries, continues }: ReasoningBlockProps) {
  if (entries.length === 0) return null;

  return (
    <div className={styles.root}>
      {entries.map((entry, i) => (
        <ReasoningCard key={traceEntryKey(entry)} entry={entry} trailing={continues || i < entries.length - 1} />
      ))}
    </div>
  );
}
