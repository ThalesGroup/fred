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
import type { TaskViewModel } from "../../../../features/tasks/taskTypes";
import { TERMINAL_STATES } from "../../../../features/tasks/taskTypes";
import { relativeTime } from "../../../../features/tasks/taskLabels";
import IconButton from "../../atoms/IconButton/IconButton.tsx";
import { Tooltip } from "../../atoms/Tooltip/Tooltip.tsx";
import { TaskProgressBar } from "../../atoms/TaskProgressBar/TaskProgressBar";
import { TaskStateBadge } from "../../atoms/TaskStateBadge/TaskStateBadge";
import styles from "./TaskCard.module.css";

interface TaskCardProps {
  task: TaskViewModel;
}

export function truncate(name: string, max = 32): string {
  return name.length > max ? `${name.slice(0, max - 1)}…` : name;
}

export function TaskCard({ task }: TaskCardProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const isTerminal = TERMINAL_STATES.has(task.state);
  const timeMs = task.terminalAt ?? task.registeredAt;
  const displayName = task.target?.label ?? task.taskId;

  const handleCopyWarnings = async () => {
    if (!task.warnings || task.warnings.length === 0) return;
    await navigator.clipboard.writeText(task.warnings.join("\n"));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className={styles.card} data-state={task.state}>
      <div className={styles.header}>
        <span className={styles.filename} title={displayName}>
          {truncate(displayName)}
        </span>
        <TaskStateBadge state={task.state} showLabel={false} size="sm" />
      </div>

      {!isTerminal && (
        <div className={styles.progressRow}>
          <TaskProgressBar state={task.state} progress={task.progress} />
        </div>
      )}

      <div className={styles.footer}>
        {task.state === "failed" && task.error ? (
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
          <span className={styles.stepText}>{task.step}</span>
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
              color="on-surface"
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
        <span className={styles.timestamp}>{relativeTime(timeMs, t)}</span>
      </div>
    </div>
  );
}
