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
import {
  useSelfTestRun,
  type SelfTestRun,
  type SelfTestRunState,
  type SelfTestStepStatus,
} from "../../../../features/selfTest/useSelfTestRun";
import styles from "./SelfTestPage.module.css";

// The Task atoms speak the fred-core TaskState vocabulary; map the self-test
// step/run verdicts onto it so we can reuse the badge and progress bar as-is.
const STEP_TO_TASK_STATE: Record<SelfTestStepStatus, TaskState> = {
  pending: "pending",
  running: "running",
  passed: "succeeded",
  failed: "failed",
  skipped: "cancelled",
};

const RUN_TO_TASK_STATE: Record<SelfTestRunState, TaskState> = {
  running: "running",
  passed: "succeeded",
  failed: "failed",
};

function buildReport(run: SelfTestRun, passed: number, failed: number, total: number): string {
  const header = [
    `Self-test campaign ${run.run_id}`,
    `State: ${run.state}`,
    `Result: ${passed} passed, ${failed} failed, ${total} steps`,
    "",
  ];
  const steps = run.steps.map((step, i) => {
    const dur = step.duration_ms != null ? ` (${Math.round(step.duration_ms)} ms)` : "";
    const info = step.error ? ` — ERROR: ${step.error}` : step.detail ? ` — ${step.detail}` : "";
    return `${i + 1}. [${step.status.toUpperCase()}] ${step.title}${info}${dur}`;
  });
  return [...header, ...steps].join("\n");
}

export default function SelfTestPage() {
  const { t } = useTranslation();
  const { run, isRunning, error, start } = useSelfTestRun();
  const [copied, setCopied] = useState(false);

  const passed = run?.steps.filter((s) => s.status === "passed").length ?? 0;
  const failed = run?.steps.filter((s) => s.status === "failed").length ?? 0;
  const total = run?.steps.length ?? 0;

  const handleCopy = async () => {
    if (!run) return;
    await navigator.clipboard.writeText(buildReport(run, passed, failed, total));
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

      {error && <div className={styles.error}>{error}</div>}

      {run && (
        <section className={styles.section}>
          <div className={styles.summary}>
            <TaskStateBadge state={RUN_TO_TASK_STATE[run.state]} size="md" />
            <span className={styles.counts}>{t("rework.selftest.page.counts", { passed, failed, total })}</span>
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
          <TaskProgressBar state={RUN_TO_TASK_STATE[run.state]} progress={run.progress} />

          <ul className={styles.steps}>
            {run.steps.map((step) => (
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
                {step.duration_ms != null && <span className={styles.duration}>{Math.round(step.duration_ms)} ms</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {!run && !error && <div className={styles.empty}>{t("rework.selftest.page.empty")}</div>}
    </div>
  );
}
