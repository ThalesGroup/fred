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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const task = {
  taskId: "task-1",
  kind: "ingestion",
  state: "failed",
  progress: null,
  step: null,
  error: "boom",
  registeredAt: new Date().toISOString(),
  acknowledgedAt: null,
  localOnly: true,
  target: { label: "report.pdf" },
};

vi.mock("react-redux", () => ({ useSelector: () => task }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../../../features/tasks/useTaskAcknowledgement", () => ({
  useTaskAcknowledgement: () => ({ acknowledge: vi.fn(), isAcknowledging: () => false }),
}));

import { TaskIndicator } from "./TaskIndicator";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const ACK = "rework.tasks.popover.acknowledge";
const hasAck = (el: Element | null) => [...(el?.querySelectorAll("button") ?? [])].some((b) => b.textContent === ACK);

describe("TaskIndicator", () => {
  let root: Root;
  let container: HTMLDivElement;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("opens the detail with acknowledgement on click", () => {
    act(() => root.render(<TaskIndicator taskId="task-1" />));
    act(() => container.querySelector("button")!.click());
    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog).not.toBeNull();
    expect(hasAck(dialog)).toBe(true);
  });
});
