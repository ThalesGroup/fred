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
import { usePipelineRun } from "../../../../features/pipeline/usePipelineRun";
import { selfTestScenario } from "../../../../features/pipeline/scenarios/selfTestScenario";
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
  // A skipped REQUIRED step means a validation never ran (e.g. the self-test agent
  // was missing), so the run did not succeed — only teardown steps may skip freely.
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

export default function SelfTestPage() {
  const { t } = useTranslation();
  const { steps, isRunning, start } = usePipelineRun(selfTestScenario);
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

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>{t("rework.selftest.page.title")}</h1>
        <Button
          color="primary"
          variant="filled"
          size="medium"
          icon={{ category: "outlined", type: "check_circle", filled: false }}
          onClick={start}
          disabled={isRunning}
        >
          {isRunning ? t("rework.selftest.page.running") : t("rework.selftest.page.run")}
        </Button>
      </div>

      <p className={styles.subtitle}>{t("rework.selftest.page.subtitle")}</p>

      {total > 0 && (
        <section className={styles.section}>
          <div className={styles.summary}>
            <TaskStateBadge state={overallState(steps, isRunning)} size="md" />
            <span className={styles.counts}>
              {t("rework.selftest.page.counts", { passed, failed, skipped, total })}
            </span>
            <Button
              color="secondary"
              variant="outlined"
              size="small"
              icon={{ category: "outlined", type: "content_copy", filled: false }}
              onClick={handleCopy}
              className={styles.copyBtn}
            >
              {copied ? t("rework.selftest.page.copied") : t("rework.selftest.page.copy")}
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
                    <span className={step.error ? styles.stepError : styles.stepDetail}>
                      {step.error ?? step.detail}
                    </span>
                  )}
                </div>
                {step.durationMs != null && <span className={styles.duration}>{step.durationMs} ms</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {total === 0 && <div className={styles.empty}>{t("rework.selftest.page.empty")}</div>}
    </div>
  );
}
