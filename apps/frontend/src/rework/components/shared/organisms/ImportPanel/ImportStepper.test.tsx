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

/** The four phases' states, in order: transfer, preparation, extraction,
 *  indexing. */
function phases(task: TaskViewModel): string[] {
  const html = renderToStaticMarkup(<ImportStepper task={task} />);
  const states = [...html.matchAll(/data-state="(\w+)"/g)].map((m) => m[1]);
  expect(states).toHaveLength(4);
  return states;
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

  it("stands down once the document is usable", () => {
    // The card's badge and timestamp say what became of it; four ticks would
    // only repeat them.
    expect(renderToStaticMarkup(<ImportStepper task={vm({ stage: "analysis", state: "succeeded" })} />)).toBe("");
  });

  it("hands each row the previous phase's state, which is what colours the rail", () => {
    const html = renderToStaticMarkup(
      <ImportStepper task={vm({ stage: "analysis", state: "running", step: "processing" })} />,
    );
    const rows = [...html.matchAll(/data-state="(\w+)"(?:\s+data-prev="(\w+)")?/g)].map((m) => [m[1], m[2]]);
    expect(rows.map((r) => r[1])).toEqual([undefined, "done", "done", "current"]);
  });
});
