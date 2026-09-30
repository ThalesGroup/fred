import en from "../../../locales/en/translation.json";
import fr from "../../../locales/fr/translation.json";
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
import { IMPORT_PHASES, SERVER_PHASE, importPhaseHintFor, importPhaseIndex, importPhaseLabel } from "./importPhases";
import { INGESTION_STEPS } from "../tasks/taskLabels";

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

  // The names alone say little to someone importing for the first time, so the
  // line carries the same explanation the stepper's markers do — on every
  // phase, and on both ways an import can end.
  it("explains whichever phase the line is naming", () => {
    expect(importPhaseHintFor(task({ stage: "upload", state: "running" }), t)).toBe(
      "rework.imports.stepper.hint.upload",
    );
    expect(importPhaseHintFor(task({ stage: "analysis", state: "running", step: "processing" }), t)).toBe(
      "rework.imports.stepper.hint.processing",
    );
    expect(importPhaseHintFor(task({ stage: "analysis", state: "succeeded" }), t)).toBe(
      "rework.imports.stepper.hint.done",
    );
    expect(importPhaseHintFor(task({ stage: "upload", state: "succeeded" }), t)).toBe(
      "rework.imports.stepper.hint.doneUpload",
    );
    // Held on the user's answer: the panel words that line itself.
    expect(importPhaseHintFor(task({ stage: "decision", state: "running" }), t)).toBeNull();
  });

  // The card is read by someone importing a file, not by someone learning what
  // the product is called. Naming it explains nothing they need and dates every
  // string the day the product is renamed or white-labelled.
  it("never names the product in anything the import card shows", () => {
    const strings = (node: unknown): string[] =>
      typeof node === "string"
        ? [node]
        : typeof node === "object" && node !== null
          ? Object.values(node).flatMap(strings)
          : [];

    for (const locale of [fr, en]) {
      for (const text of strings(locale.rework.imports)) {
        expect(text, `"${text}" names the product`).not.toMatch(/\bFred\b/);
      }
    }
  });

  it("has a hint for every phase, in both languages", () => {
    for (const locale of [fr, en]) {
      const hints = locale.rework.imports.stepper.hint as Record<string, string>;
      for (const key of [...IMPORT_PHASES, "done", "doneUpload"]) {
        expect(hints[key], `no hint for "${key}"`).toBeTruthy();
      }
    }
  });

  // Unplaced, a late step fell to the first phase: a file showing "Indexing"
  // went back to "Document preparation", the one thing a stepper must never
  // do. Walked over both an import's own steps and the revectorize ones that
  // can reach this panel.
  it("never walks backwards on a step the server actually emits", () => {
    const order = ["listed", "uploading", "processing", "indexing", "vectorized", "done"];
    const walked = order.map((step) => importPhaseIndex(task({ stage: "analysis", state: "running", step })));

    expect(walked).toEqual([...walked].sort((a, b) => a - b));
  });

  it("places every step the labels know about", () => {
    // A step named in one place and forgotten in the other is exactly how the
    // stepper started reporting a phase the file had already left.
    for (const step of INGESTION_STEPS) {
      if (step === "done") continue; // handled before the table is consulted
      expect(SERVER_PHASE[step], `"${step}" has no phase`).toBeDefined();
    }
  });
});
