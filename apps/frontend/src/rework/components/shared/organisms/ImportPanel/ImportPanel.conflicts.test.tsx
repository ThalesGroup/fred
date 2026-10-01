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

// A name taken while the file was on its way is a question, not a failure:
// nothing went wrong and nothing was lost. The answer is Replace or Skip, as a
// file explorer asks it, and it is given here — never in the document table.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { taskSlice, uploadConflicted, uploadStarted } from "../../../../features/tasks/taskSlice";
import { clearHeldImports, runImport } from "../../../../features/imports/importRun";

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

beforeEach(() => {
  clearHeldImports();
  streamMock.mockReset();
  sentMetadata = undefined;
  store = makeStore();
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
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

const byText = (label: string) => [...container.querySelectorAll("button")].find((b) => b.textContent === label);
const replace = () => byText("rework.imports.conflict.replace");
const skip = () => byText("rework.imports.conflict.skip");
const awaitingDecision = () => Object.values(store.getState().tasks.byId).find((vm) => vm.stage === "decision")!;
/** Metadata the last request carried — what the decision actually changes. */
let sentMetadata: Record<string, unknown> | undefined;

/** An import of two files where the server refuses one on the name. */
async function importWithOneConflict() {
  streamMock.mockImplementation(async (_files, _mode, _meta, discover, _onFailed, _onResolved, onConflicted) => {
    onConflicted("report.pdf");
    discover({ taskId: "task-ok", documentUid: "doc-ok", filename: "notes.md" });
    return [];
  });
  await act(async () => {
    await runImport(
      [
        {
          requestMetadata: { tags: ["tag-1"], profile: "standard" },
          files: [new File(["x"], "report.pdf"), new File(["y"], "notes.md")],
        },
      ],
      { dispatch: store.dispatch, uploadMode: "process", teamId: "team-1", onError: () => {} },
    );
  });
}

describe("ImportPanel — a name taken while the file was on its way", () => {
  it("is listed as a question, not an error", async () => {
    await importWithOneConflict();

    const conflicted = awaitingDecision();
    expect(conflicted.state).not.toBe("failed");
    expect(conflicted.error).toBeNull();
    expect(conflicted.conflict).toEqual({ tagId: "tag-1", filename: "report.pdf" });
    expect(container.textContent).toContain("rework.imports.conflict.question");
  });

  it("opens the panel itself, because a question no one sees is not one", async () => {
    // The panel starts collapsed here — no toggle was clicked.
    expect(container.querySelector("aside")!.dataset.expanded).toBe("false");

    await importWithOneConflict();

    expect(container.querySelector("aside")!.dataset.expanded).toBe("true");
  });

  it("leaves the other files of the import alone", async () => {
    await importWithOneConflict();

    expect(store.getState().tasks.byId["task-ok"].stage).toBe("analysis");
    expect(store.getState().tasks.byId["task-ok"].error).toBeNull();
  });

  it("sends the file again with the decision attached when the answer is Replace", async () => {
    await importWithOneConflict();
    const conflictedId = awaitingDecision().taskId;

    streamMock.mockImplementation(async (_files, _mode, metadata: Record<string, unknown>, discover) => {
      sentMetadata = metadata;
      discover({ taskId: "task-replaced", documentUid: "doc-1", filename: "report.pdf" });
      return [];
    });
    await act(async () => {
      replace()!.click();
    });
    await act(async () => {});

    expect(sentMetadata).toMatchObject({
      tags: ["tag-1"],
      profile: "standard",
      conflict_decisions: { "report.pdf": "overwrite" },
    });
    // The same entry became the ingestion task; no second row appeared.
    expect(store.getState().tasks.byId[conflictedId]).toBeUndefined();
    expect(store.getState().tasks.byId["task-replaced"].stage).toBe("analysis");
  });

  it("sends nothing at all when the answer is Skip", async () => {
    await importWithOneConflict();
    streamMock.mockClear();

    await act(async () => {
      skip()!.click();
    });
    await act(async () => {});

    // The point of asking is not to transfer bytes the answer makes useless.
    expect(streamMock).not.toHaveBeenCalled();
    expect(Object.values(store.getState().tasks.byId).some((vm) => vm.stage === "decision")).toBe(false);
  });

  it("asks for the import to be started again when the file is no longer held", () => {
    // What a reload leaves behind: the question, without the file it is about.
    act(() => {
      store.dispatch(uploadStarted({ localId: "local-1", filename: "orphan.pdf", teamId: "team-1" }));
      store.dispatch(uploadConflicted({ localId: "local-1", tagId: "tag-1", filename: "orphan.pdf" }));
      container.querySelector("button")!.click();
    });

    expect(replace()).toBeUndefined();
    expect(skip()).toBeUndefined();
    expect(container.textContent).toContain("rework.imports.retry.unavailable");
  });
});
