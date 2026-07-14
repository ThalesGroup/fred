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

// The activity surface must never read a failed or cancelled task as done, and
// must surface a repeatedly-failing (stalled) task. `t` is mocked to echo its
// key, so we assert on which key each row uses.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { TaskSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

const h = vi.hoisted(() => ({ tasks: [] as TaskSummary[] }));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useListTasksControlPlaneV1TasksGetQuery: () => ({
    data: { tasks: h.tasks },
    isLoading: false,
    isError: false,
  }),
}));
vi.mock("@shared/atoms/TaskStateBadge/TaskStateBadge", () => ({
  TaskStateBadge: ({ state }: { state: string }) => <span data-badge={state} />,
}));
vi.mock("@shared/atoms/TaskProgressBar/TaskProgressBar", () => ({
  TaskProgressBar: () => <span data-progress />,
}));

import TaskActivity from "./TaskActivity";

function task(over: Partial<TaskSummary> & Pick<TaskSummary, "task_id" | "state">): TaskSummary {
  return {
    kind: "erasure",
    progress: null,
    step: null,
    error: null,
    target: { type: "conversation", id: over.task_id, label: "chat" },
    created_by: "alice",
    team_id: "nb",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    scheduled_for: null,
    ...over,
  } as TaskSummary;
}

function render(): string {
  return renderToStaticMarkup(<TaskActivity scope="platform" />);
}

describe("TaskActivity completed-row labelling", () => {
  it("labels a succeeded task 'completed'", () => {
    h.tasks = [task({ task_id: "s1", state: "succeeded" })];
    const html = render();
    expect(html).toContain("rework.taskActivity.completedOn");
    expect(html).not.toContain("rework.taskActivity.failedOn");
  });

  it("labels a FAILED task 'failed', never 'completed'", () => {
    h.tasks = [task({ task_id: "s2", state: "failed" })];
    const html = render();
    expect(html).toContain("rework.taskActivity.failedOn");
    expect(html).not.toContain("rework.taskActivity.completedOn");
  });

  it("labels a CANCELLED task 'cancelled', never 'completed'", () => {
    h.tasks = [task({ task_id: "s3", state: "cancelled" })];
    const html = render();
    expect(html).toContain("rework.taskActivity.cancelledOn");
    expect(html).not.toContain("rework.taskActivity.completedOn");
  });
});

describe("TaskActivity stalled surfacing", () => {
  it("flags a running task whose step is 'stalled'", () => {
    h.tasks = [task({ task_id: "s4", state: "running", step: "stalled", progress: 0.5 })];
    const html = render();
    expect(html).toContain("rework.taskActivity.stalled");
  });

  it("does not flag a normally-running task", () => {
    h.tasks = [task({ task_id: "s5", state: "running", step: "erasing", progress: 0.5 })];
    const html = render();
    expect(html).not.toContain("rework.taskActivity.stalled");
  });
});

// AUTHZ-07 Step 3 — the migration terminal result must be observable, durable,
// and never read as a silent success when partial.

function migrationTask(over: Partial<TaskSummary> & Pick<TaskSummary, "task_id" | "state">): TaskSummary {
  return task({ kind: "migration", target: { type: "platform_import", id: "imp-1", label: "demo.zip" }, ...over });
}

const CLEAN_RESULT = {
  import_id: "imp-1",
  source_platform: "swift",
  identities_created: 15,
  users_processed: 15,
  users_skipped: [],
  teams_imported: 3,
  teams_skipped: 0,
  teams_provisioned: 3,
  team_roles_granted: 14,
  team_roles_skipped: 0,
  platform_roles_granted: 2,
  agents_imported: 4,
  agents_skipped: 0,
  agents_gap: 0,
  tags_imported: 2,
  tags_skipped: 0,
  docs_imported: 1,
  docs_skipped: 0,
  warnings: [] as string[],
};

