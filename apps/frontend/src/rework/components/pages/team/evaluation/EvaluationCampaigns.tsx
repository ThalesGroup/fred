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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { IndicatorDot } from "@shared/atoms/IndicatorDot/IndicatorDot";
import { TaskStateBadge } from "@shared/atoms/TaskStateBadge/TaskStateBadge";
import ProgressBar from "@shared/atoms/ProgressBar/ProgressBar";
import KpiStatCard from "@shared/molecules/KpiStatCard/KpiStatCard";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { FieldBlock, StatusPill, operationalToTaskState, scoreTone, verdictTone } from "./EvaluationShared";
import {
  useDeleteCampaignEvaluationV1CampaignsCampaignIdDeleteMutation,
  useListCampaignsEvaluationV1CampaignsGetQuery,
  useListCasesEvaluationV1CampaignsCampaignIdCasesGetQuery,
  type EvaluationCampaignResponse,
  type EvaluationCaseResponse,
} from "../../../../../slices/evaluation/evaluationOpenApi";
import styles from "./EvaluationCampaigns.module.css";

interface EvaluationCampaignsProps {
  teamId: string;
  onNewCampaign: () => void;
  onOpenCampaign: (campaignId: string, selectedCaseId?: string) => void;
}

function targetLabel(
  target: EvaluationCampaignResponse["target"],
  t: (k: string, o?: Record<string, unknown>) => string,
): string {
  if (target.kind === "managed_instance") {
    return t("rework.evaluation.campaigns.targetInstance", {
      id: target.agent_instance_id.slice(0, 8),
    });
  }
  return target.agent_id;
}

// ── Case drawer ────────────────────────────────────────────────────────────

