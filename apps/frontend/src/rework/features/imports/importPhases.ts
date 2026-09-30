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

/** Every step an ingestion task can carry, placed on the four phases. All of
 *  them, not just the ones an import itself emits: an unplaced step falls to
 *  the default below, and one emitted late then walks the stepper backwards.
 *
 *  An import emits `uploading` / `processing` / `indexing` / `done`. The other
 *  three belong to revectorizing an existing document — a corpus operation,
 *  not an import — and reach this panel only when such a task is shown as one,
 *  which it should not be. Placed anyway: a stepper going backwards is a worse
 *  way to find that out. */
export const SERVER_PHASE: Record<string, number> = {
  // The batch has been listed; nothing has been said about this file yet.
  listed: 1,
  uploading: 1,
  processing: 2,
  indexing: 3,
  // Vectors written — the same work `indexing` reports on an import.
  vectorized: 3,
  // Already current: there was nothing left to do to it.
  skip: IMPORT_PHASES.length,
};

/** The phase's own name — the same wording the status line uses for it. */
export const importPhaseName = (phase: ImportPhase, t: TFunction): string => t(PHASE_LABEL[phase]);

/** What the phase is for, in a sentence or two. The names alone say little to
 *  someone importing for the first time, so the markers carry this on hover. */
export const importPhaseHint = (phase: ImportPhase, t: TFunction): string => t(`rework.imports.stepper.hint.${phase}`);

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

/** A run stands for the work crossing from one phase to the next, so it is
 *  drawn only once the phase behind it is done — a phase that gave up let
 *  nothing past. The run feeding the phase in flight takes that phase's
 *  colour, so the eye follows the work forward instead of stopping at the
 *  last tick. */
export function importLinkStates(states: PhaseState[]): PhaseState[] {
  return states.slice(0, -1).map((state, i) => {
    if (states[i + 1] === "current") return "current";
    return state === "done" ? "done" : "pending";
  });
}

/** The current phase's name — or, once every phase is behind it, that it is
 *  done. Null only for a file held on the user's answer, which the panel
 *  words itself. */
export function importPhaseLabel(task: PhaseInput, t: TFunction): string | null {
  if (task.stage === "decision") return null;
  const index = importPhaseIndex(task);
  // Past the last phase: the file is in, and saying so is the last thing the
  // card has to say before it goes. Except in upload-only mode, which never
  // hands the file to the server's half — there is no ingestion to report.
  if (index >= IMPORT_PHASES.length) {
    return t(task.stage === "upload" ? "rework.tasks.importStage.uploadDone" : "rework.tasks.ingestionStep.done");
  }
  return t(PHASE_LABEL[IMPORT_PHASES[index]]);
}

/** The same explanation, for whichever phase the status line is naming. Null
 *  where that line is not naming a phase at all. */
export function importPhaseHintFor(task: PhaseInput, t: TFunction): string | null {
  if (task.stage === "decision") return null;
  const index = importPhaseIndex(task);
  if (index >= IMPORT_PHASES.length) {
    return t(task.stage === "upload" ? "rework.imports.stepper.hint.doneUpload" : "rework.imports.stepper.hint.done");
  }
  return importPhaseHint(IMPORT_PHASES[index], t);
}
