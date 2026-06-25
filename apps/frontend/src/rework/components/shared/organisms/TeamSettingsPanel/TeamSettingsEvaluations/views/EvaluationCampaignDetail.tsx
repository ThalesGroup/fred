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

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useDispatch, useSelector } from "react-redux";
import Button from "@shared/atoms/Button/Button";
import Disclosure from "@shared/atoms/Disclosure/Disclosure";
import ProgressBar from "@shared/atoms/ProgressBar/ProgressBar";
import { TaskStateBadge } from "@shared/atoms/TaskStateBadge/TaskStateBadge";
import { TaskProgressBar } from "@shared/atoms/TaskProgressBar/TaskProgressBar";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import type { ColorTheme } from "@shared/utils/Type";
import {
  StatusPill,
  FieldBlock,
  verdictTone,
  stateTone,
  scoreTone,
  operationalToTaskState,
  type StatusTone,
} from "./EvaluationShared";
import { selectTask, taskRegistered } from "@rework/features/tasks/taskSlice";
import {
  useCancelCampaignEvaluationV1CampaignsCampaignIdCancelPostMutation,
  useAnalyzeCampaignEvaluationV1CampaignsCampaignIdAnalyzePostMutation,
  useGetCampaignEvaluationV1CampaignsCampaignIdGetQuery,
  useGetTelemetryEvaluationV1TelemetryGetQuery,
  useGetTelemetrySessionEvaluationV1TelemetrySessionCampaignIdGetQuery,
  useListCasesEvaluationV1CampaignsCampaignIdCasesGetQuery,
  type CampaignAnalysisResult,
  type EvaluationCampaignResponse,
  type EvaluationCaseResponse,
  type EvaluationMetricResultResponse,
} from "../../../../../../../slices/evaluation/evaluationOpenApi";
import styles from "./EvaluationCampaignDetail.module.css";

// ── Helpers (pure logic — no UI framework) ──────────────────────────────────

/** ProgressBar's theme is a ColorTheme; map our semantic tone onto it. */
function toneTheme(tone: StatusTone): ColorTheme {
  return tone === "neutral" ? "on-surface-retreat" : tone;
}

function formatMs(ms: number | null | undefined): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
}

function passRate(c: EvaluationCampaignResponse): number {
  if (!c.total_cases) return 0;
  return Math.round((c.passed_cases / c.total_cases) * 100);
}

function useAnimatedCount(target: number): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    const start = performance.now();
    let raf: number;
    const tick = (now: number) => {
      const t = Math.min((now - start) / 800, 1);
      const ease = 1 - Math.pow(1 - t, 3);
      setCount(Math.round(ease * target));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target]);
  return count;
}

// ── Sub-components ───────────────────────────────────────────────────────────

function StatCard({ label, value, tone }: { label: string; value: number; tone: StatusTone }) {
  const animated = useAnimatedCount(value);
  return (
    <div className={styles.statCard}>
      <span className={styles.statValue} data-tone={tone}>
        {animated}
      </span>
      <span className={styles.statLabel}>{label}</span>
    </div>
  );
}

