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

import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { TaskViewModel } from "../../../../features/tasks/taskTypes";
import { TERMINAL_STATES } from "../../../../features/tasks/taskTypes";
import { STATE_COLOR, relativeTime, stepLabel } from "../../../../features/tasks/taskLabels";
import IconButton from "../../atoms/IconButton/IconButton.tsx";
import { Tooltip } from "../../atoms/Tooltip/Tooltip.tsx";
import { writeRichClipboard } from "@rework/utils/clipboardUtils";
import { TaskProgressBar } from "../../atoms/TaskProgressBar/TaskProgressBar";
import { TaskStateBadge } from "../../atoms/TaskStateBadge/TaskStateBadge";
import styles from "./TaskCard.module.css";

interface TaskCardProps {
  task: TaskViewModel;
  /** Replaces the footer's own error/step line. For a caller that knows the
   *  task's domain and can say more about it than a generic card can — the
   *  import panel naming a failure's cause, rather than showing the sentence
   *  the backend wrote for a log. */
  statusText?: string;
  /** The detail behind `statusText`, on hover. */
  statusDetail?: string | null;
  /** Controls next to the dismiss button — a retry, a decision to make. */
  actions?: ReactNode;
  /** Replaces the progress bar at the foot of the card. For a caller whose
   *  task has no measurable progress to show — an import, where the server
   *  reports named phases rather than a fraction. */
  progressSlot?: ReactNode;
  /** Replaces the footer's timestamp. For a caller with something live to put
   *  there while the task runs — an import's phase markers, facing the name of
   *  the phase they are on. Omit it and the timestamp comes back. */
  trailingSlot?: ReactNode;
  /** Present only when this task can be acknowledged (failed/cancelled, not
   *  yet acknowledged) — the caller owns the `POST /tasks/{id}/ack` call and
   *  the resulting store update (TASK-EVENT-STREAM-RFC.md §2.10). */
  onAcknowledge?: () => void;
  acknowledging?: boolean;
}

export function TaskCard({
  task,
  statusText,
  statusDetail,
  actions,
  progressSlot,
  trailingSlot,
  onAcknowledge,
  acknowledging,
}: TaskCardProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const isTerminal = TERMINAL_STATES.has(task.state);
  const timeMs = task.terminalAt ?? task.registeredAt;
  const displayName = task.target?.label ?? task.taskId;
  const needsAttention =
    (task.state === "failed" || task.state === "cancelled") && task.acknowledgedAt === null && !!onAcknowledge;

  const handleCopyWarnings = async () => {
    if (!task.warnings || task.warnings.length === 0) return;
    const ok = await writeRichClipboard("", task.warnings.join("\n"));
    if (ok) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    }
  };

  return (
    <div className={styles.card} data-state={task.state}>
      <div className={styles.header}>
        {/* The state reads as a colour before it reads as anything else, so it
            leads the line the name is on. */}
        <TaskStateBadge state={task.state} showLabel={false} size="sm" />
        {/* Cut by the CSS ellipsis, which cuts at the width actually left —
            a character count cut short names in a wide card. */}
        <span className={styles.filename} title={displayName}>
          {displayName}
        </span>
        {/* Always present, even empty: the buttons are twice the line's height,
            so letting the row size itself would jolt the card every time one
            appeared. */}
        <div className={styles.toolbar}>
          {actions}
          {needsAttention && (
            <IconButton
              variant="icon"
              size="small"
              icon={{ category: "outlined", type: "close" }}
              onClick={onAcknowledge}
              disabled={acknowledging}
              title={t("rework.tasks.card.acknowledge")}
            />
          )}
        </div>
      </div>

      <div className={styles.footer}>
        {statusText ? (
          <span className={styles.stepText} style={{ color: STATE_COLOR[task.state] }}>
            {statusDetail ? (
              <Tooltip content={<span className={styles.errorTooltip}>{statusDetail}</span>}>
                <span>{statusText}</span>
              </Tooltip>
            ) : (
              statusText
            )}
          </span>
        ) : task.state === "failed" && task.error ? (
          // Tooltip's own wrapper is inline-flex with no flex-grow of its own — nesting it
          // *inside* .errorText (rather than putting .errorText on the wrapper itself) keeps
          // the existing flex:1/min-width:0/ellipsis truncation on the real flex item, so the
          // Tooltip's internal markup never has to know about TaskCard's row layout.
          <span className={styles.errorText}>
            <Tooltip content={<span className={styles.errorTooltip}>{task.error}</span>}>
              <span>{task.error}</span>
            </Tooltip>
          </span>
        ) : task.step ? (
          <span className={styles.stepText} style={{ color: STATE_COLOR[task.state] }}>
            {stepLabel(task, t)}
          </span>
        ) : null}
        {task.warnings && task.warnings.length > 0 && (
          <div className={styles.warningGroup}>
            <Tooltip
              content={
                <ul className={styles.warningTooltip}>
                  {task.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              }
            >
              <span className={styles.warningBadge}>⚠ {task.warnings.length}</span>
            </Tooltip>
            <IconButton
              variant="icon"
              size="small"
              icon={{
                category: "outlined",
                type: copied ? "check_circle" : "content_copy",
                filled: false,
              }}
              onClick={handleCopyWarnings}
              title={copied ? t("rework.tasks.card.copied") : t("rework.tasks.card.copyWarnings")}
            />
          </div>
        )}
        {trailingSlot ?? <span className={styles.timestamp}>{relativeTime(timeMs, t)}</span>}
      </div>

      {progressSlot !== undefined ? (
        <div className={styles.progressRow}>{progressSlot}</div>
      ) : (
        !isTerminal && (
          <div className={styles.progressRow}>
            <TaskProgressBar state={task.state} progress={task.progress} />
          </div>
        )
      )}
    </div>
  );
}
