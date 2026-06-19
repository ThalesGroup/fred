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

import type { TraceEntry, TraceStatus } from "../../../../../utils/traceUtils";
import {
  entryLabel,
  phaseKeyForEntry,
  primaryTextForEntry,
  secondaryTextForEntry,
  statusForEntry,
} from "../../../../../utils/traceUtils";
import { useTraceDrawer } from "../traceDrawerContext";
import phaseStyles from "../phaseBadge.module.css";
import styles from "./TraceEntryRow.module.css";

interface TraceEntryRowProps {
  entry: TraceEntry;
}

function DotStatus({ status }: { status: TraceStatus }) {
  return <span className={`${styles.dot} ${styles[`dot_${status}`]}`} aria-label={status} />;
}

export function TraceEntryRow({ entry }: TraceEntryRowProps) {
  const { openTrace } = useTraceDrawer();
  const status = statusForEntry(entry);
  const label = entryLabel(entry);
  const phase = phaseKeyForEntry(entry);
  const primary = primaryTextForEntry(entry);
  const secondary = secondaryTextForEntry(entry);
  const isPending = status === "pending";

  return (
    <div
      className={`${styles.row} ${styles[`row_${status}`]}`}
      role="button"
      tabIndex={0}
      aria-label={`${label}: ${primary}`}
      onClick={() => openTrace(entry)}
      onKeyDown={(e) => e.key === "Enter" && openTrace(entry)}
    >
      <DotStatus status={status} />

      <div className={styles.labelRow}>
        <span
          className={phase ? `${phaseStyles.phaseBadge} ${styles.phaseBadge}` : styles.label}
          data-phase={phase ?? undefined}
        >
          {label}
        </span>
        <span className={`${styles.primary} ${isPending ? styles.primaryPending : ""}`}>
          {primary || (isPending ? "running…" : "")}
        </span>
      </div>

      {secondary && <span className={styles.secondary}>{secondary}</span>}
    </div>
  );
}
