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

import { useDispatch, useSelector } from "react-redux";
import { useTranslation } from "react-i18next";
import {
  completedTasksCleared,
  failuresAcknowledged,
  selectAllTasks,
  selectUnacknowledgedFailures,
} from "../../../../features/tasks/taskSlice";
import { TaskCard } from "@shared/molecules/TaskCard/TaskCard";
import styles from "./TasksPage.module.css";

export default function TasksPage() {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const tasks = useSelector(selectAllTasks);
  const unacknowledgedFailures = useSelector(selectUnacknowledgedFailures);

  const activeTasks = tasks.filter((t) => t.state === "running" || t.state === "pending" || t.state === "cancelling");
  const terminalTasks = tasks.filter((t) => t.state === "succeeded" || t.state === "failed" || t.state === "cancelled");

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>{t("rework.tasks.page.title")}</h1>
        {unacknowledgedFailures > 0 && (
          <button className={styles.ackBtn} type="button" onClick={() => dispatch(failuresAcknowledged())}>
            {t("rework.tasks.page.ackFailures", { count: unacknowledgedFailures })}
          </button>
        )}
      </div>

      {tasks.length === 0 ? (
        <div className={styles.empty}>
          <span className={styles.emptyIcon}>✓</span>
          <span>{t("rework.tasks.page.empty")}</span>
        </div>
      ) : (
        <>
          {activeTasks.length > 0 && (
            <section className={styles.section}>
              <h2 className={styles.sectionTitle}>{t("rework.tasks.page.active")}</h2>
              <div className={styles.grid}>
                {activeTasks.map((task) => (
                  <TaskCard key={task.taskId} task={task} />
                ))}
              </div>
            </section>
          )}

          {terminalTasks.length > 0 && (
            <section className={styles.section}>
              <div className={styles.sectionHeader}>
                <h2 className={styles.sectionTitle}>
                  {t("rework.tasks.page.terminalCount", { count: terminalTasks.length })}
                </h2>
                <button className={styles.clearBtn} type="button" onClick={() => dispatch(completedTasksCleared())}>
                  {t("rework.tasks.page.clearCompleted")}
                </button>
              </div>
              <div className={styles.grid}>
                {terminalTasks.map((task) => (
                  <TaskCard key={task.taskId} task={task} />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
