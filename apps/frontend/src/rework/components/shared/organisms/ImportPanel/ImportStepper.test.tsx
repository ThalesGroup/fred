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

// The stepper replaced a progress bar that had to invent its own movement,
// because the server reports one coarse step for the whole heavy phase. Its
// whole value is that it never claims more than is known — so what it says in
// each state is the thing worth pinning.

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

/** The two phases' states, in order. Three elements carry `data-state`: the
 *  transfer, the run between them, then the analysis — the run repeats the
 *  phase behind it, so only the first and last are read here. */
function phases(task: TaskViewModel): string[] {
  const html = renderToStaticMarkup(<ImportStepper task={task} />);
  const states = [...html.matchAll(/data-state="(\w+)"/g)].map((m) => m[1]);
  expect(states).toHaveLength(3);
  return [states[0], states[2]];
}

describe("ImportStepper", () => {
  it("shows the transfer running and the analysis not started", () => {
    expect(phases(vm({ stage: "upload", state: "running" }))).toEqual(["current", "pending"]);
  });

  it("shows the transfer done and the analysis running", () => {
    expect(phases(vm({ stage: "analysis", state: "running" }))).toEqual(["done", "current"]);
  });

  it("never shows the analysis as started while the file is still going up", () => {
    // The whole point of the two phases: a transferred file is not a usable
    // document, and a file still transferring has reached nothing at all.
    expect(phases(vm({ stage: "upload", state: "pending" }))[1]).toBe("pending");
  });

  it("holds the transfer as done, not running, while a name waits on an answer", () => {
    // Nothing is moving: the bytes arrived and the server declined to write.
    expect(phases(vm({ stage: "decision", state: "pending" }))).toEqual(["done", "pending"]);
  });

  it("marks the phase that gave up, and leaves the other one alone", () => {
    expect(phases(vm({ stage: "upload", state: "failed" }))).toEqual(["failed", "pending"]);
    expect(phases(vm({ stage: "analysis", state: "failed" }))).toEqual(["done", "failed"]);
  });

  it("stands down once the document is usable", () => {
    // The card's badge and timestamp say what became of it; two ticks would
    // only repeat them.
    expect(renderToStaticMarkup(<ImportStepper task={vm({ stage: "analysis", state: "succeeded" })} />)).toBe("");
  });
});
