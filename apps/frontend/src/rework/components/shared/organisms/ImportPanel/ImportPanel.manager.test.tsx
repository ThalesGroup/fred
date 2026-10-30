// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { taskEventReceived, taskRegistered, taskSlice } from "../../../../features/tasks/taskSlice";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const probe = vi.hoisted(() => ({ write: vi.fn(), error: vi.fn() }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }) }));
vi.mock("@shared/molecules/TaskCard/TaskCard", () => ({
  TaskCard: ({ actions }: { actions: ReactNode }) => <div>{actions}</div>,
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: probe.error }) }));
vi.mock("../../../../features/tasks/useTaskAcknowledgement", () => ({
  useTaskAcknowledgement: () => ({ acknowledge: vi.fn(), isAcknowledging: () => false }),
}));
vi.mock("../../../../features/imports/importRun", () => ({
  retryImport: probe.write,
  resolveConflict: probe.write,
  cancelImport: probe.write,
  resumeUnfinishedImports: probe.write,
  heldImport: () => ({}),
  canCancelImport: () => true,
  releaseHeldImport: vi.fn(),
}));
vi.mock("../../../../features/imports/unfinishedImports", () => ({
  unfinishedImports: () => [
    { entryId: "missing", filename: "missing.pdf", teamId: "team-1", uploadMode: "upload", requestMetadata: {} },
  ],
  forgetUnfinishedImports: vi.fn(),
  noteImportSettled: vi.fn(),
}));
import { ImportPanel } from "./ImportPanel";
let container: HTMLDivElement;
let root: Root;
let store: ReturnType<typeof makeStore>;
const makeStore = () => configureStore({ reducer: { tasks: taskSlice.reducer } });
beforeEach(() => {
  probe.write.mockClear();
  probe.error.mockClear();
  store = makeStore();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(
      <Provider store={store}>
        <ImportPanel teamId="team-1" unavailableReason="Documents unavailable" />
      </Provider>,
    );
  });
  act(() => {
    container.querySelector("button")!.click();
  });
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});
function click(label: string) {
  const button = [...container.querySelectorAll("button")].find(
    (b) => b.getAttribute("aria-label") === label || b.textContent === label,
  );
  expect(button).toBeDefined();
  act(() => button!.click());
}
it("keeps imported-task controls but prevents retry, replacement, cancellation and resend", () => {
  act(() => {
    for (const [taskId, stage] of [
      ["retry", "upload"],
      ["decision", "decision"],
      ["cancel", "upload"],
    ] as const) {
      store.dispatch(
        taskRegistered({
          taskId,
          kind: "ingestion",
          target: { type: "document", id: taskId, label: `${taskId}.pdf` },
          teamId: "team-1",
          stage,
          localOnly: true,
        }),
      );
    }
    store.dispatch(
      taskEventReceived({
        kind: "ingestion",
        task_id: "retry",
        state: "failed",
        seq: 1,
        timestamp: "2026-10-18T00:00:00Z",
        error: "failed",
        progress: 0,
        step: null,
        detail: null,
      }),
    );
  });
  click("rework.imports.retry.action");
  click("rework.imports.conflict.replace");
  click("rework.imports.conflict.skip");
  click("rework.imports.cancel.action");
  click("rework.imports.resend.action");
  const input = container.querySelector('input[type="file"]')!;
  Object.defineProperty(input, "files", { value: [new File(["a"], "missing.pdf")] });
  act(() => {
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(probe.write).not.toHaveBeenCalled();
  expect(probe.error).toHaveBeenCalledTimes(6);
});
