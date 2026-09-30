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

// The phases an imported file goes through, and where a given file has got to.
// One model for both the stepper's markers and the words naming the current
// phase, so the two can never disagree about where a file is.

import type { TFunction } from "i18next";
import type { TaskViewModel } from "../tasks/taskTypes";

/** The browser's own transfer, then the three the ingestion workflow reports
 *  one by one. Nothing finer exists: the phases below are exactly the events
 *  the server emits per file. */
export const IMPORT_PHASES = ["upload", "uploading", "processing", "indexing"] as const;
export type ImportPhase = (typeof IMPORT_PHASES)[number];
export type PhaseState = "pending" | "current" | "done" | "failed";

const PHASE_LABEL: Record<ImportPhase, string> = {
  upload: "rework.tasks.importStage.upload",
  uploading: "rework.tasks.ingestionStep.uploading",
  processing: "rework.tasks.ingestionStep.processing",
  indexing: "rework.tasks.ingestionStep.indexing",
};

const SERVER_PHASE: Record<string, number> = { uploading: 1, processing: 2, indexing: 3 };

/** The phase's own name — the same wording the status line uses for it. */
export const importPhaseName = (phase: ImportPhase, t: TFunction): string => t(PHASE_LABEL[phase]);

type PhaseInput = Pick<TaskViewModel, "stage" | "step" | "state">;

/** Index of the phase in flight; `IMPORT_PHASES.length` once all are behind. */
export function importPhaseIndex(task: PhaseInput): number {
  if (task.state === "succeeded") return IMPORT_PHASES.length;
  if (task.stage === "upload") return 0;
  // Waiting on the user: the transfer is over, the server has not started.
  if (task.stage === "decision") return 1;
  const step = task.step ?? "";
  if (step === "done") return IMPORT_PHASES.length;
  // A deployment without the scheduler skips `indexing` entirely, and the
  // first event can arrive late — an unnamed step means only the transfer is
  // known to be behind us.
  return SERVER_PHASE[step] ?? 1;
}

export function importPhaseStates(task: PhaseInput): PhaseState[] {
  const current = importPhaseIndex(task);
  const stopped = task.state === "failed" || task.state === "cancelled";
  const held = task.stage === "decision";
  return IMPORT_PHASES.map((_, i) => {
    if (i < current) return "done";
    if (i > current) return "pending";
    if (stopped) return "failed";
    return held ? "pending" : "current";
  });
}
