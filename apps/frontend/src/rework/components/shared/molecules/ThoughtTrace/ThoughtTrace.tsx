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
import type { ChatMessage } from "../../../../../slices/agentic/agenticOpenApi";
import { groupTraceEntries, thoughtSummaryLabel } from "../../../../utils/traceUtils";
import { TraceEntryRow } from "./TraceEntryRow/TraceEntryRow";
import styles from "./ThoughtTrace.module.css";

interface ThoughtTraceProps {
  messages: ChatMessage[];
  // When the final reply has arrived the trace auto-collapses; pass false while still streaming
  done?: boolean;
}

export function ThoughtTrace({ messages, done = false }: ThoughtTraceProps) {
  const entries = groupTraceEntries(messages);
  const [expanded, setExpanded] = useState(true);

  if (entries.length === 0) return null;

  const summary = thoughtSummaryLabel(entries);

  return (
    <div className={styles.root} aria-label="Agent reasoning trace">
      <button className={styles.toggle} onClick={() => setExpanded((v) => !v)} aria-expanded={expanded}>
        <span className={`${styles.chevron} ${expanded ? styles.chevronOpen : ""}`}>›</span>
        <span className={`${styles.summary} ${!done ? styles.summaryStreaming : ""}`}>{summary}</span>
      </button>

      {expanded && (
        <div className={styles.body}>
          <div className={styles.guideline} aria-hidden="true" />
          <div className={styles.entries}>
            {entries.map((entry, i) => (
              <TraceEntryRow key={i} entry={entry} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
