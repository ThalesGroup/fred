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

// A failure has to stay on screen, say what happened in words the reader can
// act on, and offer a way out — but only a way out that actually works. The
// real TaskCard renders here, unmocked: what the reader ends up seeing is the
// whole point of this file.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { taskSlice, uploadFailed, uploadStarted } from "../../../../features/tasks/taskSlice";
import { clearHeldImports, runImport } from "../../../../features/imports/importRun";
import { forgetCachedRecord, unfinishedImports } from "../../../../features/imports/unfinishedImports";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: vi.fn() }) }));
vi.mock("../../../../features/tasks/useTaskAcknowledgement", () => ({
  useTaskAcknowledgement: () => ({ acknowledge: vi.fn(), isAcknowledging: () => false }),
}));

// One request that answers with a per-file failure, so a real run leaves a
// real failed entry behind — held file included.
const streamMock = vi.fn();
vi.mock("../../../../../slices/streamDocumentUpload", () => ({
  leafFileName: (file: File) => file.name.split("/").pop() || file.name,
  streamUploadOrProcessDocument: (...args: unknown[]) => streamMock(...args),
}));

import { ImportPanel } from "./ImportPanel";

let container: HTMLDivElement;
let root: Root;
let store: ReturnType<typeof makeStore>;

const makeStore = () => configureStore({ reducer: { tasks: taskSlice.reducer } });

function mount() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(
      <Provider store={store}>
        <ImportPanel teamId="team-1" />
      </Provider>,
    );
  });
  // Open it — collapsed, the rail shows nothing but its button.
  act(() => {
    container.querySelector("button")!.click();
  });
}

beforeEach(() => {
  window.localStorage.clear();
  // The record is held in memory between reads; each test starts from a fresh
  // page load, not a cleared key.
  forgetCachedRecord();
  clearHeldImports();
  streamMock.mockReset();
  store = makeStore();
  mount();
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

const cardText = () => container.querySelector('[class*="card"]')?.textContent ?? "";
const retryButton = () =>
  [...container.querySelectorAll("button")].find((b) => b.getAttribute("aria-label") === "rework.imports.retry.action");

/** A real import whose single file the server rejects. */
async function importThatFails(error = "Storage quota exceeded for team fredlab: limit is 10 GB.") {
  streamMock.mockImplementation(async (_files, _mode, _meta, _discover, onFailed) => {
    onFailed("report.pdf", error);
    return [];
  });
  await act(async () => {
    await runImport([{ requestMetadata: { tags: ["tag-1"] }, files: [new File(["x"], "report.pdf")] }], {
      dispatch: store.dispatch,
      uploadMode: "process",
      teamId: "team-1",
      onError: () => {},
    });
  });
}

describe("ImportPanel — a failed file", () => {
  it("stays listed, with the cause put in the reader's words", async () => {
    await importThatFails();

    expect(cardText()).toContain("report.pdf");
    // Not the backend's sentence about limits and byte counts.
    expect(cardText()).toContain("rework.imports.failure.quotaExceeded");
    expect(cardText()).not.toContain("10 GB");
  });

  it("says so plainly when the failure came with no cause at all", async () => {
    // "Execution failed" is the backend admitting it has nothing; dressing it
    // up as a cause would be inventing one.
    await importThatFails("Execution failed");

    expect(cardText()).toContain("rework.imports.failure.unreported");
  });

  it("offers a retry while the browser still holds the file", async () => {
    await importThatFails();

    expect(retryButton()).toBeDefined();
    expect(container.textContent).not.toContain("rework.imports.retry.unavailable");
  });

  it("sends the file again on retry, under the same entry", async () => {
    await importThatFails();
    const entryId = Object.keys(store.getState().tasks.byId)[0];

    streamMock.mockImplementation(async (_files, _mode, _meta, discover) => {
      discover({ taskId: "task-1", documentUid: "doc-1", filename: "report.pdf" });
      return [];
    });
    await act(async () => {
      retryButton()!.click();
    });
    // The click starts a promise the handler does not await; let it settle.
    await act(async () => {});

    // The entry became the ingestion task rather than a second row beside it.
    expect(store.getState().tasks.byId[entryId]).toBeUndefined();
    expect(store.getState().tasks.byId["task-1"].stage).toBe("analysis");
    expect(Object.keys(store.getState().tasks.byId)).toHaveLength(1);
  });

  it("stops expecting a failure the user dismissed", async () => {
    await importThatFails();
    expect(unfinishedImports()).toHaveLength(1);

    const buttons = [...container.querySelectorAll("button")];
    const dismiss = buttons[buttons.length - 1];
    act(() => {
      dismiss.click();
    });

    // Otherwise it comes back as "did not arrive" on every later visit, long
    // after the user said they were done with it.
    expect(unfinishedImports()).toEqual([]);
    // And it goes now, rather than lingering for the tray's eviction window:
    // dismissing it means being done with it.
    expect(container.querySelector('[class*="card"]')).toBeNull();
  });

  it("asks for the file again instead of offering a retry that cannot work", () => {
    // A reload leaves the store's failed entry (rehydrated or still there) with
    // no file behind it — the browser cannot re-read what it no longer holds.
    act(() => {
      store.dispatch(uploadStarted({ localId: "local-1", filename: "orphan.pdf", teamId: "team-1" }));
      store.dispatch(uploadFailed({ localId: "local-1", error: "Failed to fetch" }));
    });

    expect(retryButton()).toBeUndefined();
    expect(container.textContent).toContain("rework.imports.retry.unavailable");
  });

  it("keeps the failure listed across leaving the page, and leaves the other files alone", async () => {
    streamMock.mockImplementation(async (_files, _mode, _meta, discover, onFailed) => {
      onFailed("report.pdf", "Execution failed");
      discover({ taskId: "task-ok", documentUid: "doc-ok", filename: "notes.md" });
      return [];
    });
    await act(async () => {
      await runImport(
        [
          {
            requestMetadata: { tags: ["tag-1"] },
            files: [new File(["x"], "report.pdf"), new File(["y"], "notes.md")],
          },
        ],
        {
          dispatch: store.dispatch,
          uploadMode: "process",
          teamId: "team-1",
          onError: () => {},
        },
      );
    });

    act(() => {
      root.unmount();
    });
    container.remove();
    mount();

    expect(container.textContent).toContain("report.pdf");
    expect(container.textContent).toContain("rework.imports.failure.unreported");
    // The file that went through is untouched by its neighbour's failure.
    expect(store.getState().tasks.byId["task-ok"].state).toBe("pending");
    expect(store.getState().tasks.byId["task-ok"].error).toBeNull();
  });
});
