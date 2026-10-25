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
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import type { TraceDisplayItem, TraceGroupRule } from "@rework/utils/traceGrouping";
import { isCancelledByUser, statusForEntry, traceEntryKey, type ToolEntry } from "@rework/utils/traceUtils";
import { ReasoningRow } from "../ReasoningRow/ReasoningRow";
import { useTraceDrawer } from "../traceDrawerContext";
import styles from "./ToolTraceGroup.module.css";

type Group = Extract<TraceDisplayItem, { kind: "group" }>;
type Preview = ReturnType<TraceGroupRule["preview"]>;

function previewText(preview: Preview): string {
  return typeof preview === "string" ? preview : [preview.label, preview.value].filter(Boolean).join(" - ");
}

function previewContent(preview: Preview) {
  if (typeof preview === "string") return preview;
  return (
    <>
      {preview.label && <span className={styles.previewLabel}>{preview.label}</span>}
      {preview.label && preview.value && <span className={styles.previewSeparator}> - </span>}
      {preview.value && <code className={styles.previewValue}>{preview.value}</code>}
    </>
  );
}

export function ToolTraceGroup({
  group,
  pendingToolCallIds,
}: {
  group: Group;
  pendingToolCallIds?: readonly string[] | null;
}) {
  const { t } = useTranslation();
  const { openTrace } = useTraceDrawer();
  const [expanded, setExpanded] = useState(false);
  const calls = group.rows.filter((row): row is typeof row & { entry: ToolEntry } => row.entry.kind === "combo");
  const current =
    [...calls].reverse().find((row) => statusForEntry(row.entry, pendingToolCallIds) === "pending") ??
    calls[calls.length - 1];
  const statuses = calls.map((row) => statusForEntry(row.entry, pendingToolCallIds));
  const status = statuses.includes("pending")
    ? "pending"
    : statuses.includes("awaiting_confirmation")
      ? "awaiting_confirmation"
      : statuses.includes("error")
        ? "error"
        : "ok";
  const preview = current ? group.rule.preview(current.entry) : "";
  const headingPreview = typeof preview === "string" ? preview : preview.label;
  const spokenStatus =
    status === "pending"
      ? t("rework.chatTrace.toolStatus.running")
      : status === "awaiting_confirmation"
        ? t("rework.chatTrace.awaitingConfirmation")
        : calls.some(
              (row) => statusForEntry(row.entry, pendingToolCallIds) === "error" && !isCancelledByUser(row.entry),
            )
          ? t("rework.chatTrace.toolStatus.failure")
          : calls.some((row) => isCancelledByUser(row.entry))
            ? t("rework.chatTrace.cancelledByUser")
            : t("rework.chatTrace.toolStatus.success");
  return (
    <div className={styles.group}>
      <button
        type="button"
        className={styles.heading}
        aria-expanded={expanded}
        aria-label={`${group.index}. ${t(group.rule.titleKey)}. ${t(group.rule.countKey, { count: group.count })}. ${spokenStatus}${headingPreview ? `. ${headingPreview}` : ""}`}
        onClick={() => setExpanded((value) => !value)}
      >
        <span className={styles.marker} aria-hidden="true">
          <span className={`${styles.dot} ${styles[`dot_${status}`]}`} />
          <span className={styles.index}>{group.index}</span>
        </span>
        <span className={styles.title}>{t(group.rule.titleKey)}</span>
        <span className={styles.count}>{t(group.rule.countKey, { count: group.count })}</span>
        {headingPreview && <span className={styles.preview}>{headingPreview}</span>}
        <Icon category="outlined" type={expanded ? "expand_less" : "expand_more"} />
      </button>
      {expanded && (
        <div className={styles.children}>
          {group.rows.map((row) => {
            if (row.lane === "reasoning") {
              return (
                <ReasoningRow
                  key={traceEntryKey(row.entry)}
                  entry={row.entry}
                  text={row.reasoningText ?? ""}
                  restated={row.restated}
                />
              );
            }
            if (row.entry.kind !== "combo") return null;
            const entry = row.entry;
            const childStatus = statusForEntry(entry, pendingToolCallIds);
            const cancelled = isCancelledByUser(entry);
            const itemLabel = group.rule.itemLabel(entry);
            const itemPreview = group.rule.preview(entry);
            const itemPreviewText = previewText(itemPreview);
            const statusText =
              childStatus === "ok"
                ? t("rework.chatTrace.toolStatus.success")
                : cancelled
                  ? t("rework.chatTrace.cancelledByUser")
                  : childStatus === "error"
                    ? t("rework.chatTrace.toolStatus.failure")
                    : childStatus === "awaiting_confirmation"
                      ? t("rework.chatTrace.awaitingConfirmation")
                      : t("rework.chatTrace.toolStatus.running");
            return (
              <button
                type="button"
                key={traceEntryKey(entry)}
                className={styles.child}
                aria-label={[itemLabel, itemPreviewText, statusText].filter(Boolean).join(". ")}
                onClick={() => openTrace(entry)}
              >
                <span className={`${styles.childDot} ${styles[`dot_${childStatus}`]}`} aria-hidden="true" />
                {itemLabel && <span className={styles.childTitle}>{itemLabel}</span>}
                {itemPreviewText && <span className={styles.childPreview}>{previewContent(itemPreview)}</span>}
                {childStatus !== "ok" && <span className={styles.childStatus}>{statusText}</span>}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
