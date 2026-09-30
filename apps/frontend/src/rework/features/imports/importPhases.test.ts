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

// The one line an import card says about itself. The markers beside it carry
// the shape of the work; this is the only place it is put into words.

import type { TFunction } from "i18next";
import { describe, expect, it } from "vitest";
import type { TaskViewModel } from "../tasks/taskTypes";
import { importPhaseLabel } from "./importPhases";

const t = ((key: string) => key) as unknown as TFunction;

const task = (o: Partial<TaskViewModel>) =>
  ({ stage: "analysis", step: null, state: "running", ...o }) as TaskViewModel;

describe("importPhaseLabel", () => {
  it("names the phase in flight", () => {
    expect(importPhaseLabel(task({ stage: "upload" }), t)).toBe("rework.tasks.importStage.upload");
    expect(importPhaseLabel(task({ step: "processing" }), t)).toBe("rework.tasks.ingestionStep.processing");
  });

  it("says the file is in once every phase is behind it", () => {
    // The card's last word before it leaves the panel on its own.
    expect(importPhaseLabel(task({ state: "succeeded" }), t)).toBe("rework.tasks.ingestionStep.done");
  });

  it("says nothing for a file held on the user's answer", () => {
    // The panel asks the question itself; a phase name would talk over it.
    expect(importPhaseLabel(task({ stage: "decision", state: "pending" }), t)).toBeNull();
  });

  it("says the file was sent, not ingested, when nothing was going to ingest it", () => {
    // Upload-only mode never hands the file to the server's half. Calling that
    // "ingestion complete" claimed something that never happened.
    expect(importPhaseLabel(task({ stage: "upload", state: "succeeded" }), t)).toBe(
      "rework.tasks.importStage.uploadDone",
    );
  });
});
