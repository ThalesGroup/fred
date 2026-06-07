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

import type { TaskViewModel } from "../../../../features/tasks/taskTypes";
import { TERMINAL_STATES } from "../../../../features/tasks/taskTypes";
import { TaskProgressBar } from "../../atoms/TaskProgressBar/TaskProgressBar";
import { TaskStateBadge } from "../../atoms/TaskStateBadge/TaskStateBadge";
import styles from "./TaskCard.module.css";

interface TaskCardProps {
  task: TaskViewModel;
}

export function relativeTime(ms: number, now = Date.now()): string {
  const diffS = Math.floor((now - ms) / 1000);
  if (diffS < 60) return "just now";
  const diffM = Math.floor(diffS / 60);
  if (diffM < 60) return `${diffM} min ago`;
  const diffH = Math.floor(diffM / 60);
  return `${diffH}h ago`;
}

export function truncate(name: string, max = 32): string {
  return name.length > max ? `${name.slice(0, max - 1)}…` : name;
}

export function TaskCard({ task }: TaskCardProps) {
  const isTerminal = TERMINAL_STATES.has(task.state);
  const timeMs = task.terminalAt ?? task.registeredAt;
  const displayName = task.target?.label ?? task.taskId;

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
          <span className={styles.errorText}>{task.error}</span>
        ) : task.step ? (
          <span className={styles.stepText}>{task.step}</span>
        ) : null}
        <span className={styles.timestamp}>{relativeTime(timeMs)}</span>
      </div>
    </div>
  );
}
