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

import { useFocusHandoff } from "@shared/utils/useFocusHandoff";
import * as React from "react";
import { createPortal } from "react-dom";
import { useSelector } from "react-redux";
import { useTranslation } from "react-i18next";
import { selectTask } from "../../../../features/tasks/taskSlice";
import { useTaskAcknowledgement } from "../../../../features/tasks/useTaskAcknowledgement";
import { relativeTime, stepLabel, taskSupportDetails } from "../../../../features/tasks/taskLabels";
import { TaskProgressBar } from "../../atoms/TaskProgressBar/TaskProgressBar";
import { TaskStateBadge } from "../../atoms/TaskStateBadge/TaskStateBadge";
import Button from "@shared/atoms/Button/Button.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { useCopyConfirmation } from "../../../../core/hooks/useCopyConfirmation";
import { writeRichClipboard } from "../../../../utils/clipboardUtils";
import { viewportHeight, viewportWidth } from "@shared/utils/viewport.ts";
import styles from "./TaskDetailPopover.module.css";

interface TaskDetailPopoverProps {
  taskId: string;
  anchorEl: HTMLElement | null;
  open: boolean;
  onClose: () => void;
}

export function TaskDetailPopover({ taskId, anchorEl, open, onClose }: TaskDetailPopoverProps) {
  const { t } = useTranslation();
  const task = useSelector(selectTask(taskId));
  const popoverRef = React.useRef<HTMLDivElement>(null);

  // Below the anchor by default; above it, held by its bottom edge, when a low anchor leaves more room there.
  const [pos, setPos] = React.useState<{ top?: number; bottom?: number; left: number; maxHeight?: number } | null>(
    null,
  );

  React.useLayoutEffect(() => {
    if (!open || !anchorEl) {
      setPos(null);
      return;
    }
    const rect = anchorEl.getBoundingClientRect();
    const POPOVER_WIDTH = 280;
    const MARGIN = 8;
    const GAP = 6;
    // Matches .popover's max-height in TaskDetailPopover.module.css: the worst-case
    // height, so the box never needs measuring (content scrolls internally).
    const POPOVER_MAX_HEIGHT = Math.min(400, viewportHeight() - 2 * MARGIN);
    const spaceBelow = viewportHeight() - MARGIN - rect.bottom - GAP;
    const spaceAbove = rect.top - GAP - MARGIN;
    // Prefer left-aligned; flip to right-aligned when it would overflow the viewport.
    const left =
      rect.left + POPOVER_WIDTH + MARGIN > viewportWidth() ? Math.max(MARGIN, rect.right - POPOVER_WIDTH) : rect.left;
    if (spaceBelow < POPOVER_MAX_HEIGHT && spaceAbove > spaceBelow) {
      setPos({
        bottom: viewportHeight() - rect.top + GAP,
        left,
        maxHeight: Math.min(POPOVER_MAX_HEIGHT, spaceAbove),
      });
      return;
    }
    // Below, clamped upward when a long error would push its bottom edge off-screen.
    const top = Math.max(MARGIN, Math.min(rect.bottom + GAP, viewportHeight() - MARGIN - POPOVER_MAX_HEIGHT));
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

  useFocusHandoff(open && !!task && !!pos, popoverRef);

  if (!open || !task || !pos) return null;

  return createPortal(
    <div
      ref={popoverRef}
      className={styles.popover}
      role="dialog"
      aria-modal="false"
      aria-label={t("rework.tasks.popover.title", { label: task.target?.label ?? task.taskId })}
      style={{ top: pos.top, bottom: pos.bottom, left: pos.left, maxHeight: pos.maxHeight }}
    >
      <TaskDetailContent taskId={taskId} onClose={onClose} />
    </div>,
    document.body,
  );
}

interface TaskDetailContentProps {
  taskId: string;
  /** Without it the panel is passive (a hover panel): no close button, no acknowledgement. */
  onClose?: () => void;
}

/** The task's state, progress, step and error; the surface around it belongs to the caller. */
export function TaskDetailContent({ taskId, onClose }: TaskDetailContentProps) {
  const { t } = useTranslation();
  const task = useSelector(selectTask(taskId));
  const { acknowledge, isAcknowledging } = useTaskAcknowledgement();
  const { copied: errorCopied, confirmCopied: confirmErrorCopied } = useCopyConfirmation();

  if (!task) return null;

  const handleCopyError = () => {
    if (!task.error) return;
    writeRichClipboard("", taskSupportDetails(task, t)).then((ok) => {
      if (ok) confirmErrorCopied();
    });
  };

  const progressPct = task.progress !== null ? `${Math.round(task.progress * 100)}%` : null;
  const elapsedLabel = t("rework.tasks.popover.startedAgo", { time: relativeTime(task.registeredAt, t) });
  const targetLabel = task.target?.label ?? task.taskId;
  const needsAttention = (task.state === "failed" || task.state === "cancelled") && task.acknowledgedAt === null;

  return (
    <div className={styles.content}>
      <div className={styles.header}>
        <span className={styles.title} title={targetLabel}>
          {targetLabel}
        </span>
        {onClose && (
          <IconButton
            variant="icon"
            size="medium"
            icon={{ category: "outlined", type: "close" }}
            aria-label={t("rework.tasks.popover.close")}
            onClick={onClose}
          />
        )}
      </div>

      <div className={styles.stateRow}>
        <TaskStateBadge state={task.state} size="sm" />
        {progressPct && <span className={styles.meta}>{progressPct}</span>}
      </div>

      <TaskProgressBar state={task.state} progress={task.progress} />

      {task.step && (
        <div className={styles.stepRow}>
          <span className={styles.step}>{stepLabel(task, t)}</span>
          <span className={styles.meta}>· {elapsedLabel}</span>
        </div>
      )}

      {task.error && (
        <div className={styles.errorRow}>
          <span className={styles.errorText}>{task.error}</span>
          <IconButton
            variant="icon"
            size="medium"
            icon={{ category: "outlined", type: errorCopied ? "check_circle" : "content_copy" }}
            aria-label={errorCopied ? t("rework.tasks.popover.errorCopied") : t("rework.tasks.popover.copyError")}
            onClick={handleCopyError}
          />
        </div>
      )}

      {task.error && (
        <span className={styles.supportRef}>{t("rework.tasks.popover.supportReference", { id: task.taskId })}</span>
      )}

      {onClose && needsAttention && (
        <div className={styles.ackRow}>
          <Button
            color="on-surface"
            variant="text"
            size="small"
            onClick={async () => {
              if (await acknowledge(task.taskId, task.kind, task.localOnly)) onClose();
            }}
            disabled={isAcknowledging(task.taskId)}
          >
            {t("rework.tasks.popover.acknowledge")}
          </Button>
        </div>
      )}
    </div>
  );
}
