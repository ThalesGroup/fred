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
import type { TaskState } from "../../../../features/tasks/taskTypes";
import { STATE_COLOR, stateLabel } from "../../../../features/tasks/taskLabels";
import styles from "./TaskStateBadge.module.css";

interface TaskStateBadgeProps {
  state: TaskState;
  showLabel?: boolean;
  size?: "sm" | "md";
}

export function TaskStateBadge({ state, showLabel = true, size = "sm" }: TaskStateBadgeProps) {
  const { t } = useTranslation();
  const label = stateLabel(state, t);
  return (
    <span className={styles.badge} data-size={size}>
      <span
        className={styles.dot}
        data-state={state}
        style={{ "--badge-color": STATE_COLOR[state] } as React.CSSProperties}
        role="img"
        aria-label={label}
      />
      {showLabel && (
        <span className={styles.label} style={{ color: STATE_COLOR[state] }}>
          {label}
        </span>
      )}
    </span>
  );
}
