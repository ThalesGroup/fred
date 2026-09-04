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
import { formatLatencyMs, sourceForEntry, statusForEntry, thoughtExtras } from "../../../../../utils/traceUtils";
import { useTraceDrawer } from "../traceDrawerContext";
import styles from "./ReasoningRow.module.css";

/**
 * One reasoning entry, sequenced in the trace where it actually happened.
 *
 * Deliberately NOT a `TraceEntryRow`: reasoning is not a tool step (#2172), so
 * it gets no step number and no status dot. It shares the timeline geometry
 * though — the icon is its marker on the rail, the way the status dot is a tool
 * row's — so the two read as one sequence rather than two stacked lists.
 *
 * `text` is supplied rather than derived here: it is trimmed of whatever the
 * previous reasoning row already showed, which only `traceRows` can know.
 */
export function ReasoningRow({ entry, text }: { entry: TraceEntry; text: string }) {
  const { t } = useTranslation();
  const { openTrace } = useTraceDrawer();

  const extras = entry.kind === "solo" ? thoughtExtras(entry.message) : {};
  const isStreaming = statusForEntry(entry) === "streaming";
  const durationMs = extras.duration_ms ?? null;

  // Model-native blocks carry a generic backend title ("Model reasoning") that
  // says nothing the row doesn't. Authored titles are author-written, so they
  // earn their place.
  const title = sourceForEntry(entry) === "model_native" ? null : extras.title;

  // Named by its own content, like a tool row is. A turn now holds one reasoning
  // row per ReAct round, so a fixed label would announce them all identically and
  // the reasoning itself would never reach assistive tech. The generic label is
  // kept only for a row that has no text yet — a block that just opened.
  const spokenLabel = [title, text, extras.conclusion].filter(Boolean).join(". ");

  return (
    <button
      type="button"
      className={styles.row}
      onClick={() => openTrace(entry)}
      aria-label={spokenLabel || t("rework.chatTrace.openReasoning")}
    >
      <span className={`${styles.marker} ${isStreaming ? styles.markerLive : ""}`} aria-hidden="true">
        <Icon category="outlined" type="settings" filled />
      </span>

      <span className={styles.content}>
        {title && <span className={styles.title}>{title}</span>}

        {/* Clamped to three lines of the block's OWN content — the repeated
            preamble is already gone. Markdown is flattened; the rendered version
            lives in the detail drawer. */}
        {text && <span className={styles.preview}>{text}</span>}

        {extras.conclusion && <span className={styles.conclusion}>{extras.conclusion}</span>}
      </span>

      {durationMs != null && <span className={styles.duration}>{formatLatencyMs(durationMs)}</span>}
    </button>
  );
}
