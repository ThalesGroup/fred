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

// The one shared task/activity surface (OPS-04 §3.4). Rendered identically for
// platform admins (scope "platform") and team admins (scope "team"): the whole
// worker-action lifecycle — what is *scheduled* (with due dates), running, and
// completed — for every task kind (erasure, migration, ingestion, …). It is NOT
// per-feature; a kind is a filter, never a separate widget. Erasure previously
// had its own `ErasureSchedule`; this generalises it so both admin levels see the
// exact same view.
//
// Data comes from the standard task surface (`GET /tasks`, already scoped
// platform vs team server-side); pass `kind` to narrow it. Rendering reuses the
// shared task atoms (`TaskStateBadge`, `TaskProgressBar`); polling covers the
// scheduled→running→done transitions the client is not SSE-subscribed to.

import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { TaskStateBadge } from "@shared/atoms/TaskStateBadge/TaskStateBadge";
import { TaskProgressBar } from "@shared/atoms/TaskProgressBar/TaskProgressBar";
import Disclosure from "@shared/atoms/Disclosure/Disclosure";
import { dueRelative, relativeTime } from "@rework/features/tasks/taskLabels";
import {
  useListTasksControlPlaneV1TasksGetQuery,
  type MigrationDetail,
  type MigrationResult,
  type TaskSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./TaskActivity.module.css";

// Principal counters shown in the migration result disclosure, in display
// order. Zero-valued counters are omitted (kept to the counters that
// actually happened, same filtering spirit as the backend's own step
// summary string in `importer.py::run_import`, applied independently here
// for display — not a shared implementation). Includes every `*_skipped`
// counter and `users_processed` — a non-zero skip count is exactly the kind
// of partial-reconciliation signal this disclosure exists to surface, so it
// must never be silently dropped from view.
const MIGRATION_COUNTER_KEYS = [
  "identities_created",
  "users_processed",
  "teams_imported",
  "teams_provisioned",
  "teams_skipped",
  "team_roles_granted",
  "team_roles_skipped",
  "platform_roles_granted",
  "agents_imported",
  "agents_skipped",
  "agents_gap",
  "tags_imported",
  "tags_skipped",
  "docs_imported",
  "docs_skipped",
] as const satisfies readonly (keyof MigrationResult)[];

/** Narrow a generic `TaskSummary.detail` to `MigrationDetail` — only valid
 *  when `task.kind === "migration"`; the field carries a different shape per
 *  kind, distinguished by the sibling `kind`, same pattern as `TaskEvent`. */
function migrationDetail(task: TaskSummary): MigrationDetail | null {
  if (task.kind !== "migration" || task.detail == null) return null;
  return task.detail as MigrationDetail;
}

/** The structured outcome is only present on the terminal event; intermediate
 *  progress details never carry it. */
function migrationResult(task: TaskSummary): MigrationResult | null {
  return migrationDetail(task)?.result ?? null;
}

/** A `succeeded` migration with at least one warning is a partial
 *  reconciliation — it must never read as a silent, unqualified success. */
function hasMigrationWarnings(task: TaskSummary): boolean {
  const result = migrationResult(task);
  return !!result && (result.warnings?.length ?? 0) > 0;
}

function MigrationResultDetails({ result, t }: { result: MigrationResult; t: TFunction }) {
  const warnings = result.warnings ?? [];
  const counters = MIGRATION_COUNTER_KEYS.map((key) => [key, result[key]] as const).filter(
    ([, value]) => typeof value === "number" && value > 0,
  );

  return (
    // Warnings default the disclosure open — a partial reconciliation must be
    // seen without an extra click, not hidden behind a collapsed summary that
    // would itself read as "nothing to see here".
    <Disclosure title={t("rework.taskActivity.migration.detailsTitle")} defaultOpen={warnings.length > 0}>
      {counters.length > 0 && (
        <dl className={styles.counterList}>
          {counters.map(([key, value]) => (
            <div key={key} className={styles.counterRow}>
              <dt className={styles.counterLabel}>{t(`rework.taskActivity.migration.counter.${key}`)}</dt>
              <dd className={styles.counterValue}>{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {warnings.length > 0 && (
        <div className={styles.warningsBlock}>
          <span className={styles.warningsTitle}>
            {t("rework.taskActivity.migration.warningsTitle", { count: warnings.length })}
          </span>
          <ul className={styles.warningsList}>
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
    </Disclosure>
  );
}

interface TaskActivityProps {
  /** Server-side scope. "platform" needs can_manage_platform; "team" needs
   *  CAN_READ_MEMBERS on `teamId`. The backend enforces it either way. */
  scope: "platform" | "team";
  teamId?: string;
  /** Optional kind filter (e.g. "erasure"). Omit to show every task kind. */
  kind?: string;
}

// Scheduled work can be days out, but a running task finishes in seconds; poll
// often enough to catch the scheduled→running→done transitions the client is not
// SSE-subscribed to, without hammering the admin surface.
const ACTIVITY_POLL_MS = 30_000;

/** Soonest-due first; tasks without a due date sort last. */
function byDueAsc(a: TaskSummary, b: TaskSummary): number {
  if (!a.scheduled_for) return b.scheduled_for ? 1 : 0;
  if (!b.scheduled_for) return -1;
  return a.scheduled_for.localeCompare(b.scheduled_for);
}

export default function TaskActivity({ scope, teamId, kind }: TaskActivityProps) {
  const { t, i18n } = useTranslation();

  const { data, isLoading, isError } = useListTasksControlPlaneV1TasksGetQuery(
    { scope, teamId: teamId ?? undefined, kind },
    { pollingInterval: ACTIVITY_POLL_MS },
  );

  const tasks = data?.tasks ?? [];
  const scheduled = tasks.filter((task) => task.state === "pending").sort(byDueAsc);
  const running = tasks.filter((task) => task.state === "running" || task.state === "cancelling");
  const completed = tasks
    .filter((task) => task.state === "succeeded" || task.state === "failed" || task.state === "cancelled")
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));

  const label = (task: TaskSummary) => task.target?.label ?? task.target?.id ?? task.task_id;

  const absoluteDue = (iso: string) =>
    new Date(iso).toLocaleString(i18n.language, { dateStyle: "medium", timeStyle: "short" });

  // A completed task is NOT always "done": failed/cancelled outcomes must say so,
  // never read as success. The badge also shows its label here so the terminal
  // state is spelled out, not just a dot colour.
  const completedText = (task: TaskSummary) => {
    const when = relativeTime(new Date(task.updated_at).getTime(), t);
    if (task.state === "failed") return t("rework.taskActivity.failedOn", { when });
    if (task.state === "cancelled") return t("rework.taskActivity.cancelledOn", { when });
    return t("rework.taskActivity.completedOn", { when });
  };

  const row = (task: TaskSummary, meta: React.ReactNode, showBadgeLabel = false) => {
    const result = migrationResult(task);
    const withWarnings = hasMigrationWarnings(task);
    return (
      <li key={task.task_id} className={styles.row}>
        <div className={styles.rowMain}>
          <span className={styles.name} title={label(task)}>
            {label(task)}
          </span>
          <span className={styles.stateCell}>
            <TaskStateBadge state={task.state} showLabel={showBadgeLabel} size="sm" />
            {withWarnings && (
              <span className={styles.warningFlag} title={t("rework.taskActivity.withWarningsHint")}>
                {t("rework.taskActivity.withWarnings")}
              </span>
            )}
          </span>
          <span className={styles.meta}>{meta}</span>
        </div>
        {/* A failed task must show *why*, not just that it failed — never rendered
            alongside a success reading, and never for a task that has no error. */}
        {task.state === "failed" && task.error && <p className={styles.rowError}>{task.error}</p>}
        {result && (
          <div className={styles.rowDisclosure}>
            <MigrationResultDetails result={result} t={t} />
          </div>
        )}
      </li>
    );
  };

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
        <h3 className={styles.title}>{t("rework.taskActivity.title")}</h3>
        <span className={styles.subtitle}>{t("rework.taskActivity.subtitle")}</span>
      </header>

      {isLoading && <div className={styles.hint}>{t("rework.taskActivity.loading")}</div>}
      {isError && <div className={styles.error}>{t("rework.taskActivity.loadError")}</div>}
      {!isLoading && !isError && tasks.length === 0 && (
        <div className={styles.empty}>{t("rework.taskActivity.empty")}</div>
      )}

      {scheduled.length > 0 &&
        group(
          "rework.taskActivity.scheduled",
          scheduled.length,
          scheduled.map((task) =>
            row(
              task,
              task.scheduled_for ? (
                <>
                  <span className={styles.due}>
                    {t("rework.taskActivity.dueOn", { when: absoluteDue(task.scheduled_for) })}
                  </span>
                  <span className={styles.dueRel}>{dueRelative(new Date(task.scheduled_for).getTime(), t)}</span>
                </>
              ) : (
                t("rework.taskActivity.dueUnknown")
              ),
            ),
          ),
        )}

      {running.length > 0 &&
        group(
          "rework.taskActivity.inProgress",
          running.length,
          running.map((task) =>
            row(
              task,
              <span className={styles.progress}>
                <TaskProgressBar state={task.state} progress={task.progress ?? null} />
                {task.step === "stalled" && (
                  <span className={styles.stalled} title={t("rework.taskActivity.stalledHint")}>
                    {t("rework.taskActivity.stalled")}
                  </span>
                )}
              </span>,
            ),
          ),
        )}

      {completed.length > 0 &&
        group(
          "rework.taskActivity.completed",
          completed.length,
          completed.map((task) => row(task, completedText(task), true)),
        )}
    </section>
  );
}
