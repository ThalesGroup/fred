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
import type { TraceEntry, TraceStatus } from "../../../../../utils/traceUtils";
import {
  entryLabel,
  phaseKeyForEntry,
  primaryTextForEntry,
  secondaryTextForEntry,
  statusForEntry,
  toolDiscriminator,
} from "../../../../../utils/traceUtils";
import { useTraceDrawer } from "../traceDrawerContext";
import phaseStyles from "../phaseBadge.module.css";
import styles from "./TraceEntryRow.module.css";

interface TraceEntryRowProps {
  entry: TraceEntry;
  /** 1-based tool step number. Null for notes/errors, which are not steps. */
  index?: number | null;
  /** call_ids of every tool call currently gated behind an unanswered HITL prompt, if any — see statusForEntry(). */
  pendingToolCallIds?: readonly string[] | null;
}

function DotStatus({ status }: { status: TraceStatus }) {
  return <span className={`${styles.dot} ${styles[`dot_${status}`]}`} aria-label={status} />;
}

export function TraceEntryRow({ entry, index = null, pendingToolCallIds }: TraceEntryRowProps) {
  const { t } = useTranslation();
  const { openTrace } = useTraceDrawer();
  const status = statusForEntry(entry, pendingToolCallIds);
  const label = entryLabel(entry);
  const phase = phaseKeyForEntry(entry);
  const primary = primaryTextForEntry(entry);
  const secondary = secondaryTextForEntry(entry);
  const isPending = status === "pending";
  const isAwaitingConfirmation = status === "awaiting_confirmation";

  // Curated volume metadata (never raw args/content) so two calls to the same
  // tool are distinguishable — "Reading query" ×2 was byte-identical (#2172).
  const discriminator = toolDiscriminator(entry);
  const discriminatorText = discriminator
    ? t(`rework.chatTrace.${discriminator.kind}`, { count: discriminator.count })
    : "";

  return (
    <div
      className={`${styles.row} ${styles[`row_${status}`]}`}
      role="button"
      tabIndex={0}
      aria-label={`${index !== null ? `${index}. ` : ""}${label}${primary ? `: ${primary}` : ""}`}
      onClick={() => openTrace(entry)}
      onKeyDown={(e) => e.key === "Enter" && openTrace(entry)}
    >
      {/* Always rendered, empty for unnumbered notes, so the status dots of every
          row stay on the same vertical line as the timeline guideline. */}
      <span className={styles.index} aria-hidden="true">
        {index ?? ""}
      </span>

      <DotStatus status={status} />

      <span
        className={phase ? `${phaseStyles.phaseBadge} ${styles.phaseBadge}` : styles.label}
        data-phase={phase ?? undefined}
      >
        {label}
      </span>

      {discriminatorText && <span className={styles.discriminator}>{discriminatorText}</span>}

      <span className={`${styles.primary} ${isPending || isAwaitingConfirmation ? styles.primaryPending : ""}`}>
        {primary ||
          (isAwaitingConfirmation
            ? t("rework.chatTrace.awaitingConfirmation")
            : isPending
              ? t("rework.chatTrace.running")
              : "")}
      </span>

      {secondary && <span className={styles.secondary}>{secondary}</span>}
    </div>
  );
}
