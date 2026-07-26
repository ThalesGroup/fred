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

// Focus: the ack (dismiss) affordance's visibility predicate
// (TASK-EVENT-STREAM-RFC.md §2.10, OBSERV-02 v3 F4) — it must appear only for
// a failed/cancelled task that isn't already acknowledged AND whose caller
// actually wants to offer the action (`onAcknowledge` provided). A regression
// here would either hide the only way to dismiss a real failure, or offer a
// dead button that does nothing.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { TaskTarget, TaskViewModel } from "../../../../features/tasks/taskTypes";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import { TaskCard } from "./TaskCard";

function target(overrides: Partial<TaskTarget> = {}): TaskTarget {
  return { type: "document", id: "doc-1", label: "report.pdf", ...overrides };
}

function vm(overrides: Partial<TaskViewModel> = {}): TaskViewModel {
  return {
    taskId: "t1",
    kind: "ingestion",
    target: target(),
    owner: null,
    localOnly: false,
    state: "running",
    progress: null,
    step: null,
    error: null,
    lastSeq: -1,
    registeredAt: 1000,
    terminalAt: null,
    acknowledgedAt: null,
    warnings: null,
    ...overrides,
  };
}

describe("TaskCard ack affordance visibility", () => {
  it("hides the dismiss button when no onAcknowledge is passed, even for a failed task", () => {
    const html = renderToStaticMarkup(<TaskCard task={vm({ state: "failed", acknowledgedAt: null })} />);
    expect(html).not.toContain("rework.tasks.card.acknowledge");
  });

  it("shows the dismiss button for a failed, unacknowledged task when onAcknowledge is passed", () => {
    const html = renderToStaticMarkup(
      <TaskCard task={vm({ state: "failed", acknowledgedAt: null })} onAcknowledge={() => {}} />,
    );
    expect(html).toContain("rework.tasks.card.acknowledge");
  });

  it("shows the dismiss button for a cancelled, unacknowledged task when onAcknowledge is passed", () => {
    const html = renderToStaticMarkup(
      <TaskCard task={vm({ state: "cancelled", acknowledgedAt: null })} onAcknowledge={() => {}} />,
    );
    expect(html).toContain("rework.tasks.card.acknowledge");
  });

  it("hides the dismiss button once the task is already acknowledged", () => {
    const html = renderToStaticMarkup(
      <TaskCard task={vm({ state: "failed", acknowledgedAt: 12345 })} onAcknowledge={() => {}} />,
    );
    expect(html).not.toContain("rework.tasks.card.acknowledge");
  });

  it("hides the dismiss button for a running task even when onAcknowledge is passed", () => {
    const html = renderToStaticMarkup(<TaskCard task={vm({ state: "running" })} onAcknowledge={() => {}} />);
    expect(html).not.toContain("rework.tasks.card.acknowledge");
  });

  it("hides the dismiss button for a succeeded task", () => {
    const html = renderToStaticMarkup(
      <TaskCard task={vm({ state: "succeeded", acknowledgedAt: null })} onAcknowledge={() => {}} />,
    );
    expect(html).not.toContain("rework.tasks.card.acknowledge");
  });
});
