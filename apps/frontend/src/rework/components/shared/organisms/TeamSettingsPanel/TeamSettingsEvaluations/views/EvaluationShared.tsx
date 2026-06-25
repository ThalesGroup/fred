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

// Shared building blocks for the evaluation admin pages. Design-system only:
// semantic status -> design-token class names, no hardcoded colors.

import type { TaskState } from "@rework/features/tasks/taskTypes";
import styles from "./EvaluationShared.module.css";

export type StatusTone = "success" | "error" | "warning" | "info" | "neutral";

/**
 * Map a campaign `operational_state` onto the canonical six-state `TaskState`,
 * so the shared Task components (TaskStateBadge / TaskProgressBar) render it.
 * Mirrors the evaluator's server-side mapping ("completed" is terminal success).
 */
export function operationalToTaskState(operationalState: string): TaskState {
  switch (operationalState) {
    case "running":
      return "running";
    case "cancelling":
      return "cancelling";
    case "completed":
    case "succeeded":
      return "succeeded";
    case "failed":
      return "failed";
    case "cancelled":
      return "cancelled";
    default:
      return "pending";
  }
}

/** Map a case/campaign verdict to a semantic tone. */
export function verdictTone(verdict: string): StatusTone {
  switch (verdict) {
    case "passed":
      return "success";
    case "failed":
      return "error";
    case "inconclusive":
      return "warning";
    default:
      return "neutral";
  }
}

/** Map an operational state to a semantic tone. */
export function stateTone(state: string): StatusTone {
  switch (state) {
    case "running":
      return "info";
    case "completed":
    case "succeeded":
      return "success";
    case "failed":
    case "cancelled":
      return "error";
    case "pending":
      return "warning";
    default:
      return "neutral";
  }
}

/** Tone for a 0..100 score percentage. */
export function scoreTone(pct: number): StatusTone {
  if (pct >= 80) return "success";
  if (pct >= 50) return "warning";
  return "error";
}

const toneClass: Record<StatusTone, string> = {
  success: styles.toneSuccess,
  error: styles.toneError,
  warning: styles.toneWarning,
  info: styles.toneInfo,
  neutral: styles.toneNeutral,
};

/** A small, design-token-driven status pill. */
export function StatusPill({ label, tone }: { label: string; tone: StatusTone }) {
  return <span className={`${styles.pill} ${toneClass[tone]}`}>{label}</span>;
}

/** Labelled, monospace, scrollable text block (case input/output, etc.). */
export function FieldBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.fieldBlock}>
      <span className={styles.fieldLabel}>{label}</span>
      <pre className={styles.fieldValue}>{value}</pre>
    </div>
  );
}