describe("TaskActivity migration result (AUTHZ-07 Step 3)", () => {
  it("renders a clean success with no 'with warnings' flag", () => {
    h.tasks = [
      migrationTask({
        task_id: "m1",
        state: "succeeded",
        detail: { step_id: "done", processed: 1, total: 1, failed: 0, result: CLEAN_RESULT },
      }),
    ];
    const html = render();
    expect(html).toContain("rework.taskActivity.completedOn");
    expect(html).not.toContain("rework.taskActivity.withWarnings");
  });

  it("explicitly flags a succeeded import that produced warnings, distinct from a clean success", () => {
    h.tasks = [
      migrationTask({
        task_id: "m2",
        state: "succeeded",
        detail: {
          step_id: "done",
          processed: 1,
          total: 1,
          failed: 0,
          result: { ...CLEAN_RESULT, agents_gap: 1, warnings: ["agent x: no swift template for v2.custom"] },
        },
      }),
    ];
    const html = render();
    expect(html).toContain("rework.taskActivity.completedOn");
    expect(html).toContain("rework.taskActivity.withWarnings");
  });

  it("exposes structured counters and warnings inside the accessible disclosure", () => {
    h.tasks = [
      migrationTask({
        task_id: "m3",
        state: "succeeded",
        detail: {
          step_id: "done",
          processed: 1,
          total: 1,
          failed: 0,
          result: { ...CLEAN_RESULT, warnings: ["agent x: no swift template for v2.custom"] },
        },
      }),
    ];
    const html = render();
    // Warnings default the disclosure open, so its content is present without
    // simulating a click (this test harness renders static markup only).
    expect(html).toContain("agent x: no swift template for v2.custom");
    expect(html).toContain("rework.taskActivity.migration.counter.identities_created");
    expect(html).toContain("15");
  });

  it("never shows counters/warnings for a task with no result yet (e.g. still running)", () => {
    h.tasks = [migrationTask({ task_id: "m4", state: "running", progress: 0.4 })];
    const html = render();
    expect(html).not.toContain("rework.taskActivity.migration.detailsTitle");
  });

  it("shows the failed task's error message, never the success text", () => {
    h.tasks = [migrationTask({ task_id: "m5", state: "failed", error: "OpenFGA unreachable" })];
    const html = render();
    expect(html).toContain("OpenFGA unreachable");
    expect(html).toContain("rework.taskActivity.failedOn");
    expect(html).not.toContain("rework.taskActivity.completedOn");
  });

  it("uses the backend label, never a raw task id, when a target is present", () => {
    h.tasks = [migrationTask({ task_id: "m6", state: "succeeded" })];
    const html = render();
    expect(html).toContain("demo.zip");
    expect(html).not.toContain(">m6<");
  });

  it("does not regress a non-migration task (no migration-only markup leaks in)", () => {
    h.tasks = [
      task({
        task_id: "e1",
        state: "succeeded",
        kind: "erasure",
        target: { type: "conversation", id: "e1", label: "chat" },
      }),
    ];
    const html = render();
    expect(html).toContain("rework.taskActivity.completedOn");
    expect(html).not.toContain("rework.taskActivity.migration.detailsTitle");
    expect(html).not.toContain("rework.taskActivity.withWarnings");
  });

  it("renders the disclosure toggle as a native, keyboard-operable button with an accessible name", () => {
    h.tasks = [
      migrationTask({
        task_id: "m7",
        state: "succeeded",
        detail: { step_id: "done", processed: 1, total: 1, failed: 0, result: CLEAN_RESULT },
      }),
    ];
    const html = render();
    // Disclosure.tsx renders a native <button aria-expanded=...>; a native
    // button is keyboard-operable (Enter/Space) without extra wiring, and its
    // visible text content ("Import details") is its accessible name.
    expect(html).toMatch(/<button[^>]*aria-expanded="false"[^>]*>/);
    expect(html).toContain("rework.taskActivity.migration.detailsTitle");
  });
});
