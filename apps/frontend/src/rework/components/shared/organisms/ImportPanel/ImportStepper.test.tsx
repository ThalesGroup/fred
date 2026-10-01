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

// The stepper replaced a progress bar that had to invent its own movement. Its
// whole value is that it never claims more than the server said — so what it
// shows for each event the server actually emits is the thing worth pinning.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { TaskViewModel } from "../../../../features/tasks/taskTypes";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

import { ImportStepper } from "./ImportStepper";
import { IMPORT_PHASES } from "../../../../features/imports/importPhases";
import en from "../../../../../locales/en/translation.json";
import fr from "../../../../../locales/fr/translation.json";

function vm(overrides: Partial<TaskViewModel> = {}): TaskViewModel {
  return {
    taskId: "t1",
    kind: "ingestion",
    target: { type: "document", id: "doc-1", label: "report.pdf" },
    owner: null,
    localOnly: false,
    state: "running",
    progress: null,
    step: null,
    error: null,
    lastSeq: -1,
    stage: "upload",
    conflict: null,
    teamId: "team-1",
    registeredAt: 1000,
    terminalAt: null,
    acknowledgedAt: null,
    warnings: null,
    ...overrides,
  };
}

/** The row renders phase, link, phase, link, phase, link, phase — so even
 *  positions are the four phases and odd ones the runs between them. */
function states(task: TaskViewModel): string[] {
  const html = renderToStaticMarkup(<ImportStepper task={task} />);
  const all = [...html.matchAll(/data-state="(\w+)"/g)].map((m) => m[1]);
  expect(all).toHaveLength(7);
  return all;
}

/** The four phases' states, in order: transfer, preparation, extraction,
 *  indexing. */
function phases(task: TaskViewModel): string[] {
  return states(task).filter((_, i) => i % 2 === 0);
}

/** The three runs between them, in order. */
function links(task: TaskViewModel): string[] {
  return states(task).filter((_, i) => i % 2 === 1);
}

describe("ImportStepper", () => {
  it("shows the transfer running and nothing on the server started", () => {
    expect(phases(vm({ stage: "upload", state: "running" }))).toEqual(["current", "pending", "pending", "pending"]);
  });

  it("follows each phase the server names, one at a time", () => {
    const analysing = (step: string) => phases(vm({ stage: "analysis", state: "running", step }));
    expect(analysing("uploading")).toEqual(["done", "current", "pending", "pending"]);
    expect(analysing("processing")).toEqual(["done", "done", "current", "pending"]);
    expect(analysing("indexing")).toEqual(["done", "done", "done", "current"]);
  });

  it("never shows a server phase as started while the file is still going up", () => {
    // The point of separating them: a transferred file is not a usable
    // document, and a file still transferring has reached nothing at all.
    expect(phases(vm({ stage: "upload", state: "pending" })).slice(1)).toEqual(["pending", "pending", "pending"]);
  });

  it("waits on the first server phase before it is named", () => {
    // The hand-off lands before any step event does; claiming extraction then
    // would be guessing.
    expect(phases(vm({ stage: "analysis", state: "running", step: null }))).toEqual([
      "done",
      "current",
      "pending",
      "pending",
    ]);
  });

  it("shows a transferred file as waiting for a worker, with nothing spinning", () => {
    const queued = vm({ stage: "analysis", state: "pending" });
    expect(phases(queued)).toEqual(["done", "waiting", "pending", "pending"]);
    expect(links(queued)).toEqual(["waiting", "pending", "pending"]);
    const html = renderToStaticMarkup(<ImportStepper task={queued} />);
    expect(html).toContain(">pending<");
    expect(html).not.toContain("<svg");
  });

  it("holds the transfer as done, with nothing running, while a name waits on an answer", () => {
    // Nothing is moving: the bytes arrived and the server declined to write.
    expect(phases(vm({ stage: "decision", state: "pending" }))).toEqual(["done", "pending", "pending", "pending"]);
  });

  it("marks the phase that gave up and leaves the ones after it alone", () => {
    expect(phases(vm({ stage: "upload", state: "failed" }))).toEqual(["failed", "pending", "pending", "pending"]);
    expect(phases(vm({ stage: "analysis", state: "failed", step: "processing" }))).toEqual([
      "done",
      "done",
      "failed",
      "pending",
    ]);
  });

  it("closes every phase when a deployment reports done without an indexing event", () => {
    // The no-scheduler path goes uploading → processing → done: the phase it
    // never names must not be left hanging as unreached.
    expect(phases(vm({ stage: "analysis", state: "running", step: "done" }))).toEqual(["done", "done", "done", "done"]);
  });

  it("carries the run feeding the phase in flight in that phase's colour", () => {
    // The eye should follow the work forward rather than stop at the last
    // tick, so the run into the spinner is not painted as another success.
    expect(links(vm({ stage: "analysis", state: "running", step: "processing" }))).toEqual([
      "done",
      "current",
      "pending",
    ]);
  });

  it("draws no run out of a phase that gave up", () => {
    // The transfer and the preparation did happen and stay drawn; nothing ever
    // crossed from extraction to indexing, so nothing is drawn there.
    expect(links(vm({ stage: "analysis", state: "failed", step: "processing" }))).toEqual(["done", "done", "pending"]);
  });

  // The markers are four dots; their names and what they mean live only in the
  // tooltips. A hint missing from a locale shows the user a raw key, which is
  // exactly the failure nobody notices until it ships.
  it.each(["fr", "en"])("explains every phase in %s", (locale) => {
    const hints = (locale === "fr" ? fr : en).rework.imports.stepper.hint as Record<string, string>;
    for (const phase of IMPORT_PHASES) {
      expect(hints[phase], `${locale}: no hint for "${phase}"`).toBeTruthy();
    }
    // One sentence per phase, not a paragraph — the panel holds two or three
    // lines at the tooltip's width.
    for (const text of Object.values(hints)) expect(text.length).toBeLessThan(160);
  });
});
