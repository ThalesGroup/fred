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
import Button from "@shared/atoms/Button/Button.tsx";
import { TaskStateBadge } from "@shared/atoms/TaskStateBadge/TaskStateBadge.tsx";
import { TaskProgressBar } from "@shared/atoms/TaskProgressBar/TaskProgressBar.tsx";
import type { TaskState } from "../../../../features/tasks/taskTypes";
import type { StepReport, StepStatus } from "../../../../features/pipeline/types";
import styles from "./SelfTestPage.module.css";

// The Task atoms speak the fred-core TaskState vocabulary; map the pipeline
// step verdicts onto it so we can reuse the badge and progress bar as-is.
const STEP_TO_TASK_STATE: Record<StepStatus, TaskState> = {
  pending: "pending",
  running: "running",
  passed: "succeeded",
  failed: "failed",
  skipped: "cancelled",
};

function overallState(steps: StepReport[], isRunning: boolean): TaskState {
  if (isRunning || steps.length === 0) return "running";
  if (steps.some((s) => s.status === "failed")) return "failed";
  // A skipped REQUIRED step means a validation never ran (e.g. a precondition
  // was missing), so the run did not succeed — only teardown/optional steps
  // may skip freely.
  if (steps.some((s) => s.status === "skipped" && !s.optional)) return "failed";
  return "succeeded";
}

function buildReport(steps: StepReport[]): string {
  const passed = steps.filter((s) => s.status === "passed").length;
  const failed = steps.filter((s) => s.status === "failed").length;
  const skipped = steps.filter((s) => s.status === "skipped").length;
  const lines = steps.map((step, i) => {
    const dur = step.durationMs != null ? ` (${step.durationMs} ms)` : "";
    const info = step.error ? ` — ERROR: ${step.error}` : step.detail ? ` — ${step.detail}` : "";
    return `${i + 1}. [${step.status.toUpperCase()}] ${step.title}${info}${dur}`;
  });
  return [
    `Self-test: ${passed} passed, ${failed} failed, ${skipped} skipped, ${steps.length} steps`,
    "",
    ...lines,
  ].join("\n");
}

interface StepReportPanelProps {
  steps: StepReport[];
  isRunning: boolean;
  /** Shown instead of the step list before the first run. */
  emptyLabel: string;
}

/**
 * Renders one pipeline run's live progress + step list + copy-to-clipboard
 * report. Shared by every self-test section on this page (functional,
 * authorization-for-myself, authorization-for-another-profile) so the
 * report UI/format stays identical regardless of which scenario produced it.
 */
export function StepReportPanel({ steps, isRunning, emptyLabel }: StepReportPanelProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const passed = steps.filter((s) => s.status === "passed").length;
  const failed = steps.filter((s) => s.status === "failed").length;
  const skipped = steps.filter((s) => s.status === "skipped").length;
  const total = steps.length;
  const completed = steps.filter((s) => s.status !== "running").length;
  const progress = total > 0 ? completed / total : null;

  const handleCopy = async () => {
    await navigator.clipboard.writeText(buildReport(steps));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  if (total === 0) {
    return <div className={styles.empty}>{emptyLabel}</div>;
  }

  return (
    <section className={styles.section}>
      <div className={styles.summary}>
        <TaskStateBadge state={overallState(steps, isRunning)} size="md" />
        <span className={styles.counts}>{t("rework.selftest.report.counts", { passed, failed, skipped, total })}</span>
        <Button
          color="secondary"
          variant="outlined"
          size="small"
          icon={{ category: "outlined", type: "content_copy", filled: false }}
          onClick={handleCopy}
          className={styles.copyBtn}
        >
          {copied ? t("rework.selftest.report.copied") : t("rework.selftest.report.copy")}
        </Button>
      </div>
      <TaskProgressBar state={overallState(steps, isRunning)} progress={progress} />

      <ul className={styles.steps}>
        {steps.map((step) => (
          <li key={step.id} className={styles.step}>
            <TaskStateBadge state={STEP_TO_TASK_STATE[step.status]} showLabel={false} size="md" />
            <div className={styles.stepBody}>
              <span className={styles.stepTitle}>{step.title}</span>
              {(step.error || step.detail) && (
                <span className={step.error ? styles.stepError : styles.stepDetail}>{step.error ?? step.detail}</span>
              )}
            </div>
            {step.durationMs != null && <span className={styles.duration}>{step.durationMs} ms</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
