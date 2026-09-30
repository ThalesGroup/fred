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

// Confirming an import hands the work off and gives the application back. The
// dialog closes on acceptance, not on completion: the transfer is the long
// part, and it carries on afterwards, reported to the panel — which is asked
// to open, so the work is visible rather than hidden behind a collapsed
// trigger.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const probe = vi.hoisted(() => ({
  dispatched: [] as { type: string }[],
  onClose: vi.fn(),
  onUploadComplete: vi.fn(),
  /** One per in-flight request, so the test can hold every transfer open and
   *  release them all at once — several run concurrently. */
  releases: [] as (() => void)[],
  transferStarted: 0,
  registeredTasks: [] as string[],
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-redux", () => ({
  useDispatch: () => (action: { type: string }) => probe.dispatched.push(action),
}));
vi.mock("react-dropzone", () => ({
  useDropzone: () => ({ getRootProps: () => ({}), getInputProps: () => ({}), isDragActive: false }),
}));
vi.mock("@shared/utils/Portal", () => ({ Portal: ({ children }: { children: React.ReactNode }) => children }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({}) }));
vi.mock("@shared/molecules/Select/Select", () => ({ default: () => null }));
vi.mock("@shared/molecules/UploadWarningBanner/UploadWarningBanner", () => ({ default: () => null }));
vi.mock("@hooks/useTeamCapabilities.ts", () => ({ useTeamCapabilities: () => ({ canUpdateResources: true }) }));
vi.mock("../../../../../slices/streamDocumentUpload", () => ({
  leafFileName: (file: File) => file.name.split("/").pop() || file.name,
  streamUploadOrProcessDocument: (files: File[], _mode: string, _metadata: unknown, onTask?: (t: unknown) => void) => {
    probe.transferStarted += 1;
    return new Promise((resolve) => {
      probe.releases.push(() => {
        for (const file of files) {
          probe.registeredTasks.push(file.name);
          onTask?.({ taskId: `task-${file.name}`, documentUid: `uid-${file.name}`, filename: file.name });
        }
        resolve([]);
      });
    });
  },
}));
vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useImportNameCheckKnowledgeFlowV1DocumentsNameCheckPostMutation: () => [
    () => ({ unwrap: () => Promise.resolve({ conflicts: [] }) }),
  ],
  useQuotaPrecheckKnowledgeFlowV1QuotaPrecheckPostMutation: () => [
    () => ({ unwrap: () => Promise.resolve({ allowed: true }) }),
  ],
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useGetTeamQuery: () => ({ data: undefined }),
}));

import { DocumentUploadDrawer } from "./DocumentUploadDrawer";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  probe.dispatched.length = 0;
  probe.registeredTasks.length = 0;
  probe.transferStarted = 0;
  probe.releases.length = 0;
  probe.onClose.mockClear();
  probe.onUploadComplete.mockClear();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

async function saveFifty() {
  const files = Array.from({ length: 50 }, (_, i) => new File(["x"], `file-${i}.pdf`));
  act(() => {
    root.render(
      <DocumentUploadDrawer
        isOpen
        onClose={probe.onClose}
        onUploadComplete={probe.onUploadComplete}
        teamId="team-a"
        metadata={{ tags: ["tag-base"] }}
        initialFiles={files}
      />,
    );
  });
  const save = [...container.querySelectorAll("button")].find((b) =>
    b.textContent?.includes("documentLibrary.importCount"),
  );
  if (!save) throw new Error("save button not rendered");
  await act(async () => {
    save.click();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

/** Let every transfer finish. They run through a bounded pool, so releasing the
 *  in-flight ones starts the next ones — drain until none are left. */
async function finishTheTransfer() {
  await act(async () => {
    for (let round = 0; round < 60 && probe.releases.length; round += 1) {
      const pending = probe.releases.splice(0);
      for (const release of pending) release();
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  });
}

describe("DocumentUploadDrawer hands the import off", () => {
  it("closes while the transfer is still running", async () => {
    await saveFifty();

    // The transfer has started and is deliberately still open.
    expect(probe.transferStarted).toBeGreaterThan(0);
    expect(probe.releases.length).toBeGreaterThan(0);
    // The dialog is already gone: the user has the application back.
    expect(probe.onClose).toHaveBeenCalled();
  });

  it("asks the panel to show itself as it closes", async () => {
    await saveFifty();

    // Otherwise the work carries on behind a collapsed trigger, which reads
    // as nothing happening — the complaint the panel exists to answer.
    expect(probe.dispatched.map((action) => action.type)).toContain("tasks/importPanelOpenRequested");
  });

  it("lists every file in the panel before a byte moves", async () => {
    await saveFifty();

    // Waiting for each file's own transfer would leave most of the import
    // invisible: batches run a few at a time, so the last files sit queued
    // with nothing on screen saying they exist.
    expect(probe.dispatched.filter((a) => a.type === "tasks/uploadStarted").length).toBe(50);
  });

  it("keeps reporting each file to the panel after the dialog is gone", async () => {
    await saveFifty();
    expect(probe.registeredTasks).toEqual([]);

    await finishTheTransfer();

    expect(probe.registeredTasks.length).toBe(50);
    // Each file's entry switches over to its real task as the server names it.
    expect(probe.dispatched.filter((a) => a.type === "tasks/uploadHandedOff").length).toBe(
      probe.registeredTasks.length,
    );
  });

  it("refreshes the folder only once the import is through", async () => {
    await saveFifty();
    expect(probe.onUploadComplete).not.toHaveBeenCalled();

    await finishTheTransfer();

    expect(probe.onUploadComplete).toHaveBeenCalled();
  });
});