function CaseDrawer({
  campaignId,
  open,
  onClose,
  onOpenCase,
}: {
  campaignId: string | null;
  open: boolean;
  onClose: () => void;
  onOpenCase: (caseId: string) => void;
}) {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useListCasesEvaluationV1CampaignsCampaignIdCasesGetQuery(
    { campaignId: campaignId ?? "", limit: 200 },
    { skip: !campaignId || !open },
  );
  const cases = data?.cases ?? [];

  return (
    <InlineDrawer open={open} onClose={onClose} title={t("rework.evaluation.campaigns.drawerTitle")} width="560px">
      <p className={styles.drawerHint}>{t("rework.evaluation.campaigns.drawerHint")}</p>

      {isLoading && <p className={styles.muted}>{t("common.loading")}</p>}
      {isError && <p className={styles.error}>{t("rework.evaluation.campaigns.casesError")}</p>}

      <div className={styles.caseList}>
        {cases.map((c) => (
          <CaseCard key={c.case_id} c={c} onClick={() => onOpenCase(c.case_id)} />
        ))}
        {!isLoading && !isError && cases.length === 0 && (
          <p className={styles.muted}>{t("rework.evaluation.campaigns.noCases")}</p>
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
              {t("rework.evaluation.campaigns.metricsCount", { count: c.metrics.length })}
            </span>
          )}
        </div>
      </div>

      <FieldBlock label={t("rework.evaluation.campaigns.inputLabel")} value={c.input} />

      {c.execution_error && (
        <div className={styles.execError}>
          <span className={styles.execErrorTitle}>{t("rework.evaluation.campaigns.executionError")}</span>
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

      <span className={styles.caseLink}>{t("rework.evaluation.campaigns.viewFullDetail")}</span>
    </button>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function EvaluationCampaigns({ teamId, onNewCampaign, onOpenCampaign }: EvaluationCampaignsProps) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const [drawerCampaignId, setDrawerCampaignId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<EvaluationCampaignResponse | null>(null);

  const { data, isLoading, isError, refetch } = useListCampaignsEvaluationV1CampaignsGetQuery(
    { teamId },
    { skip: !teamId, pollingInterval: 10_000 },
  );
  const [deleteCampaign, { isLoading: isDeleting }] = useDeleteCampaignEvaluationV1CampaignsCampaignIdDeleteMutation();

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    try {
      await deleteCampaign({ campaignId: deleteTarget.campaign_id }).unwrap();
      showSuccess({ summary: t("rework.evaluation.campaigns.deleteSuccess") });
      setDeleteTarget(null);
      refetch();
    } catch {
      showError({ summary: t("rework.evaluation.campaigns.deleteError") });
    }
  };

  const campaigns = data?.campaigns ?? [];
  const running = campaigns.filter((c) => c.operational_state === "running").length;
  const totalCases = campaigns.reduce((sum, c) => sum + c.completed_cases, 0);
  const criticalErrors = campaigns.reduce((sum, c) => sum + c.execution_error_cases, 0);
  const completedWithAverages = campaigns.filter((c) => c.metric_averages && Object.keys(c.metric_averages).length > 0);
  const globalScore = completedWithAverages.length
    ? Math.round(
        (completedWithAverages.reduce((sum, c) => {
          const vals = Object.values(c.metric_averages!);
          const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
          return sum + avg;
        }, 0) /
          completedWithAverages.length) *
          100,
      )
    : null;

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
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>{t("rework.evaluation.campaigns.title")}</h1>
          <p className={styles.subtitle}>{t("rework.evaluation.campaigns.description")}</p>
        </div>
        <Button color="primary" variant="filled" size="medium" onClick={onNewCampaign}>
          {t("rework.evaluation.campaigns.newCampaign")}
        </Button>
      </div>

      <div className={styles.kpiRow}>
        <KpiStatCard
          label={t("rework.evaluation.campaigns.kpi.active")}
          value={running}
          isLoading={isLoading}
          isError={isError}
        />
        <KpiStatCard
          label={t("rework.evaluation.campaigns.kpi.globalScore")}
          value={globalScore ?? undefined}
          isLoading={isLoading}
          isError={isError}
        />
        <KpiStatCard
          label={t("rework.evaluation.campaigns.kpi.casesEvaluated")}
          value={totalCases}
          isLoading={isLoading}
          isError={isError}
        />
        <KpiStatCard
          label={t("rework.evaluation.campaigns.kpi.criticalFailures")}
          value={criticalErrors}
          isLoading={isLoading}
          isError={isError}
        />
      </div>

      {!isLoading && campaigns.length === 0 && (
        <PageEmptyState
          icon="reviews"
          message={t("rework.evaluation.campaigns.empty")}
          action={{ label: t("rework.evaluation.campaigns.createCampaign"), onClick: onNewCampaign }}
        />
      )}

      {!isLoading && campaigns.length > 0 && (
        <div className={styles.table} role="table">
          <div className={`${styles.row} ${styles.headerRow}`} role="row">
            <span>{t("rework.evaluation.campaigns.col.name")}</span>
            <span>{t("rework.evaluation.campaigns.col.target")}</span>
            <span>{t("rework.evaluation.campaigns.col.state")}</span>
            <span>{t("rework.evaluation.campaigns.col.verdict")}</span>
            <span>{t("rework.evaluation.campaigns.col.progress")}</span>
            <span>{t("rework.evaluation.campaigns.col.scores")}</span>
            <span />
          </div>

          {campaigns.map((c) => {
            const isRunning = c.operational_state === "running";
            return (
              <div
                key={c.campaign_id}
                className={`${styles.row} ${styles.bodyRow} ${isRunning ? styles.rowRunning : ""}`}
                role="row"
                tabIndex={0}
                onClick={() => setDrawerCampaignId(c.campaign_id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") setDrawerCampaignId(c.campaign_id);
                }}
              >
                <div className={styles.nameCell}>
                  {isRunning && <IndicatorDot status="streaming" label={t("rework.evaluation.campaigns.col.state")} />}
                  <div>
                    <div className={styles.name}>{c.name}</div>
                    <div className={styles.mono}>{c.campaign_id.slice(0, 12)}</div>
                  </div>
                </div>
                <span className={styles.mono}>{targetLabel(c.target, t)}</span>
                <span>
                  <TaskStateBadge state={operationalToTaskState(c.operational_state)} />
                </span>
                <span>
                  <StatusPill label={c.verdict} tone={verdictTone(c.verdict)} />
                </span>
                <div className={styles.progressCell}>
                  <span className={styles.muted}>
                    {c.completed_cases} / {c.total_cases}
                  </span>
                  <ProgressBar theme="secondary" current={c.completed_cases} max={c.total_cases || 1} />
                </div>
                <div className={styles.scoresCell}>
                  {c.metric_averages && Object.keys(c.metric_averages).length > 0 ? (
                    Object.entries(c.metric_averages).map(([name, avg]) => {
                      const pct = Math.round(avg * 100);
                      return (
                        <div key={name} className={styles.scoreLine}>
                          <span className={styles.muted}>{name}</span>
                          <StatusPill label={`${pct}%`} tone={scoreTone(pct)} />
                        </div>
                      );
                    })
                  ) : (
                    <span className={styles.muted}>—</span>
                  )}
                </div>
                <div className={styles.actionsCell} onClick={(e) => e.stopPropagation()}>
                  <Button
                    color="on-surface"
                    variant="outlined"
                    size="small"
                    onClick={() => onOpenCampaign(c.campaign_id)}
                  >
                    {t("rework.evaluation.campaigns.detail")}
                  </Button>
                  <Button
                    color="error"
                    variant="outlined"
                    size="small"
                    disabled={isRunning}
                    onClick={() => setDeleteTarget(c)}
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
        campaignId={drawerCampaignId}
        open={!!drawerCampaignId}
        onClose={() => setDrawerCampaignId(null)}
        onOpenCase={(caseId) => {
          const id = drawerCampaignId;
          setDrawerCampaignId(null);
          if (id) onOpenCampaign(id, caseId);
        }}
      />

      <ConfirmationDialog
        open={!!deleteTarget}
        title={t("rework.evaluation.campaigns.deleteTitle")}
        message={t("rework.evaluation.campaigns.deleteMessage", { name: deleteTarget?.name ?? "" })}
        confirmLabel={isDeleting ? t("common.deleting") : t("common.delete")}
        cancelLabel={t("common.cancel")}
        criticalAction
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
