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
import IconButton from "@shared/atoms/IconButton/IconButton";
import MonacoPane from "@shared/atoms/MonacoPane/MonacoPane";
import { InlineDrawer } from "../../InlineDrawer/InlineDrawer";
import { MarkdownRenderer } from "../../MarkdownRenderer/MarkdownRenderer";
import type { TraceEntry } from "../../../../../utils/traceUtils";
import {
  PHASE_LABELS,
  detailTextForEntry,
  entryLabel,
  formatLatencyMs,
  humanizeToolName,
  phaseKeyForEntry,
  sourceForEntry,
  statusForEntry,
  thoughtExtras,
  toolName,
  toolResultLatencyMs,
  toolResultOk,
} from "../../../../../utils/traceUtils";
import phaseStyles from "../phaseBadge.module.css";
import styles from "./TraceDetailDrawer.module.css";

interface TraceDetailDrawerProps {
  /** The entry to inspect, or null when the panel is closed. */
  entry: TraceEntry | null;
  onClose: () => void;
}

function toolPayload(entry: Extract<TraceEntry, { kind: "combo" }>): unknown {
  // Expose only the humanized action name and execution outcome.
  // Raw tool names, arguments, and result payloads must not be shown to end users.
  const action = humanizeToolName(toolName(entry.call));
  if (!entry.result) return { action, status: "running" };
  return {
    action,
    status: toolResultOk(entry.result) ? "completed" : "failed",
    latency: formatLatencyMs(toolResultLatencyMs(entry.result)),
  };
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

/** Structured JSON view for tool call / result entries. */
function ToolDetail({ entry }: { entry: Extract<TraceEntry, { kind: "combo" }> }) {
  const payload = toolPayload(entry);
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard
      .writeText(JSON.stringify(payload, null, 2))
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      })
      .catch(() => {});
  };

  return (
    <>
      <div className={styles.toolbar}>
        <span className={styles.spacer} />
        <IconButton
          color="on-surface"
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: copied ? "check_circle" : "content_copy" }}
          aria-label={copied ? "Copied" : "Copy JSON"}
          onClick={handleCopy}
        />
      </div>
      <MonacoPane
        value={JSON.stringify(payload, null, 2)}
        height="calc(100vh - 160px)"
        options={{ lineNumbers: "off", folding: true }}
      />
    </>
  );
}

export function TraceDetailDrawer({ entry, onClose }: TraceDetailDrawerProps) {
  const label = entry ? entryLabel(entry) : "";

  return (
    <InlineDrawer open={entry !== null} onClose={onClose} title={label} layout="overlay" width="460px">
      {entry && (entry.kind === "combo" ? <ToolDetail entry={entry} /> : <TextDetail entry={entry} />)}
    </InlineDrawer>
  );
}
