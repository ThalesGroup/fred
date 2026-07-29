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

// The Runs of ONE Evaluation — RFC AGENT-EVALUATION §8.5: this list is "grouped
// by evaluation", never a flat team-wide run list. The case set is shared by every
// row here, which is exactly what makes two Runs comparable: they differ only by
// the target/config each froze in its RunSnapshot.

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { IndicatorDot } from "@shared/atoms/IndicatorDot/IndicatorDot";
import { TaskStateBadge } from "@shared/atoms/TaskStateBadge/TaskStateBadge";
import ProgressBar from "@shared/atoms/ProgressBar/ProgressBar";
import Select from "@shared/molecules/Select/Select";
import type { OptionModel } from "@models/Option.model.ts";
import { Breadcrumb } from "@shared/molecules/Breadcrumb/Breadcrumb";
import KpiStatCard from "@shared/molecules/KpiStatCard/KpiStatCard";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { FieldBlock, StatusPill, operationalToTaskState, scoreTone, verdictTone } from "./EvaluationShared";
import { useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery } from "../../../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useDeleteRunEvaluationV1RunsRunIdDeleteMutation,
  useListRunCasesEvaluationV1RunsRunIdCasesGetQuery,
  useListRunsEvaluationV1EvaluationsEvaluationIdRunsGetQuery,
  useStartRunEvaluationV1EvaluationsEvaluationIdRunsPostMutation,
  type EvaluationCaseResponse,
  type EvaluationRun,
} from "../../../../../../../slices/evaluation/evaluationOpenApi";
import styles from "./EvaluationRuns.module.css";

// Server-side page size for the runs table. The backend caps limit at 200; this
// stays well under it and keeps the table scannable at scale.
const RUNS_PAGE_SIZE = 25;

type RunSortValue = "created_at:desc" | "created_at:asc";

interface EvaluationRunsProps {
  teamId: string;
  evaluationId: string;
  evaluationName: string;
  onBack: () => void;
  onNewRun: () => void;
  onOpenRun: (runId: string, selectedCaseId?: string) => void;
}

function buildAgentLabels(instances: Array<{ agent_instance_id: string; display_name: string }>): Map<string, string> {
  const counts = new Map<string, number>();
  for (const instance of instances) {
    counts.set(instance.display_name, (counts.get(instance.display_name) ?? 0) + 1);
  }
  return new Map(
    instances.map((instance) => {
      const duplicated = (counts.get(instance.display_name) ?? 0) > 1;
      const label = duplicated
        ? `${instance.display_name} · ${instance.agent_instance_id.slice(0, 6)}`
        : instance.display_name;
      return [instance.agent_instance_id, label];
    }),
  );
}

// ── Case drawer ────────────────────────────────────────────────────────────

function CaseDrawer({
  runId,
  open,
  onClose,
  onOpenCase,
}: {
  runId: string | null;
  open: boolean;
  onClose: () => void;
  onOpenCase: (caseId: string) => void;
}) {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useListRunCasesEvaluationV1RunsRunIdCasesGetQuery(
    { runId: runId ?? "", limit: 200 },
    { skip: !runId || !open },
  );
  const cases = data?.cases ?? [];

  return (
    <InlineDrawer open={open} onClose={onClose} title={t("rework.evaluation.runs.drawerTitle")} width="560px">
      <p className={styles.drawerHint}>{t("rework.evaluation.runs.drawerHint")}</p>

      {isLoading && <p className={styles.muted}>{t("common.loading")}</p>}
      {isError && <p className={styles.error}>{t("rework.evaluation.runs.casesError")}</p>}

      <div className={styles.caseList}>
        {cases.map((c) => (
          <CaseCard key={c.case_id} c={c} onClick={() => onOpenCase(c.case_id)} />
        ))}
        {!isLoading && !isError && cases.length === 0 && (
          <p className={styles.muted}>{t("rework.evaluation.runs.noCases")}</p>
        )}
      </div>
    </InlineDrawer>
  );
}