function AnalysisSection({ title, items, tone }: { title: string; items: string[]; tone: StatusTone }) {
  if (!items.length) return null;
  return (
    <div className={styles.analysisSection}>
      <span className={styles.analysisHeading} data-tone={tone}>
        {title}
      </span>
      <ul className={styles.analysisList}>
        {items.map((item, i) => (
          <li key={i} className={styles.analysisItem}>
            <span className={styles.bullet} data-tone={tone} aria-hidden="true" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const RISK_TONE: Record<string, StatusTone> = { low: "success", medium: "warning", high: "error" };

// ── Main ─────────────────────────────────────────────────────────────────────

interface EvaluationCampaignDetailProps {
  campaignId: string;
  selectedCaseId?: string;
  onBack: () => void;
}

export default function EvaluationCampaignDetail({
  campaignId,
  selectedCaseId,
  onBack,
}: EvaluationCampaignDetailProps) {
  const { t } = useTranslation();
  const [selectedCase, setSelectedCase] = useState<EvaluationCaseResponse | null>(null);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<CampaignAnalysisResult | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  const {
    data: campaign,
    isLoading: campaignLoading,
    refetch: refetchCampaign,
  } = useGetCampaignEvaluationV1CampaignsCampaignIdGetQuery({ campaignId }, { skip: !campaignId });

  const {
    data: casesData,
    isLoading: casesLoading,
    refetch: refetchCases,
  } = useListCasesEvaluationV1CampaignsCampaignIdCasesGetQuery({ campaignId, limit: 200 }, { skip: !campaignId });

  const [cancelCampaign, { isLoading: isCancelling }] =
    useCancelCampaignEvaluationV1CampaignsCampaignIdCancelPostMutation();
  const [analyzeCampaign, { isLoading: isAnalyzing }] =
    useAnalyzeCampaignEvaluationV1CampaignsCampaignIdAnalyzePostMutation();

  const { data: telemetry } = useGetTelemetryEvaluationV1TelemetryGetQuery();
  const { data: langfuseSession } = useGetTelemetrySessionEvaluationV1TelemetrySessionCampaignIdGetQuery(
    { campaignId },
    {
      skip: !campaignId || !telemetry?.enabled,
      pollingInterval: 10000,
    },
  );

  const isLive = campaign?.operational_state === "running" || campaign?.operational_state === "pending";

  // The campaign run is a task in the shared task store. Register it (live only,
  // dedup-safe) so useTaskSseManager streams /evaluation/v1/tasks/{task_id}/events
  // and it surfaces in the global TaskTray; the badge/bar below read from the store.
  const dispatch = useDispatch();
  const taskVm = useSelector(selectTask(campaign?.task_id ?? ""));
  useEffect(() => {
    if (!campaign?.task_id || !isLive) return;
    dispatch(
      taskRegistered({
        taskId: campaign.task_id,
        kind: "evaluation",
        target: { type: "evaluation_campaign", id: campaign.campaign_id, label: campaign.name },
      }),
    );
  }, [dispatch, campaign?.task_id, campaign?.campaign_id, campaign?.name, isLive]);

  // Refresh domain data (campaign aggregates + cases) as the task progresses.
  useEffect(() => {
    if (!taskVm) return;
    refetchCampaign();
    refetchCases();
  }, [taskVm?.lastSeq, taskVm?.state]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-open the case drawer when opened from the campaigns list.
  useEffect(() => {
    if (!selectedCaseId || !casesData?.cases) return;
    const found = casesData.cases.find((c) => c.case_id === selectedCaseId);
    if (found) setSelectedCase(found);
  }, [selectedCaseId, casesData?.cases]);

  const handleCancel = async () => {
    setCancelError(null);
    try {
      await cancelCampaign({ campaignId }).unwrap();
    } catch (e) {
      const detail = (e as { data?: { detail?: unknown } })?.data?.detail;
      setCancelError(typeof detail === "string" ? detail : t("rework.evaluation.detail.cancelError"));
    }
  };

  const handleAnalyze = async () => {
    setAnalysisError(null);
    try {
      const result = await analyzeCampaign({ campaignId }).unwrap();
      setAnalysis(result.analysis as CampaignAnalysisResult);
    } catch (e) {
      const detail = (e as { data?: { detail?: unknown } })?.data?.detail;
      setAnalysisError(typeof detail === "string" ? detail : t("rework.evaluation.detail.analyzeError"));
    }
  };

  if (campaignLoading) {
    return <div className={styles.centered}>{t("rework.evaluation.detail.loading")}</div>;
  }
  if (!campaign) {
    return (
      <div className={styles.page}>
        <ServiceNotice icon="error" title={t("rework.evaluation.detail.notFound")} centered />
      </div>
    );
  }

  const cases = casesData?.cases ?? [];
  const rate = passRate(campaign);
  const taskState = taskVm?.state ?? operationalToTaskState(campaign.operational_state);
  const taskProgress =
    taskVm?.progress ?? (campaign.total_cases ? campaign.completed_cases / campaign.total_cases : null);

  const metricEntries = Object.entries(campaign.metric_averages ?? {});
  const globalScore = metricEntries.length
    ? Math.round((metricEntries.reduce((a, [, v]) => a + v, 0) / metricEntries.length) * 100)
    : null;

  const metadata: { label: string; value: string }[] = [
    {
      label: t("rework.evaluation.detail.meta.dataset"),
      value: `${campaign.dataset_name}${campaign.dataset_version ? ` v${campaign.dataset_version}` : ""}`,
    },
    { label: t("rework.evaluation.detail.meta.profile"), value: campaign.profile },
    { label: t("rework.evaluation.detail.meta.judge"), value: campaign.judge_profile_id },
    { label: t("rework.evaluation.detail.meta.team"), value: campaign.team_id },
    { label: t("rework.evaluation.detail.meta.created"), value: formatDate(campaign.created_at) },
    { label: t("rework.evaluation.detail.meta.started"), value: formatDate(campaign.started_at) },
    { label: t("rework.evaluation.detail.meta.completed"), value: formatDate(campaign.completed_at) },
  ];

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>{campaign.name}</h1>
          <p className={styles.subtitle}>
            {t("rework.evaluation.detail.subtitle", { id: campaign.campaign_id.slice(0, 12) })}
          </p>
        </div>
        <div className={styles.actions}>
          {isLive && (
            <Button color="error" variant="outlined" size="medium" disabled={isCancelling} onClick={handleCancel}>
              {isCancelling ? t("rework.evaluation.detail.cancelling") : t("rework.evaluation.detail.cancel")}
            </Button>
          )}
          {/* Gate on the canonical terminal-success TaskState (not the raw
              operational_state string): the backend may report "succeeded" or
              "completed", and operationalToTaskState collapses both to
              "succeeded" — the same state the hero badge renders. */}
          {taskState === "succeeded" && (
            <Button color="on-surface" variant="outlined" size="medium" disabled={isAnalyzing} onClick={handleAnalyze}>
              {isAnalyzing ? t("rework.evaluation.detail.analyzing") : t("rework.evaluation.detail.analyze")}
            </Button>
          )}
          {telemetry?.enabled && (
            <Button
              color="on-surface"
              variant="outlined"
              size="medium"
              disabled={!langfuseSession?.available}
              onClick={() => langfuseSession?.url && window.open(langfuseSession.url, "_blank")}
            >
              {langfuseSession?.available
                ? t("rework.evaluation.detail.langfuseOpen")
                : telemetry?.langfuse_session_url
                  ? t("rework.evaluation.detail.langfuseWaiting")
                  : t("rework.evaluation.detail.langfuseOffline")}
            </Button>
          )}
          <Button
            color="on-surface"
            variant="text"
            size="medium"
            icon={{ category: "outlined", type: "arrow_back" }}
            onClick={onBack}
          >
            {t("rework.evaluation.detail.back")}
          </Button>
        </div>
      </div>

      {cancelError && <div className={styles.errorBanner}>{cancelError}</div>}

      {/* Hero state row — canonical task state + domain verdict (two distinct planes). */}
      <div className={styles.heroRow}>
        <TaskStateBadge state={taskState} />
        <StatusPill
          label={t("rework.evaluation.detail.verdictLabel", { verdict: campaign.verdict })}
          tone={verdictTone(campaign.verdict)}
        />
        <span className={styles.muted}>
          {t("rework.evaluation.detail.rateSummary", {
            rate,
            done: campaign.completed_cases,
            total: campaign.total_cases,
          })}
        </span>
      </div>

      {/* Canonical task progress (creep while running, snaps to 100% on success). */}
      <TaskProgressBar state={taskState} progress={taskProgress} />

      {/* Aggregate stat cards */}
      <div className={styles.statRow}>
        <StatCard label={t("rework.evaluation.detail.stats.passed")} value={campaign.passed_cases} tone="success" />
        <StatCard label={t("rework.evaluation.detail.stats.failed")} value={campaign.failed_cases} tone="error" />
        <StatCard
          label={t("rework.evaluation.detail.stats.execErrors")}
          value={campaign.execution_error_cases}
          tone="warning"
        />
        <StatCard
          label={t("rework.evaluation.detail.stats.scoringErrors")}
          value={campaign.scoring_error_cases}
          tone="neutral"
        />
      </div>

      {/* Metric averages */}
      {metricEntries.length > 0 && (
        <div className={styles.card}>
          <span className={styles.cardTitle}>{t("rework.evaluation.detail.metricScores")}</span>
          <div className={styles.metricList}>
            {metricEntries.map(([name, avg]) => {
              const pct = Math.round(avg * 100);
              return (
                <div key={name} className={styles.metricRow}>
                  <div className={styles.metricHead}>
                    <span className={styles.muted}>{name}</span>
                    <span className={styles.metricPct} data-tone={scoreTone(pct)}>
                      {pct}%
                    </span>
                  </div>
                  <ProgressBar theme={toneTheme(scoreTone(pct))} current={pct} max={100} />
                </div>
              );
            })}
            {globalScore !== null && (
              <div className={styles.globalScore}>
                <span className={styles.muted}>{t("rework.evaluation.detail.globalScore")}</span>
                <span className={styles.metricPct} data-tone={scoreTone(globalScore)}>
                  {globalScore}%
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Analysis */}
      {analysisError && <div className={styles.errorBanner}>{analysisError}</div>}
      {analysis && (
        <div className={styles.card}>
          <div className={styles.analysisHead}>
            <div>
              <span className={styles.cardTitle}>{t("rework.evaluation.detail.analysisTitle")}</span>
              <StatusPill
                label={t("rework.evaluation.detail.risk", { level: analysis.risk_level })}
                tone={RISK_TONE[analysis.risk_level] ?? "neutral"}
              />
            </div>
            <Button color="on-surface" variant="text" size="small" onClick={() => setAnalysis(null)}>
              {t("rework.evaluation.detail.dismiss")}
            </Button>
          </div>
          <p className={styles.analysisSummary}>{analysis.summary}</p>
          <AnalysisSection title={t("rework.evaluation.detail.strengths")} items={analysis.strengths} tone="success" />
          <AnalysisSection
            title={t("rework.evaluation.detail.weaknesses")}
            items={analysis.weaknesses}
            tone="warning"
          />
          <AnalysisSection
            title={t("rework.evaluation.detail.recommendations")}
            items={analysis.recommendations}
            tone="info"
          />
        </div>
      )}

      {/* Metadata */}
      <Disclosure title={t("rework.evaluation.detail.campaignInfo")}>
        <div className={styles.metaGrid}>
          {metadata.map((item) => (
            <div key={item.label} className={styles.metaItem}>
              <span className={styles.muted}>{item.label}</span>
              <span className={styles.metaValue}>{item.value}</span>
            </div>
          ))}
        </div>
      </Disclosure>

      {/* Cases */}
      <div className={styles.card}>
        <span className={styles.cardTitle}>
          {t("rework.evaluation.detail.cases", { count: casesData?.total ?? 0 })}
        </span>
        {casesLoading ? (
          <div className={styles.centered}>{t("rework.evaluation.detail.loadingCases")}</div>
        ) : (
          <div className={styles.table}>
            <div className={`${styles.row} ${styles.headerRow}`}>
              <span>{t("rework.evaluation.detail.col.id")}</span>
              <span>{t("rework.evaluation.detail.col.input")}</span>
              <span>{t("rework.evaluation.detail.col.status")}</span>
              <span>{t("rework.evaluation.detail.col.verdict")}</span>
              <span>{t("rework.evaluation.detail.col.latency")}</span>
              <span>{t("rework.evaluation.detail.col.metrics")}</span>
            </div>
            {cases.map((c) => (
              <button
                key={c.case_id}
                type="button"
                className={`${styles.row} ${styles.bodyRow}`}
                onClick={() => setSelectedCase(c)}
              >
                <span className={styles.mono}>{c.external_id ?? c.case_id.slice(0, 10)}</span>
                <span className={styles.truncate}>{c.input}</span>
                <StatusPill label={c.status} tone={stateTone(c.status)} />
                <StatusPill label={c.verdict} tone={verdictTone(c.verdict)} />
                <span className={styles.muted}>{formatMs(c.latency_ms)}</span>
                <span className={styles.metricChips}>
                  {c.metrics.length > 0 ? (
                    <>
                      {c.metrics.slice(0, 2).map((m, i) => (
                        <StatusPill
                          key={i}
                          label={`${m.name.replace("Metric", "")} ${m.score != null ? `${Math.round(m.score * 100)}%` : "—"}`}
                          tone={verdictTone(m.verdict)}
                        />
                      ))}
                      {c.metrics.length > 2 && <span className={styles.muted}>+{c.metrics.length - 2}</span>}
                    </>
                  ) : (
                    <span className={styles.muted}>—</span>
                  )}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Case drawer */}
      <InlineDrawer
        open={!!selectedCase}
        onClose={() => setSelectedCase(null)}
        title={t("rework.evaluation.detail.caseTitle")}
        width="560px"
      >
        {selectedCase && <CaseDetail caseData={selectedCase} t={t} />}
      </InlineDrawer>
    </div>
  );
}

// ── Case drawer body ─────────────────────────────────────────────────────────

function CaseDetail({ caseData, t }: { caseData: EvaluationCaseResponse; t: ReturnType<typeof useTranslation>["t"] }) {
  return (
    <div className={styles.caseBody}>
      <div className={styles.caseMetaRow}>
        <StatusPill label={caseData.verdict} tone={verdictTone(caseData.verdict)} />
        <span className={styles.muted}>
          {t("rework.evaluation.detail.latency")}: {formatMs(caseData.latency_ms)}
        </span>
        <span className={styles.muted}>
          {t("rework.evaluation.detail.col.status")}: {caseData.status}
        </span>
      </div>

      <FieldBlock label={t("rework.evaluation.detail.input")} value={caseData.input} />
      {caseData.expected_output && (
        <FieldBlock label={t("rework.evaluation.detail.expected")} value={caseData.expected_output} />
      )}
      {caseData.actual_output && (
        <FieldBlock label={t("rework.evaluation.detail.actual")} value={caseData.actual_output} />
      )}

      {caseData.execution_error && (
        <div className={styles.errorBanner}>
          <strong>{t("rework.evaluation.detail.execError")}</strong>
          <span>{caseData.execution_error}</span>
        </div>
      )}

      {caseData.scoring_errors?.length > 0 && (
        <div className={styles.warningBanner}>
          <strong>{t("rework.evaluation.detail.scoringErrors")}</strong>
          {caseData.scoring_errors.map((e, i) => (
            <span key={i}>{e}</span>
          ))}
        </div>
      )}

      {caseData.metrics.length > 0 && (
        <div className={styles.caseSection}>
          <span className={styles.cardTitle}>
            {t("rework.evaluation.detail.metrics", { count: caseData.metrics.length })}
          </span>
          {caseData.metrics.map((m: EvaluationMetricResultResponse, i: number) => (
            <div key={i} className={styles.metricRow}>
              <div className={styles.metricHead}>
                <span className={styles.muted}>{m.name.replace("Metric", "")}</span>
                <div className={styles.caseMetaRow}>
                  {m.score != null && (
                    <span className={styles.metricPct} data-tone={verdictTone(m.verdict)}>
                      {Math.round(m.score * 100)}%
                    </span>
                  )}
                  <StatusPill label={m.verdict} tone={verdictTone(m.verdict)} />
                </div>
              </div>
              {m.score != null && (
                <ProgressBar theme={toneTheme(verdictTone(m.verdict))} current={Math.round(m.score * 100)} max={100} />
              )}
              {m.explanation && <span className={styles.muted}>{m.explanation}</span>}
            </div>
          ))}
        </div>
      )}

      {caseData.structural_checks?.length > 0 && (
        <div className={styles.caseSection}>
          <span className={styles.cardTitle}>
            {t("rework.evaluation.detail.structural", { count: caseData.structural_checks.length })}
          </span>
          {caseData.structural_checks.map((c: { name: string; passed: boolean | null }, i: number) => (
            <div key={i} className={styles.metricHead}>
              <span className={styles.muted}>{c.name}</span>
              <StatusPill
                label={
                  c.passed === null
                    ? t("rework.evaluation.detail.skipped")
                    : c.passed
                      ? t("rework.evaluation.detail.passed")
                      : t("rework.evaluation.detail.failed")
                }
                tone={c.passed === null ? "neutral" : c.passed ? "success" : "error"}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
