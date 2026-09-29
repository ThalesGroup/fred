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

// The name question at Save: the drawer asks the destination folder what it
// already holds, before a single byte leaves. Nothing is sent until every
// conflict has an answer; a file the user chooses to keep is never uploaded at
// all; and a conflict the server finds anyway, after the drawer asked, is
// reported as a question rather than as a failure.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const probe = vi.hoisted(() => ({
  /** Files actually handed to the upload stream, with the metadata they carry. */
  sent: [] as { names: string[]; metadata: Record<string, unknown> }[],
  nameCheck: vi.fn(),
  /** Leaf names the fake server reports as conflicting at write time. */
  lateConflicts: [] as string[],
  showError: vi.fn(),
  showInfo: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-redux", () => ({ useDispatch: () => () => {} }));
vi.mock("react-dropzone", () => ({
  useDropzone: () => ({ getRootProps: () => ({}), getInputProps: () => ({}), isDragActive: false }),
}));
vi.mock("@shared/utils/Portal", () => ({ Portal: ({ children }: { children: React.ReactNode }) => children }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: probe.showError, showInfo: probe.showInfo }),
}));
vi.mock("@shared/molecules/Select/Select", () => ({ default: () => null }));
vi.mock("@shared/molecules/UploadWarningBanner/UploadWarningBanner", () => ({ default: () => null }));
vi.mock("@hooks/useTeamCapabilities.ts", () => ({ useTeamCapabilities: () => ({ canUpdateResources: true }) }));
vi.mock("../../../../../slices/streamDocumentUpload", () => ({
  leafFileName: (file: File) => file.name.split("/").pop() || file.name,
  streamUploadOrProcessDocument: (
    files: File[],
    _mode: string,
    metadata: Record<string, unknown>,
    _onTask: unknown,
    _onFailed: unknown,
    onResolved?: (filename: string) => void,
    onConflicted?: (filename: string) => void,
  ) => {
    probe.sent.push({ names: files.map((f) => f.name), metadata });
    for (const file of files) {
      const leaf = file.name.split("/").pop() || file.name;
      if (probe.lateConflicts.includes(leaf)) onConflicted?.(leaf);
      else onResolved?.(leaf);
    }
    return Promise.resolve([]);
  },
}));
vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useImportNameCheckKnowledgeFlowV1DocumentsNameCheckPostMutation: () => [probe.nameCheck],
  useQuotaPrecheckKnowledgeFlowV1QuotaPrecheckPostMutation: () => [
    () => ({ unwrap: () => Promise.resolve({ allowed: true }) }),
  ],
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useGetTeamQuery: () => ({ data: undefined }),
}));
vi.mock("../../../../features/tasks/taskSlice", () => ({
  taskRegistered: (payload: unknown) => ({ type: "tasks/taskRegistered", payload }),
}));

import { DocumentUploadDrawer } from "./DocumentUploadDrawer";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  probe.sent.length = 0;
  probe.lateConflicts.length = 0;
  probe.nameCheck.mockReset();
  probe.showError.mockClear();
  probe.showInfo.mockClear();
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

function answering(conflicts: { tag_id: string; names: string[] }[]) {
  probe.nameCheck.mockReturnValue({ unwrap: () => Promise.resolve({ conflicts }) });
}

function renderDrawer(names: string[]) {
  act(() => {
    root.render(
      <DocumentUploadDrawer
        isOpen
        onClose={() => {}}
        teamId="team-a"
        metadata={{ tags: ["tag-base"] }}
        initialFiles={names.map((name) => new File(["x"], name))}
      />,
    );
  });
}

function button(label: string): HTMLButtonElement {
  const found = [...container.querySelectorAll("button")].find((b) => b.textContent?.includes(label));
  if (!found) throw new Error(`no button labelled ${label}`);
  return found;
}

