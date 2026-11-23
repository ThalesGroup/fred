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
import { afterEach, describe, expect, it, vi } from "vitest";

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
const acknowledge = vi.fn();

vi.mock("react-redux", () => ({ useSelector: () => task }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../../../features/tasks/useTaskAcknowledgement", () => ({
  useTaskAcknowledgement: () => ({ acknowledge, isAcknowledging: () => false }),
}));
vi.mock("@shared/utils/viewport.ts", () => ({ viewportHeight: () => 800, viewportWidth: () => 1200 }));

import { TaskDetailPopover } from "./TaskDetailPopover";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const ackButton = (popover: HTMLElement) =>
  [...popover.querySelectorAll("button")].find((b) => b.textContent === "rework.tasks.popover.acknowledge")!;

describe("TaskDetailPopover", () => {
  let root: Root;
  let container: HTMLDivElement;

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    acknowledge.mockReset();
  });

  const render = (anchorTop: number, onClose = () => undefined) => {
    container = document.createElement("div");
    document.body.appendChild(container);
    const anchor = document.createElement("button");
    anchor.getBoundingClientRect = () =>
      ({ top: anchorTop, bottom: anchorTop + 20, left: 100, right: 120, width: 20, height: 20 }) as DOMRect;
    root = createRoot(container);
    act(() => root.render(<TaskDetailPopover taskId="task-1" anchorEl={anchor} open onClose={onClose} />));
    return document.querySelector<HTMLElement>('[role="dialog"]')!;
  };

  it("opens below an anchor with room under it", () => {
    const popover = render(100);
    expect(popover.style.top).toBe("126px");
    expect(popover.style.bottom).toBe("");
  });

  it("opens above a low anchor, held by its bottom edge", () => {
    const popover = render(700);
    expect(popover.style.top).toBe("");
    expect(popover.style.bottom).toBe("106px");
    expect(popover.style.maxHeight).toBe("400px");
  });

  it("closes once the acknowledgement succeeds", async () => {
    acknowledge.mockResolvedValue(true);
    const onClose = vi.fn();
    const popover = render(100, onClose);
    await act(async () => ackButton(popover).click());
    expect(acknowledge).toHaveBeenCalledWith("task-1", "ingestion", true);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("stays open when the acknowledgement fails", async () => {
    acknowledge.mockResolvedValue(false);
    const onClose = vi.fn();
    const popover = render(100, onClose);
    await act(async () => ackButton(popover).click());
    expect(onClose).not.toHaveBeenCalled();
  });
});
