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
import { createPortal } from "react-dom";
import { useSelector } from "react-redux";
import { selectTask } from "../../../../features/tasks/taskSlice";
import { TaskProgressBar } from "../../atoms/TaskProgressBar/TaskProgressBar";
import { TaskStateBadge } from "../../atoms/TaskStateBadge/TaskStateBadge";
import styles from "./TaskDetailPopover.module.css";

interface TaskDetailPopoverProps {
  taskId: string;
  anchorEl: HTMLElement | null;
  open: boolean;
  onClose: () => void;
}

export function TaskDetailPopover({ taskId, anchorEl, open, onClose }: TaskDetailPopoverProps) {
  const task = useSelector(selectTask(taskId));
  const popoverRef = React.useRef<HTMLDivElement>(null);

  // Position the popover below the anchor element
  const [pos, setPos] = React.useState<{ top: number; left: number } | null>(null);

  React.useLayoutEffect(() => {
    if (!open || !anchorEl) {
      setPos(null);
      return;
    }
    const rect = anchorEl.getBoundingClientRect();
    const POPOVER_WIDTH = 280;
    const MARGIN = 8;
    const top = rect.bottom + 6;
    // Prefer left-aligned; flip to right-aligned when it would overflow the viewport.
    const left =
      rect.left + POPOVER_WIDTH + MARGIN > window.innerWidth ? Math.max(MARGIN, rect.right - POPOVER_WIDTH) : rect.left;
    setPos({ top, left });
  }, [open, anchorEl]);

  // Close when clicking outside
  React.useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node) && e.target !== anchorEl) {
        onClose();
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open, anchorEl, onClose]);

  // Close on Escape
  React.useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open || !task || !pos) return null;

  const progressPct = task.progress !== null ? `${Math.round(task.progress * 100)}%` : null;
  const elapsedLabel = relativeTime(task.registeredAt);
  const targetLabel = task.target?.label ?? task.taskId;

  return createPortal(
    <div
      ref={popoverRef}
      className={styles.popover}
      role="dialog"
      aria-modal="false"
      aria-label={`Détails — ${targetLabel}`}
      style={{ top: pos.top, left: pos.left }}
    >
      {/* Header */}
      <div className={styles.header}>
        <span className={styles.title} title={targetLabel}>
          {targetLabel}
        </span>
        <button className={styles.closeBtn} onClick={onClose} aria-label="Fermer" type="button">
          ✕
        </button>
      </div>

      {/* State + progress % */}
      <div className={styles.stateRow}>
        <TaskStateBadge state={task.state} size="sm" />
        {progressPct && <span className={styles.pct}>{progressPct}</span>}
      </div>

      {/* Progress bar */}
      <div className={styles.barWrap}>
        <TaskProgressBar state={task.state} progress={task.progress} />
      </div>

      {/* Step + elapsed */}
      {task.step && (
        <div className={styles.stepRow}>
          <span className={styles.step}>{task.step}</span>
          <span className={styles.elapsed}>· {elapsedLabel}</span>
        </div>
      )}

      {/* Error */}
      {task.error && (
        <div className={styles.errorRow}>
          <span className={styles.errorText}>{task.error}</span>
        </div>
      )}
    </div>,
    document.body,
  );
}

function relativeTime(ms: number, now = Date.now()): string {
  const diffS = Math.floor((now - ms) / 1000);
  if (diffS < 60) return "démarré à l'instant";
  const diffM = Math.floor(diffS / 60);
  if (diffM < 60) return `démarré il y a ${diffM} min`;
  const diffH = Math.floor(diffM / 60);
  return `démarré il y a ${diffH}h`;
}