async function click(target: HTMLButtonElement) {
  await act(async () => {
    target.click();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

const sentNames = () => probe.sent.flatMap((request) => request.names);

describe("DocumentUploadDrawer name conflicts", () => {
  it("asks the destination folder about every name, once", async () => {
    answering([]);
    renderDrawer(["a.pdf", "b.pdf"]);

    await click(button("documentLibrary.save"));

    expect(probe.nameCheck).toHaveBeenCalledTimes(1);
    expect(probe.nameCheck).toHaveBeenCalledWith({
      importNameCheckRequest: { destinations: [{ tag_id: "tag-base", names: ["a.pdf", "b.pdf"] }] },
    });
  });

  it("no conflict means no question at all", async () => {
    answering([]);
    renderDrawer(["a.pdf", "b.pdf"]);

    await click(button("documentLibrary.save"));

    expect(container.textContent).not.toContain("documentLibrary.conflictsTitle");
    expect(sentNames()).toEqual(["a.pdf", "b.pdf"]);
  });

  it("some conflicts: nothing is sent until they are answered", async () => {
    answering([{ tag_id: "tag-base", names: ["a.pdf"] }]);
    renderDrawer(["a.pdf", "b.pdf"]);

    await click(button("documentLibrary.save"));

    // The question names the conflicting file, and the non-conflicting one is
    // not sent ahead of the answer — one import, one decision point.
    expect(container.textContent).toContain("documentLibrary.conflictsTitle");
    expect(probe.sent).toEqual([]);
    expect(button("documentLibrary.save").hasAttribute("disabled")).toBe(true);

    await click(button("documentLibrary.conflictOverwriteAll"));
    await click(button("documentLibrary.save"));

    expect(sentNames()).toEqual(["a.pdf", "b.pdf"]);
    expect(probe.sent[0].metadata.conflict_decisions).toEqual({ "a.pdf": "overwrite" });
  });

  it("a file the user keeps is never uploaded", async () => {
    answering([{ tag_id: "tag-base", names: ["a.pdf"] }]);
    renderDrawer(["a.pdf", "b.pdf"]);

    await click(button("documentLibrary.save"));
    await click(button("documentLibrary.conflictKeepAll"));
    await click(button("documentLibrary.save"));

    // Sending its bytes for the server to refuse is exactly the transfer the
    // question exists to avoid.
    expect(sentNames()).toEqual(["b.pdf"]);
    expect(probe.sent[0].metadata.conflict_decisions).toBeUndefined();
    expect(probe.showInfo).toHaveBeenCalledWith(
      expect.objectContaining({ detail: "documentLibrary.conflictKeptSummary" }),
    );
  });

  it("all conflicts kept: the import sends nothing", async () => {
    answering([{ tag_id: "tag-base", names: ["a.pdf", "b.pdf"] }]);
    renderDrawer(["a.pdf", "b.pdf"]);

    await click(button("documentLibrary.save"));
    await click(button("documentLibrary.conflictKeepAll"));
    await click(button("documentLibrary.save"));

    expect(probe.sent).toEqual([]);
    expect(probe.showError).not.toHaveBeenCalled();
  });

  it("each file can be answered on its own", async () => {
    answering([{ tag_id: "tag-base", names: ["a.pdf", "b.pdf"] }]);
    renderDrawer(["a.pdf", "b.pdf"]);

    await click(button("documentLibrary.save"));

    // Scoped to the conflict panel: the file list above it has a row per file too.
    const panel = container.querySelector('[aria-labelledby="upload-conflicts-title"]')!;
    const rowFor = (name: string) => [...panel.querySelectorAll("li")].find((li) => li.textContent?.startsWith(name))!;
    const rowButton = (name: string, label: string) =>
      [...rowFor(name).querySelectorAll("button")].find((b) => b.textContent?.includes(label))!;

    await click(rowButton("a.pdf", "documentLibrary.conflictOverwrite"));
    // One answered, one still open: Save stays out of reach.
    expect(button("documentLibrary.save").hasAttribute("disabled")).toBe(true);

    await click(rowButton("b.pdf", "documentLibrary.conflictKeep"));
    await click(button("documentLibrary.save"));

    expect(sentNames()).toEqual(["a.pdf"]);
    expect(probe.sent[0].metadata.conflict_decisions).toEqual({ "a.pdf": "overwrite" });
  });

  it("a conflict appearing after the question is reported as a question, not a failure", async () => {
    answering([]);
    probe.lateConflicts.push("b.pdf");
    renderDrawer(["a.pdf", "b.pdf"]);

    await click(button("documentLibrary.save"));

    expect(sentNames()).toEqual(["a.pdf", "b.pdf"]);
    expect(probe.showError).not.toHaveBeenCalled();
    expect(probe.showInfo).toHaveBeenCalledWith(expect.objectContaining({ detail: "documentLibrary.conflictLate" }));
  });

  it("a name-check transport error does not block the import", async () => {
    // The question only exists to save a transfer; the upload re-checks and
    // reports whatever it finds.
    probe.nameCheck.mockReturnValue({ unwrap: () => Promise.reject(new Error("503")) });
    renderDrawer(["a.pdf"]);

    await click(button("documentLibrary.save"));

    expect(sentNames()).toEqual(["a.pdf"]);
    expect(container.textContent).not.toContain("documentLibrary.conflictsTitle");
  });
});
