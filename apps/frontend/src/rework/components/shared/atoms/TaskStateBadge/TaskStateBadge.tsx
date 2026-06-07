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

import type { TaskState } from "../../../../features/tasks/taskTypes";
import styles from "./TaskStateBadge.module.css";

const STATE_COLOR: Record<TaskState, string> = {
  pending: "var(--on-surface-retreat)",
  running: "var(--info)",
  cancelling: "var(--warning)",
  succeeded: "var(--success)",
  failed: "var(--error)",
  cancelled: "var(--on-surface-retreat)",
};

const STATE_LABEL: Record<TaskState, string> = {
  pending: "Pending",
  running: "Running",
  cancelling: "Cancelling",
  succeeded: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};

interface TaskStateBadgeProps {
  state: TaskState;
  showLabel?: boolean;
  size?: "sm" | "md";
}

export function TaskStateBadge({ state, showLabel = true, size = "sm" }: TaskStateBadgeProps) {
  return (
    <span className={styles.badge} data-size={size}>
      <span
        className={styles.dot}
        data-state={state}
        style={{ "--badge-color": STATE_COLOR[state] } as React.CSSProperties}
        role="img"
        aria-label={STATE_LABEL[state]}
      />
      {showLabel && (
        <span className={styles.label} style={{ color: STATE_COLOR[state] }}>
          {STATE_LABEL[state]}
        </span>
      )}
    </span>
  );
}
