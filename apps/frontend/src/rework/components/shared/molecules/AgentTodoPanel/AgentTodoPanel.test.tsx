// @vitest-environment happy-dom
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

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import en from "../../../../../locales/en/translation.json";
import fr from "../../../../../locales/fr/translation.json";
import type { AgentTodo } from "../../../../utils/agentTodo";
import { AgentTodoPanel } from "./AgentTodoPanel";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: { count?: number }) => (values?.count === undefined ? key : `${key}:${values.count}`),
  }),
}));

vi.mock("@shared/atoms/Icon/Icon", () => ({
  default: ({ type }: { type: string }) => <span data-icon={type} />,
}));

const ACTIVE_TODOS: AgentTodo[] = [
  { content: "Inspect the current behavior", status: "completed" },
  { content: "Build the task panel", status: "in_progress" },
  { content: "Run verification", status: "pending" },
];

describe("AgentTodoPanel presentation", () => {
  it("ships the panel copy in English and French", () => {
    expect(en.rework.agentTodoPanel).toMatchObject({ title: "Tasks" });
    expect(fr.rework.agentTodoPanel).toMatchObject({ title: "Tâches" });
  });

  it("renders mixed task states, the remaining count, and accessible status names", () => {
    const html = renderToStaticMarkup(<AgentTodoPanel sessionId="session-1" todos={ACTIVE_TODOS} />);

    expect(html).toContain('aria-expanded="true"');
    expect(html).toContain("rework.agentTodoPanel.remaining:2");
    expect(html).toContain('data-icon="check_circle"');
    expect(html).toContain('data-icon="sync"');
    expect(html).toContain('data-icon="radio_button_unchecked"');
    expect(html).toContain('aria-label="rework.agentTodoPanel.status.in_progress: Build the task panel"');
    expect(html).toContain("Inspect the current behavior");
  });

  it("disappears when every task is complete", () => {
    const html = renderToStaticMarkup(
      <AgentTodoPanel sessionId="session-1" todos={[{ content: "Finished", status: "completed" }]} />,
    );

    expect(html).toBe("");
  });

  it("presents completed progress while pending work remains", () => {
    const html = renderToStaticMarkup(
      <AgentTodoPanel
        sessionId="session-1"
        todos={ACTIVE_TODOS.map((todo) =>
          todo.status === "in_progress" ? { ...todo, status: "completed" as const } : todo,
        )}
      />,
    );

    expect(html).toContain("rework.agentTodoPanel.remaining:1");
    expect(html).toContain('aria-label="rework.agentTodoPanel.status.completed: Build the task panel"');
    expect(html).not.toContain('data-icon="sync"');
  });

  it("disappears when no work remains", () => {
    expect(
      renderToStaticMarkup(
        <AgentTodoPanel sessionId="session-1" todos={[{ content: "Write the final answer", status: "completed" }]} />,
      ),
    ).toBe("");
  });

  it("renders nothing for an explicit empty snapshot", () => {
    expect(renderToStaticMarkup(<AgentTodoPanel sessionId="session-1" todos={[]} />)).toBe("");
  });
});

describe("AgentTodoPanel disclosure persistence", () => {
  let container: HTMLDivElement;
  let root: Root;

  const render = (sessionId: string, todos: readonly AgentTodo[] = ACTIVE_TODOS) =>
    act(() => {
      root.render(<AgentTodoPanel sessionId={sessionId} todos={todos} />);
    });

  const toggle = () => container.querySelector("button") as HTMLButtonElement;

  beforeEach(() => {
    localStorage.clear();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("restores an explicit choice for the same conversation", () => {
    render("session-a");
    act(() => toggle().click());
    expect(toggle().getAttribute("aria-expanded")).toBe("false");

    act(() => root.unmount());
    root = createRoot(container);
    render("session-a");

    expect(toggle().getAttribute("aria-expanded")).toBe("false");
  });

  it("keeps disclosure preferences isolated by conversation", () => {
    render("session-a");
    act(() => toggle().click());
    expect(toggle().getAttribute("aria-expanded")).toBe("false");

    render("session-b");
    expect(toggle().getAttribute("aria-expanded")).toBe("true");
  });

  it("does not let an explicit preference resurrect an all-complete panel", () => {
    localStorage.setItem("localHook:agentTodoPanelExpanded.session-a", "true");
    render("session-a", [{ content: "Finished", status: "completed" }]);

    expect(container.innerHTML).toBe("");
  });
});
