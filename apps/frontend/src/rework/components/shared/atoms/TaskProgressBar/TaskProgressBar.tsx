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

import ProgressBar from "../ProgressBar/ProgressBar";
import type { TaskState } from "../../../../features/tasks/taskTypes";
import type { ColorTheme } from "../../utils/Type";
import styles from "./TaskProgressBar.module.css";

interface TaskProgressBarProps {
  state: TaskState;
  /** 0–1 fraction. null means indeterminate (shimmer). */
  progress: number | null;
}

const STATE_THEME: Record<TaskState, ColorTheme> = {
  pending: "on-surface-retreat",
  running: "info",
  cancelling: "warning",
  succeeded: "success",
  failed: "error",
  cancelled: "on-surface-retreat",
};

export function TaskProgressBar({ state, progress }: TaskProgressBarProps) {
  const theme = STATE_THEME[state];

  if (progress === null) {
    return (
      <div className={styles.shimmerTrack} role="progressbar" aria-label="loading" data-color={theme}>
        <div className={styles.shimmerFill} />
      </div>
    );
  }

  return <ProgressBar theme={theme} current={Math.round(progress * 100)} max={100} />;
}
