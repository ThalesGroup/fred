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

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Disclosure from "@shared/atoms/Disclosure/Disclosure";
import IconButton from "@shared/atoms/IconButton/IconButton";
import ProgressBar from "@shared/atoms/ProgressBar/ProgressBar";
import { TaskStateBadge } from "@shared/atoms/TaskStateBadge/TaskStateBadge";
import { TaskProgressBar } from "@shared/atoms/TaskProgressBar/TaskProgressBar";
import { Breadcrumb } from "@shared/molecules/Breadcrumb/Breadcrumb";
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
import {
  useCancelRunEvaluationV1RunsRunIdCancelPostMutation,
  useAnalyzeRunEvaluationV1RunsRunIdAnalyzePostMutation,
  useGetRunEvaluationV1RunsRunIdGetQuery,
  useGetTelemetryEvaluationV1TelemetryGetQuery,
  useGetTelemetrySessionEvaluationV1TelemetrySessionRunIdGetQuery,
  useListRunCasesEvaluationV1RunsRunIdCasesGetQuery,
  type EvaluationCaseResponse,
  type EvaluationMetricResultResponse,
  type EvaluationRun,
  type RunAnalysisResult,
} from "../../../../../../../slices/evaluation/evaluationOpenApi";
import styles from "./EvaluationRunDetail.module.css";

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

function passRate(run: EvaluationRun): number {
  if (!run.total_cases) return 0;
  return Math.round((run.passed_cases / run.total_cases) * 100);
}

