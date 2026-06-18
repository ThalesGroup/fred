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

import * as React from "react";
import { useSelector } from "react-redux";
import { useTranslation } from "react-i18next";
import { selectTask } from "../../../../features/tasks/taskSlice";
import { getKindMeta } from "../../../../features/tasks/taskKinds";
import { STATE_COLOR, stateLabel } from "../../../../features/tasks/taskLabels";
import { TaskDetailPopover } from "../../molecules/TaskDetailPopover/TaskDetailPopover";
import styles from "./TaskIndicator.module.css";

interface TaskIndicatorProps {
  taskId: string;
  size?: "sm" | "md";
}

/**
 * Inline indicator: spinning ring (running), dot (pending/cancelling), or icon (failed/cancelled).
 * Progress % is shown in the TaskDetailPopover, not inline — the ring always spins when running.
 */
export function TaskIndicator({ taskId, size = "md" }: TaskIndicatorProps) {
  const { t } = useTranslation();
  const task = useSelector(selectTask(taskId));
  const [anchorEl, setAnchorEl] = React.useState<HTMLButtonElement | null>(null);

  if (!task) return null;

  const fg = STATE_COLOR[task.state] ?? "var(--on-surface-retreat)";
  // While running, show the kind ("Processing", "Migration", …); otherwise the state.
  const label = task.state === "running" ? t(getKindMeta(task.kind).labelKey) : stateLabel(task.state, t);
  const ringSize = size === "sm" ? 14 : 16;

  return (
    <>
      <button
        className={styles.trigger}
        onClick={(e) => setAnchorEl(e.currentTarget)}
        aria-label={t("rework.tasks.indicator.details", { label })}
        type="button"
      >
        {task.state === "failed" ? (
          <WarningIcon color={fg} size={ringSize} />
        ) : task.state === "cancelled" ? (
          <BanIcon color={fg} size={ringSize} />
        ) : task.state === "running" ? (
          <SpinningRing color={fg} size={ringSize} />
        ) : (
          <span className={styles.dot} data-state={task.state} style={{ "--dot-color": fg } as React.CSSProperties} />
        )}

        <span className={styles.label} data-size={size} style={{ color: fg }}>
          {label}
        </span>
      </button>

      <TaskDetailPopover
        taskId={taskId}
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={() => setAnchorEl(null)}
      />
    </>
  );
}

// ── Icons ─────────────────────────────────────────────────────────────────────

interface SvgProps {
  color: string;
  size: number;
}

function WarningIcon({ color, size }: SvgProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ flexShrink: 0 }}
      aria-hidden="true"
    >
      <path d="M10.363 3.591l-8.106 13.534a1.914 1.914 0 0 0 1.636 2.871h16.214a1.914 1.914 0 0 0 1.636 -2.871l-8.106 -13.534a1.914 1.914 0 0 0 -3.274 0z" />
      <path d="M12 9v4" />
      <path d="M12 17l.01 0" />
    </svg>
  );
}

function BanIcon({ color, size }: SvgProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ flexShrink: 0 }}
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" />
      <line x1="5.7" y1="5.7" x2="18.3" y2="18.3" />
    </svg>
  );
}

function SpinningRing({ color, size }: SvgProps) {
  const strokeWidth = 2;
  const r = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * r;
  const cx = size / 2;

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className={styles.spinningRing}
      style={{ flexShrink: 0 }}
    >
      <circle cx={cx} cy={cx} r={r} fill="none" stroke="currentColor" strokeWidth={strokeWidth} opacity={0.18} />
      <circle
        cx={cx}
        cy={cx}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={`${circumference * 0.75} ${circumference * 0.25}`}
      />
    </svg>
  );
}
