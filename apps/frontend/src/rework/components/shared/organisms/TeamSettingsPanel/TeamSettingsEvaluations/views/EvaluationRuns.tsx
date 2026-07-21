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

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { IndicatorDot } from "@shared/atoms/IndicatorDot/IndicatorDot";
import { TaskStateBadge } from "@shared/atoms/TaskStateBadge/TaskStateBadge";
import ProgressBar from "@shared/atoms/ProgressBar/ProgressBar";
import { Breadcrumb } from "@shared/molecules/Breadcrumb/Breadcrumb";
import KpiStatCard from "@shared/molecules/KpiStatCard/KpiStatCard";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { FieldBlock, StatusPill, operationalToTaskState, scoreTone, verdictTone } from "./EvaluationShared";
import {
  useDeleteRunEvaluationV1RunsRunIdDeleteMutation,
  useListRunCasesEvaluationV1RunsRunIdCasesGetQuery,
  useListRunsEvaluationV1EvaluationsEvaluationIdRunsGetQuery,
  useStartRunEvaluationV1EvaluationsEvaluationIdRunsPostMutation,
  type EvaluationCaseResponse,
  type EvaluationRun,
} from "../../../../../../../slices/evaluation/evaluationOpenApi";
import styles from "./EvaluationRuns.module.css";

interface EvaluationRunsProps {
  teamId: string;
  evaluationId: string;
  evaluationName: string;
  onBack: () => void;
  onNewRun: () => void;
  onOpenRun: (runId: string, selectedCaseId?: string) => void;
}

function targetLabel(target: EvaluationRun["target"], t: (k: string, o?: Record<string, unknown>) => string): string {
  if (target.kind === "managed_instance") {
    return t("rework.evaluation.runs.targetInstance", {
      id: target.agent_instance_id.slice(0, 8),
    });
  }
  return target.agent_id;
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

  const { data, isLoading, isError, refetch } = useListRunsEvaluationV1EvaluationsEvaluationIdRunsGetQuery(
    { evaluationId },
    { skip: !evaluationId, pollingInterval: 10_000 },
  );
  const [deleteRun, { isLoading: isDeleting }] = useDeleteRunEvaluationV1RunsRunIdDeleteMutation();
  const [startRun, { isLoading: isRerunning }] = useStartRunEvaluationV1EvaluationsEvaluationIdRunsPostMutation();

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

  const runs = data ?? [];
  const running = runs.filter((run) => run.operational_state === "running").length;
  // operationalToTaskState is the canonical mapper (it also treats "succeeded"
  // as terminal-success, matching the backend's own documented either/or) —
  // reuse it instead of comparing the raw string, so this count can't silently
  // drop to 0 if the backend ever reports "succeeded" instead of "completed".
  const completed = runs.filter((run) => operationalToTaskState(run.operational_state) === "succeeded").length;
  const totalCases = runs.reduce((sum, run) => sum + run.completed_cases, 0);
  const criticalErrors = runs.reduce((sum, run) => sum + run.execution_error_cases, 0);

  // Most recent run, sorted defensively — do not assume the API already
  // orders by recency. Only a "managed_instance" target can be one-click
  // rerun (see StartRunRequest); anything else falls back to "New run…".
  const mostRecentRun = useMemo(
    () => [...runs].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0] ?? null,
    [runs],
  );
  const rerunManagedTarget = mostRecentRun?.target.kind === "managed_instance" ? mostRecentRun.target : null;
  const rerunTargetLabel = mostRecentRun ? targetLabel(mostRecentRun.target, t) : "";

  const handleRerun = async () => {
    if (!rerunManagedTarget) return;
    try {
      const result = await startRun({
        evaluationId,
        startRunRequest: {
          team_id: teamId,
          target: { kind: "managed_instance", agent_instance_id: rerunManagedTarget.agent_instance_id },
          // The previous run's metric selection isn't exposed by the read API (only
          // team_id/target are reused today) — default to the historical baseline
          // metric until rerun is extended to carry the original choice forward.
          metrics: ["answer_relevancy"],
        },
      }).unwrap();
      onOpenRun(result.run_id);
    } catch (e) {
      const detail = (e as { data?: { detail?: unknown } })?.data?.detail;
      showError({
        summary: typeof detail === "string" ? detail : t("rework.evaluation.runCreate.error"),
      });
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
            <Button color="on-surface" variant="outlined" size="medium" onClick={onNewRun}>
              {t("rework.evaluation.runs.newRun")}
            </Button>
            {rerunManagedTarget && (
              <Button color="primary" variant="filled" size="medium" disabled={isRerunning} onClick={handleRerun}>
                {isRerunning
                  ? t("rework.evaluation.runCreate.starting")
                  : t("rework.evaluation.runs.rerun", { target: rerunTargetLabel })}
              </Button>
            )}
          </div>
          {rerunManagedTarget && (
            <p className={styles.rerunHint}>
              {t("rework.evaluation.runs.rerunHint", {
                target: rerunTargetLabel,
                model: rerunManagedTarget.agent_instance_id,
              })}
            </p>
          )}
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

      {!isLoading && runs.length === 0 && (
        <ServiceNotice icon="reviews" title={t("rework.evaluation.runs.empty")} centered />
      )}

      {!isLoading && runs.length > 0 && (
        <div className={styles.table} role="table">
          <div className={`${styles.row} ${styles.headerRow}`} role="row">
            <span>{t("rework.evaluation.runs.col.run")}</span>
            <span>{t("rework.evaluation.runs.col.target")}</span>
            <span>{t("rework.evaluation.runs.col.state")}</span>
            <span>{t("rework.evaluation.runs.col.verdict")}</span>
            <span>{t("rework.evaluation.runs.col.progress")}</span>
            <span>{t("rework.evaluation.runs.col.scores")}</span>
            <span />
          </div>

          {runs.map((run) => {
            const isRunning = run.operational_state === "running";
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
                <span className={styles.mono}>{targetLabel(run.target, t)}</span>
                <span>
                  <TaskStateBadge state={operationalToTaskState(run.operational_state)} />
                </span>
                <span>
                  <StatusPill label={run.verdict} tone={verdictTone(run.verdict)} />
                </span>
                <div className={styles.progressCell}>
                  <span className={styles.muted}>
                    {run.completed_cases} / {run.total_cases}
                  </span>
                  <ProgressBar theme="secondary" current={run.completed_cases} max={run.total_cases || 1} />
                </div>
                <div className={styles.scoresCell}>
                  <div className={styles.scoreLine}>
                    <span className={styles.muted}>{run.profile}</span>
                    <StatusPill label={run.judge_profile_id} tone={scoreTone(run.verdict === "passed" ? 100 : 50)} />
                  </div>
                </div>
                <div className={styles.actionsCell} onClick={(e) => e.stopPropagation()}>
                  <Button color="on-surface" variant="outlined" size="small" onClick={() => onOpenRun(run.run_id)}>
                    {t("rework.evaluation.runs.detail")}
                  </Button>
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
