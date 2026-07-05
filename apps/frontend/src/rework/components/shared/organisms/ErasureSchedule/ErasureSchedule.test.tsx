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

// CTRLP-12 (design#1): the provable-erasure surface must never read a failed or
// cancelled erasure as "Erased", and must surface a repeatedly-failing (stalled)
// erasure. `t` is mocked to echo its key, so we assert on which key each row uses.

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
    refetch: () => undefined,
  }),
}));
vi.mock("@rework/features/tasks/useRefetchOnTaskSuccess", () => ({
  useRefetchOnTaskSuccess: () => undefined,
}));
vi.mock("@shared/atoms/TaskStateBadge/TaskStateBadge", () => ({
  TaskStateBadge: ({ state }: { state: string }) => <span data-badge={state} />,
}));
vi.mock("@shared/atoms/TaskProgressBar/TaskProgressBar", () => ({
  TaskProgressBar: () => <span data-progress />,
}));

import ErasureSchedule from "./ErasureSchedule";

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
  return renderToStaticMarkup(<ErasureSchedule scope="platform" />);
}

describe("ErasureSchedule completed-row labelling", () => {
  it("labels a succeeded erasure 'erased'", () => {
    h.tasks = [task({ task_id: "s1", state: "succeeded" })];
    const html = render();
    expect(html).toContain("rework.erasureSchedule.erasedOn");
    expect(html).not.toContain("rework.erasureSchedule.failedOn");
  });

  it("labels a FAILED erasure 'failed', never 'erased'", () => {
    h.tasks = [task({ task_id: "s2", state: "failed" })];
    const html = render();
    expect(html).toContain("rework.erasureSchedule.failedOn");
    expect(html).not.toContain("rework.erasureSchedule.erasedOn");
  });

  it("labels a CANCELLED erasure 'cancelled', never 'erased'", () => {
    h.tasks = [task({ task_id: "s3", state: "cancelled" })];
    const html = render();
    expect(html).toContain("rework.erasureSchedule.cancelledOn");
    expect(html).not.toContain("rework.erasureSchedule.erasedOn");
  });
});

describe("ErasureSchedule stalled surfacing", () => {
  it("flags a running erasure whose step is 'stalled'", () => {
    h.tasks = [task({ task_id: "s4", state: "running", step: "stalled", progress: 0.5 })];
    const html = render();
    expect(html).toContain("rework.erasureSchedule.stalled");
  });

  it("does not flag a normally-running erasure", () => {
    h.tasks = [task({ task_id: "s5", state: "running", step: "erasing", progress: 0.5 })];
    const html = render();
    expect(html).not.toContain("rework.erasureSchedule.stalled");
  });
});
