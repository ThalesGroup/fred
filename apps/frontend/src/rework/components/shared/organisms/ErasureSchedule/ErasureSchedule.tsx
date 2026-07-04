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

// Erasure schedule (CTRLP-12). Makes the deferred-delete pipeline visible to the
// people accountable for it: platform admins (scope "platform") and team admins
// (scope "team") must see not only erasures in flight but everything *scheduled*
// — which conversation, and when it is due to be provably erased.
//
// Data comes from the standard task surface (`GET /tasks?kind=erasure`, already
// scoped platform vs team server-side), and rendering reuses the exact same task
// atoms as ingestion (`TaskStateBadge`, `TaskProgressBar`). Freshness reuses the
// same shared hook (`useRefetchOnTaskSuccess`) so a completed erasure updates
// live; polling covers the scheduled→running transitions the client is not
// subscribed to over SSE.

import { useTranslation } from "react-i18next";
import { TaskStateBadge } from "@shared/atoms/TaskStateBadge/TaskStateBadge";
import { TaskProgressBar } from "@shared/atoms/TaskProgressBar/TaskProgressBar";
import { dueRelative, relativeTime } from "@rework/features/tasks/taskLabels";
import { useRefetchOnTaskSuccess } from "@rework/features/tasks/useRefetchOnTaskSuccess";
import {
  useListTasksControlPlaneV1TasksGetQuery,
  type TaskSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./ErasureSchedule.module.css";

interface ErasureScheduleProps {
  /** Server-side scope. "platform" needs can_manage_platform; "team" needs
   *  CAN_READ_MEMBERS on `teamId`. The backend enforces it either way. */
  scope: "platform" | "team";
  teamId?: string;
}

// Erasures due days out change slowly, but a running one finishes in seconds;
// poll often enough to catch the scheduled→running→done transitions the client
// is not SSE-subscribed to, without hammering the admin surface.
const ERASURE_POLL_MS = 30_000;

/** Soonest-due first; tasks without a due date sort last. */
function byDueAsc(a: TaskSummary, b: TaskSummary): number {
  if (!a.scheduled_for) return b.scheduled_for ? 1 : 0;
  if (!b.scheduled_for) return -1;
  return a.scheduled_for.localeCompare(b.scheduled_for);
}

export default function ErasureSchedule({ scope, teamId }: ErasureScheduleProps) {
  const { t, i18n } = useTranslation();

  const { data, isLoading, isError, refetch } = useListTasksControlPlaneV1TasksGetQuery(
    { scope, teamId: teamId ?? undefined, kind: "erasure" },
    { pollingInterval: ERASURE_POLL_MS },
  );

  // Instant refresh when an erasure the client *is* watching completes; polling
  // still covers everything the client never subscribed to.
  useRefetchOnTaskSuccess("conversation", () => void refetch());

  const tasks = data?.tasks ?? [];
  const scheduled = tasks.filter((task) => task.state === "pending").sort(byDueAsc);
  const running = tasks.filter((task) => task.state === "running" || task.state === "cancelling");
  const completed = tasks
    .filter((task) => task.state === "succeeded" || task.state === "failed" || task.state === "cancelled")
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));

  const label = (task: TaskSummary) => task.target?.label ?? task.target?.id ?? task.task_id;

  const absoluteDue = (iso: string) =>
    new Date(iso).toLocaleString(i18n.language, { dateStyle: "medium", timeStyle: "short" });

  const row = (task: TaskSummary, meta: React.ReactNode) => (
    <li key={task.task_id} className={styles.row}>
      <span className={styles.name} title={label(task)}>
        {label(task)}
      </span>
      <TaskStateBadge state={task.state} showLabel={false} size="sm" />
      <span className={styles.meta}>{meta}</span>
    </li>
  );

  const group = (titleKey: string, count: number, children: React.ReactNode) => (
    <div className={styles.group}>
      <div className={styles.groupHead}>
        <span className={styles.groupTitle}>{t(titleKey)}</span>
        <span className={styles.groupCount}>{count}</span>
      </div>
      <ul className={styles.list}>{children}</ul>
    </div>
  );

  return (
    <section className={styles.container}>
      <header className={styles.head}>
        <h3 className={styles.title}>{t("rework.erasureSchedule.title")}</h3>
        <span className={styles.subtitle}>{t("rework.erasureSchedule.subtitle")}</span>
      </header>

      {isLoading && <div className={styles.hint}>{t("rework.erasureSchedule.loading")}</div>}
      {isError && <div className={styles.error}>{t("rework.erasureSchedule.loadError")}</div>}
      {!isLoading && !isError && tasks.length === 0 && (
        <div className={styles.empty}>{t("rework.erasureSchedule.empty")}</div>
      )}

      {scheduled.length > 0 &&
        group(
          "rework.erasureSchedule.scheduled",
          scheduled.length,
          scheduled.map((task) =>
            row(
              task,
              task.scheduled_for ? (
                <>
                  <span className={styles.due}>
                    {t("rework.erasureSchedule.dueOn", { when: absoluteDue(task.scheduled_for) })}
                  </span>
                  <span className={styles.dueRel}>{dueRelative(new Date(task.scheduled_for).getTime(), t)}</span>
                </>
              ) : (
                t("rework.erasureSchedule.dueUnknown")
              ),
            ),
          ),
        )}

      {running.length > 0 &&
        group(
          "rework.erasureSchedule.inProgress",
          running.length,
          running.map((task) =>
            row(
              task,
              <span className={styles.progress}>
                <TaskProgressBar state={task.state} progress={task.progress ?? null} />
              </span>,
            ),
          ),
        )}

      {completed.length > 0 &&
        group(
          "rework.erasureSchedule.completed",
          completed.length,
          completed.map((task) =>
            row(
              task,
              t("rework.erasureSchedule.erasedOn", { when: relativeTime(new Date(task.updated_at).getTime(), t) }),
            ),
          ),
        )}
    </section>
  );
}