function aggregateMetricAverages(cases: EvaluationCaseResponse[]): Array<[string, number]> {
  const metrics = new Map<string, number[]>();
  for (const evaluationCase of cases) {
    for (const metric of evaluationCase.metrics) {
      if (metric.score == null) continue;
      const scores = metrics.get(metric.name) ?? [];
      scores.push(metric.score);
      metrics.set(metric.name, scores);
    }
  }

  return Array.from(metrics.entries()).map(([name, scores]) => [
    name,
    scores.reduce((sum, score) => sum + score, 0) / scores.length,
  ]);
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

interface EvaluationRunDetailProps {
  runId: string;
  selectedCaseId?: string;
  teamId: string;
  evaluationName: string;
  onBack: () => void;
  onBackToList: () => void;
}

export default function EvaluationRunDetail({
  runId,
  selectedCaseId,
  evaluationName,
  onBack,
  onBackToList,
}: EvaluationRunDetailProps) {
  const { t } = useTranslation();
  const [selectedCase, setSelectedCase] = useState<EvaluationCaseResponse | null>(null);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<RunAnalysisResult | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  // Whether the run is still active. Starts false — we don't know the state
  // until the first fetch resolves — then tracks run.operational_state. Used
  // to gate polling below; RTK Query still performs the initial fetch of both
  // queries regardless of pollingInterval, so this doesn't delay first paint.
  const [isLive, setIsLive] = useState(false);

  const { data: run, isLoading: runLoading } = useGetRunEvaluationV1RunsRunIdGetQuery(
    { runId },
    { skip: !runId, pollingInterval: isLive ? 5000 : 0 },
  );

  const {
    data: casesData,
    isLoading: casesLoading,
    refetch: refetchCases,
  } = useListRunCasesEvaluationV1RunsRunIdCasesGetQuery(
    { runId, limit: 200 },
    { skip: !runId, pollingInterval: isLive ? 5000 : 0 },
  );

  const [cancelRun, { isLoading: isCancelling }] = useCancelRunEvaluationV1RunsRunIdCancelPostMutation();
  const [analyzeRun, { isLoading: isAnalyzing }] = useAnalyzeRunEvaluationV1RunsRunIdAnalyzePostMutation();

  const { data: telemetry } = useGetTelemetryEvaluationV1TelemetryGetQuery();
  // Unlike `run`/`cases` above, this poll had no isLive gate — it kept hitting
  // the backend every 10s indefinitely, even long after the run went terminal,
  // as long as the drawer stayed open. Match the sibling queries' pattern:
  // poll while live, single fetch once terminal.
  const { data: langfuseSession } = useGetTelemetrySessionEvaluationV1TelemetrySessionRunIdGetQuery(
    { runId },
    {
      skip: !runId || !telemetry?.enabled,
      pollingInterval: isLive ? 10000 : 0,
    },
  );

  // The run and cases queries poll independently, on their own timers — not
  // in lockstep. If the run flips to a terminal state right as the cases
  // poll was mid-cycle, the cases table can freeze one tick before the last
  // case's own result actually landed (the exact symptom: run header shows
  // "Done, 5/5", one case row still stuck on "Running"). Force one more
  // cases fetch on the live -> terminal transition so the table can't get
  // stuck behind the run's own terminal write.
  const wasLiveRef = useRef(false);
  useEffect(() => {
    const nowLive = run?.operational_state === "running" || run?.operational_state === "pending";
    if (wasLiveRef.current && !nowLive) {
      refetchCases();
    }
    wasLiveRef.current = nowLive;
    setIsLive(nowLive);
  }, [run?.operational_state, refetchCases]);

  // Auto-open the case drawer when opened from the runs list's case drawer
  // ("View full detail" — EvaluationRuns.tsx's CaseDrawer).
  useEffect(() => {
    if (!selectedCaseId || !casesData?.cases) return;
    const found = casesData.cases.find((c) => c.case_id === selectedCaseId);
    if (found) setSelectedCase(found);
  }, [selectedCaseId, casesData?.cases]);

  const handleCancel = async () => {
    setCancelError(null);
    try {
      await cancelRun({ runId }).unwrap();
    } catch (e) {
      const detail = (e as { data?: { detail?: unknown } })?.data?.detail;
      setCancelError(typeof detail === "string" ? detail : t("rework.evaluation.detail.cancelError"));
    }
  };

  const handleAnalyze = async () => {
    setAnalysisError(null);
    try {
      const result = await analyzeRun({ runId }).unwrap();
      setAnalysis(result.analysis as RunAnalysisResult);
    } catch (e) {
      const detail = (e as { data?: { detail?: unknown } })?.data?.detail;
      setAnalysisError(typeof detail === "string" ? detail : t("rework.evaluation.detail.analyzeError"));
    }
  };

  if (runLoading) {
    return <div className={styles.centered}>{t("rework.evaluation.detail.loading")}</div>;
  }
  if (!run) {
    return (
      <div className={styles.page}>
        <ServiceNotice icon="error" title={t("rework.evaluation.detail.notFound")} centered />
      </div>
    );
  }

  const cases = casesData?.cases ?? [];
  const rate = passRate(run);
  const taskState = operationalToTaskState(run.operational_state);
  const taskProgress = run.total_cases ? run.completed_cases / run.total_cases : null;

  const metricEntries = aggregateMetricAverages(cases);
  const globalScore = metricEntries.length
    ? Math.round((metricEntries.reduce((sum, [, avg]) => sum + avg, 0) / metricEntries.length) * 100)
    : null;

  const metadata: { label: string; value: string }[] = [
    {
      label: t("rework.evaluation.detail.meta.dataset"),
      value: `${run.snapshot.evaluation_name} v${run.snapshot.evaluation_version}`,
    },
    { label: t("rework.evaluation.detail.meta.profile"), value: run.profile },
    { label: t("rework.evaluation.detail.meta.judge"), value: run.judge_profile_id },
    { label: t("rework.evaluation.detail.meta.team"), value: run.evaluation_id },
    { label: t("rework.evaluation.detail.meta.created"), value: formatDate(run.created_at) },
    { label: t("rework.evaluation.detail.meta.started"), value: formatDate(run.started_at) },
    { label: t("rework.evaluation.detail.meta.completed"), value: formatDate(run.completed_at) },
  ];

  return (
    <div className={styles.page}>
      <Breadcrumb
        segments={[
          { label: t("rework.evaluation.evaluations.title"), onClick: onBackToList },
          { label: evaluationName, onClick: onBack },
          { label: t("rework.evaluation.detail.subtitle", { id: run.run_id.slice(0, 12) }) },
        ]}
      />

      {/* Header */}
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>{run.snapshot.evaluation_name}</h1>
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
          {/* `telemetry.enabled` is a static config flag (tracer == "langfuse"),
              not a live reachability check — a deployment can have it set
              without ever actually running Langfuse. Only show this action
              when there's a real session to open, or a legitimate in-flight
              wait (a session URL already exists, e.g. mid-run before Langfuse
              has ingested the trace yet). Never render a permanently-dead
              "offline" button for a tracer that was never really reachable. */}
          {telemetry?.enabled && (langfuseSession?.available || telemetry?.langfuse_session_url) && (
            <Button
              color="on-surface"
              variant="outlined"
              size="medium"
              disabled={!langfuseSession?.available}
              onClick={() => langfuseSession?.url && window.open(langfuseSession.url, "_blank")}
            >
              {langfuseSession?.available
                ? t("rework.evaluation.detail.langfuseOpen")
                : t("rework.evaluation.detail.langfuseWaiting")}
            </Button>
          )}
        </div>
      </div>

      {cancelError && <div className={styles.errorBanner}>{cancelError}</div>}

      {/* Hero state row — canonical task state + domain verdict (two distinct planes). */}
      <div className={styles.heroRow}>
        <TaskStateBadge state={taskState} />
        <StatusPill
          label={t("rework.evaluation.detail.verdictLabel", { verdict: run.verdict })}
          tone={verdictTone(run.verdict)}
        />
        <span className={styles.muted}>
          {t("rework.evaluation.detail.rateSummary", {
            rate,
            done: run.completed_cases,
            total: run.total_cases,
          })}
        </span>
      </div>

      {/* Canonical task progress (creep while running, snaps to 100% on success). */}
      <TaskProgressBar state={taskState} progress={taskProgress} />

      {/* Aggregate stat cards */}
      <div className={styles.statRow}>
        <StatCard label={t("rework.evaluation.detail.stats.passed")} value={run.passed_cases} tone="success" />
        <StatCard label={t("rework.evaluation.detail.stats.failed")} value={run.failed_cases} tone="error" />
        <StatCard label={t("rework.evaluation.detail.stats.insufficient")} value={run.insufficient_cases} tone="info" />
        <StatCard
          label={t("rework.evaluation.detail.stats.execErrors")}
          value={run.execution_error_cases}
          tone="warning"
        />
        <StatCard
          label={t("rework.evaluation.detail.stats.scoringErrors")}
          value={run.scoring_error_cases}
          tone="neutral"
        />
      </div>

      {/* Metric averages — while the run is still live this is a rolling
          average of whichever cases have reported a score so far, not the
          final number. Label it as partial so it can't be mistaken for the
          finished result (the header's own pass-rate summary is the only
          number that's authoritative before completion). */}
      {metricEntries.length > 0 && (
        <div className={styles.card}>
          <span className={styles.cardTitle}>
            {isLive
              ? t("rework.evaluation.detail.metricScoresPartial", { done: run.completed_cases, total: run.total_cases })
              : t("rework.evaluation.detail.metricScores")}
          </span>
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
        width="880px"
      >
        {selectedCase && <CaseDetail caseData={selectedCase} t={t} />}
      </InlineDrawer>
    </div>
  );
}

// ── Case drawer body ─────────────────────────────────────────────────────────

function CaseDetail({ caseData, t }: { caseData: EvaluationCaseResponse; t: ReturnType<typeof useTranslation>["t"] }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard
      .writeText(JSON.stringify(caseData, null, 2))
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      })
      .catch(() => {});
  };

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
        <span className={styles.spacer} />
        <IconButton
          color="on-surface"
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: copied ? "check_circle" : "content_copy" }}
          aria-label={copied ? t("rework.evaluation.detail.copied") : t("rework.evaluation.detail.copyJson")}
          onClick={handleCopy}
        />
      </div>

      <FieldBlock label={t("rework.evaluation.detail.input")} value={caseData.input} />
      {(caseData.expected_output || caseData.actual_output) && (
        <div className={styles.compareGrid}>
          {caseData.expected_output && (
            <FieldBlock label={t("rework.evaluation.detail.expected")} value={caseData.expected_output} tall />
          )}
          {caseData.actual_output && (
            <FieldBlock label={t("rework.evaluation.detail.actual")} value={caseData.actual_output} tall />
          )}
        </div>
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