function CaseCard({ c, onClick }: { c: EvaluationCaseResponse; onClick: () => void }) {
  const { t } = useTranslation();
  return (
    <button type="button" className={styles.caseCard} onClick={onClick}>
      <div className={styles.caseHeader}>
        <span className={styles.mono}>{c.external_id ?? c.case_id.slice(0, 12)}</span>
        <div className={styles.caseHeaderRight}>
          <StatusPill label={c.verdict} tone={verdictTone(c.verdict)} />
          {c.metrics.length > 0 && (
            <span className={styles.muted}>
              {t("rework.evaluation.runs.metricsCount", { count: c.metrics.length })}
            </span>
          )}
        </div>
      </div>

      <FieldBlock label={t("rework.evaluation.runs.inputLabel")} value={c.input} />

      {c.execution_error && (
        <div className={styles.execError}>
          <span className={styles.execErrorTitle}>{t("rework.evaluation.runs.executionError")}</span>
          <span>{c.execution_error}</span>
        </div>
      )}

      {c.metrics.length > 0 && (
        <div className={styles.metricList}>
          {c.metrics.map((m) => (
            <div key={m.name} className={styles.metricRow}>
              <div className={styles.metricHead}>
                <span className={styles.muted}>{m.name.replace("Metric", "")}</span>
                <StatusPill
                  label={m.score != null ? `${(m.score * 100).toFixed(0)}%` : m.verdict}
                  tone={verdictTone(m.verdict)}
                />
              </div>
              {m.score != null && (
                <ProgressBar
                  theme={m.verdict === "passed" ? "success" : "error"}
                  current={Math.round(m.score * 100)}
                  max={100}
                />
              )}
            </div>
          ))}
        </div>
      )}

      <span className={styles.caseLink}>{t("rework.evaluation.runs.viewFullDetail")}</span>
    </button>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function EvaluationRuns({
  teamId,
  evaluationId,
  evaluationName,
  onBack,
  onNewRun,
  onOpenRun,
}: EvaluationRunsProps) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const [drawerRunId, setDrawerRunId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<EvaluationRun | null>(null);
  // Which run's rerun is currently in flight — per-run rather than a single global
  // flag, so relaunching one row doesn't disable every other row's Rerun button.
  const [reruningRunId, setReruningRunId] = useState<string | null>(null);

  const [sort, setSort] = useState<RunSortValue>("created_at:desc");
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    setOffset(0);
  }, [sort]);

  const { data, isLoading, isError, isFetching, refetch } = useListRunsEvaluationV1EvaluationsEvaluationIdRunsGetQuery(
    { evaluationId, sort, offset, limit: RUNS_PAGE_SIZE },
    { skip: !evaluationId, pollingInterval: 10_000 },
  );
  const { data: managedInstances = [] } = useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery(
    { teamId },
    { skip: !teamId },
  );
  const [deleteRun, { isLoading: isDeleting }] = useDeleteRunEvaluationV1RunsRunIdDeleteMutation();
  const [startRun] = useStartRunEvaluationV1EvaluationsEvaluationIdRunsPostMutation();

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    try {
      await deleteRun({ runId: deleteTarget.run_id }).unwrap();
      showSuccess({ summary: t("rework.evaluation.runs.deleteSuccess") });
      setDeleteTarget(null);
      refetch();
    } catch {
      showError({ summary: t("rework.evaluation.runs.deleteError") });
    }
  };

  // The list endpoint is now paginated: it returns { runs, total } rather than a
  // bare array. `total` is the full server-side count (not this page's length).
  const runs = data?.runs ?? [];
  const total = data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / RUNS_PAGE_SIZE));
  const currentPage = Math.floor(offset / RUNS_PAGE_SIZE) + 1;
  const running = runs.filter((run) => run.operational_state === "running").length;
  // operationalToTaskState is the canonical mapper (it also treats "succeeded"
  // as terminal-success, matching the backend's own documented either/or) —
  // reuse it instead of comparing the raw string, so this count can't silently
  // drop to 0 if the backend ever reports "succeeded" instead of "completed".
  const completed = runs.filter((run) => operationalToTaskState(run.operational_state) === "succeeded").length;
  const totalCases = runs.reduce((sum, run) => sum + run.completed_cases, 0);
  const criticalErrors = runs.reduce((sum, run) => sum + run.execution_error_cases, 0);
  const agentNameByInstanceId = buildAgentLabels(managedInstances);
  const sortOptions: OptionModel<RunSortValue>[] = [
    { value: "created_at:desc", key: "newest", label: t("rework.evaluation.controls.sort.newest") },
    { value: "created_at:asc", key: "oldest", label: t("rework.evaluation.controls.sort.oldest") },
  ];

  // Reruns any given run of this evaluation — not just the most recent one. Reuses
  // that run's own target and exact metric selection ("New run…" but without having
  // to re-pick the agent or the metrics).
  const handleRerunRun = async (run: EvaluationRun) => {
    if (run.target.kind !== "managed_instance") return;
    setReruningRunId(run.run_id);
    try {
      const result = await startRun({
        evaluationId,
        startRunRequest: {
          team_id: teamId,
          target: { kind: "managed_instance", agent_instance_id: run.target.agent_instance_id },
          // Fall back to the historical baseline only for a run predating this field
          // (empty list) — otherwise reproduce exactly what this run was scored on.
          metrics: run.metrics?.length ? run.metrics : ["answer_relevancy"],
          custom_metrics: run.custom_metrics ?? [],
        },
      }).unwrap();
      onOpenRun(result.run_id);
    } catch (e) {
      const detail = (e as { data?: { detail?: unknown } })?.data?.detail;
      showError({
        summary: typeof detail === "string" ? detail : t("rework.evaluation.runCreate.error"),
      });
    } finally {
      setReruningRunId(null);
    }
  };

  // Service unreachable → mirror the knowledge-flow "service not running" notice.
  if (isError) {
    return (
      <div className={styles.page}>
        <ServiceNotice
          icon="cloud_off"
          title={t("rework.serviceNotice.evaluationService.title")}
          description={t("rework.serviceNotice.evaluationService.description")}
          centered
        />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <Breadcrumb
        segments={[{ label: t("rework.evaluation.evaluations.title"), onClick: onBack }, { label: evaluationName }]}
      />

      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>{evaluationName}</h1>
          <p className={styles.subtitle}>{t("rework.evaluation.runs.description")}</p>
        </div>
        <div className={styles.headerActionsColumn}>
          <div className={styles.headerActions}>
            {/* Rerun lives per-row in the runs table (each run can be relaunched
                with its own target and metrics); the header only offers "New run". */}
            <Button color="on-surface" variant="outlined" size="medium" onClick={onNewRun}>
              {t("rework.evaluation.runs.newRun")}
            </Button>
          </div>
        </div>
      </div>

      <div className={styles.kpiRow}>
        <KpiStatCard
          label={t("rework.evaluation.runs.kpi.active")}
          value={running}
          isLoading={isLoading}
          isError={isError}
        />
        <KpiStatCard
          label={t("rework.evaluation.runs.kpi.completed")}
          value={completed}
          isLoading={isLoading}
          isError={isError}
        />
        <KpiStatCard
          label={t("rework.evaluation.runs.kpi.casesEvaluated")}
          value={totalCases}
          isLoading={isLoading}
          isError={isError}
        />
        <KpiStatCard
          label={t("rework.evaluation.runs.kpi.criticalFailures")}
          value={criticalErrors}
          isLoading={isLoading}
          isError={isError}
        />
      </div>

      <div className={styles.toolbar}>
        <div className={styles.toolbarSpacer} />
        <Select<RunSortValue>
          size="medium"
          options={sortOptions}
          value={sort}
          onChange={(value) => setSort(value)}
          label={t("rework.evaluation.controls.sortLabel")}
        />
      </div>

      {!isLoading && runs.length === 0 && (
        <ServiceNotice icon="reviews" title={t("rework.evaluation.runs.empty")} centered />
      )}

      {!isLoading && runs.length > 0 && (
        <div className={styles.table} role="table">
          <div className={`${styles.row} ${styles.headerRow}`} role="row">
            <div className={styles.nameHeaderCell}>{t("rework.evaluation.runs.col.run")}</div>
            <div className={styles.targetHeaderCell}>{t("rework.evaluation.runs.col.target")}</div>
            <div className={styles.stateHeaderCell}>{t("rework.evaluation.runs.col.state")}</div>
            <div className={styles.verdictHeaderCell}>{t("rework.evaluation.runs.col.verdict")}</div>
            <div className={styles.progressHeaderCell}>{t("rework.evaluation.runs.col.progress")}</div>
            <div className={styles.scoresHeaderCell}>{t("rework.evaluation.runs.col.judge")}</div>
            <div className={styles.actionsHeaderCell} />
          </div>
          {runs.map((run) => {
            const isRunning = run.operational_state === "running";
            const targetDisplayName =
              run.target.kind === "managed_instance"
                ? (agentNameByInstanceId.get(run.target.agent_instance_id) ?? t("rework.evaluation.runs.targetManaged"))
                : run.target.agent_id;
            const targetId =
              run.target.kind === "managed_instance" ? run.target.agent_instance_id.slice(0, 8) : run.target.agent_id;
            return (
              <div
                key={run.run_id}
                className={`${styles.row} ${styles.bodyRow} ${isRunning ? styles.rowRunning : ""}`}
                role="row"
                tabIndex={0}
                onClick={() => setDrawerRunId(run.run_id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") setDrawerRunId(run.run_id);
                }}
              >
                <div className={styles.nameCell}>
                  {isRunning && <IndicatorDot status="streaming" label={t("rework.evaluation.runs.col.state")} />}
                  <div>
                    <div className={styles.name}>
                      {t("rework.evaluation.runs.versionLabel", { version: run.snapshot.evaluation_version })}
                    </div>
                    <div className={styles.mono}>{run.run_id.slice(0, 12)}</div>
                  </div>
                </div>
                <div className={styles.targetCell}>
                  <span className={styles.targetName}>{targetDisplayName}</span>
                  <span className={styles.mono}>{targetId}</span>
                </div>
                <div className={styles.stateCell}>
                  <TaskStateBadge state={operationalToTaskState(run.operational_state)} />
                </div>
                <div className={styles.verdictCell}>
                  <StatusPill label={run.verdict} tone={verdictTone(run.verdict)} />
                </div>
                <div className={styles.progressCell}>
                  <span className={styles.muted}>
                    {run.completed_cases} / {run.total_cases}
                  </span>
                  <ProgressBar theme="secondary" current={run.completed_cases} max={run.total_cases || 1} />
                </div>
                <div className={styles.scoresCell}>
                  <StatusPill label={run.judge_profile_id} tone={scoreTone(run.verdict === "passed" ? 100 : 50)} />
                </div>
                <div className={styles.actionsCell} onClick={(e) => e.stopPropagation()}>
                  <Button color="on-surface" variant="outlined" size="small" onClick={() => onOpenRun(run.run_id)}>
                    {t("rework.evaluation.runs.detail")}
                  </Button>
                  {run.target.kind === "managed_instance" && (
                    <Button
                      color="on-surface"
                      variant="outlined"
                      size="small"
                      disabled={reruningRunId === run.run_id}
                      onClick={() => handleRerunRun(run)}
                    >
                      {reruningRunId === run.run_id
                        ? t("rework.evaluation.runCreate.starting")
                        : t("rework.evaluation.runs.rerunRow")}
                    </Button>
                  )}
                  <Button
                    color="error"
                    variant="outlined"
                    size="small"
                    disabled={isRunning}
                    onClick={() => setDeleteTarget(run)}
                  >
                    {t("common.delete")}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {!isLoading && total > RUNS_PAGE_SIZE && (
        <div className={styles.pagination}>
          <span>{t("rework.evaluation.controls.page", { current: currentPage, total: pageCount })}</span>
          <Button
            color="on-surface"
            variant="outlined"
            size="small"
            disabled={offset === 0 || isFetching}
            onClick={() => setOffset(Math.max(0, offset - RUNS_PAGE_SIZE))}
          >
            {t("rework.evaluation.controls.prev")}
          </Button>
          <Button
            color="on-surface"
            variant="outlined"
            size="small"
            disabled={currentPage >= pageCount || isFetching}
            onClick={() => setOffset(offset + RUNS_PAGE_SIZE)}
          >
            {t("rework.evaluation.controls.next")}
          </Button>
        </div>
      )}

      <CaseDrawer
        runId={drawerRunId}
        open={!!drawerRunId}
        onClose={() => setDrawerRunId(null)}
        onOpenCase={(caseId) => {
          const id = drawerRunId;
          setDrawerRunId(null);
          if (id) onOpenRun(id, caseId);
        }}
      />

      <ConfirmationDialog
        open={!!deleteTarget}
        title={t("rework.evaluation.runs.deleteTitle")}
        message={t("rework.evaluation.runs.deleteMessage", {
          id: deleteTarget?.run_id.slice(0, 12) ?? "",
        })}
        confirmLabel={isDeleting ? t("common.deleting") : t("common.delete")}
        cancelLabel={t("common.cancel")}
        criticalAction
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
