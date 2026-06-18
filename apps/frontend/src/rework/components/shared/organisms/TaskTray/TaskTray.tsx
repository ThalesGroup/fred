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

import { useRef, useState, useCallback, useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useClickOutside } from "../../hooks/UseClickOutside";
import { TaskCard } from "../../molecules/TaskCard/TaskCard";
import { Portal } from "../../utils/Portal";
import {
  EVICTION_DELAY_MS,
  failuresAcknowledged,
  selectUnacknowledgedFailures,
  selectVisibleTasks,
  taskEvicted,
  trayClockTicked,
} from "../../../../features/tasks/taskSlice";
import { TaskTrayTrigger } from "./TaskTrayTrigger";
import styles from "./TaskTray.module.css";

export function TaskTray() {
  const dispatch = useDispatch();
  const [isOpen, setIsOpen] = useState(false);
  const [panelPos, setPanelPos] = useState<{ bottom: number; left: number } | null>(null);

  const visibleTasks = useSelector(selectVisibleTasks);
  const unacknowledgedFailures = useSelector(selectUnacknowledgedFailures);

  const panelRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLDivElement>(null);

  const close = useCallback(() => setIsOpen(false), []);
  useClickOutside(panelRef, close, triggerRef);

  const handleToggle = useCallback(() => {
    if (!isOpen && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      setPanelPos({
        bottom: window.innerHeight - rect.top + 8,
        left: Math.min(rect.left, window.innerWidth - 296),
      });
    }
    setIsOpen((v) => !v);
  }, [isOpen]);

  // Acknowledge failures when panel opens and failures are visible
  useEffect(() => {
    if (isOpen && unacknowledgedFailures > 0) {
      dispatch(failuresAcknowledged());
    }
  }, [isOpen, unacknowledgedFailures, dispatch]);

  // Age terminal tasks out of the tray. `selectVisibleTasks` filters by elapsed
  // wall-clock, which no store change reflects on its own, so without these timers a
  // finished task would linger in the tray until some unrelated task action happened
  // to recompute the selector. Two terminal shapes, two mechanisms:
  //   • failed/cancelled (acknowledged): removed from the store via `taskEvicted`.
  //   • succeeded: kept in the store for admin history, only hidden from the tray —
  //     a `trayClockTicked` forces `selectVisibleTasks` to recompute and drop it.
  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = [];
    const now = Date.now();
    for (const vm of visibleTasks) {
      if (vm.state === "succeeded" && vm.terminalAt !== null) {
        const remaining = vm.terminalAt + EVICTION_DELAY_MS - now;
        if (remaining <= 0) {
          dispatch(trayClockTicked());
        } else {
          timers.push(setTimeout(() => dispatch(trayClockTicked()), remaining));
        }
      } else if ((vm.state === "failed" || vm.state === "cancelled") && vm.acknowledgedAt !== null) {
        const remaining = vm.acknowledgedAt + EVICTION_DELAY_MS - now;
        if (remaining <= 0) {
          dispatch(taskEvicted(vm.taskId));
        } else {
          timers.push(setTimeout(() => dispatch(taskEvicted(vm.taskId)), remaining));
        }
      }
    }
    return () => timers.forEach(clearTimeout);
  }, [visibleTasks, dispatch]);

  const runningCount = visibleTasks.filter((vm) => vm.state === "running").length;
  const failedCount = visibleTasks.filter((vm) => vm.state === "failed" || vm.state === "cancelled").length;

  const summaryParts: string[] = [];
  if (runningCount > 0) summaryParts.push(`${runningCount} running`);
  if (failedCount > 0) summaryParts.push(`${failedCount} failed`);

  return (
    <div className={styles.container}>
      <div ref={triggerRef}>
        <TaskTrayTrigger isOpen={isOpen} onClick={handleToggle} />
      </div>

      {isOpen && panelPos && (
        <Portal id="task-tray-panel">
          <div
            ref={panelRef}
            className={styles.panel}
            style={{ bottom: panelPos.bottom, left: panelPos.left }}
            role="dialog"
            aria-label="Recent tasks"
          >
            <div className={styles.panelHeader}>
              <span className={styles.panelTitle}>Recent tasks</span>
              {summaryParts.length > 0 && (
                <span className={styles.summaryChip} data-has-failures={failedCount > 0}>
                  {summaryParts.join(" · ")}
                </span>
              )}
            </div>

            <div className={styles.taskList}>
              {visibleTasks.length === 0 ? (
                <div className={styles.emptyState}>No recent tasks</div>
              ) : (
                visibleTasks.map((task) => <TaskCard key={task.taskId} task={task} />)
              )}
            </div>
          </div>
        </Portal>
      )}
    </div>
  );
}
