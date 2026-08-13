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

// Coverage for structure-preserving saves: files carrying a dropped-folder
// relative path must upload under the tag `ensureFolderPath` resolves for
// their subdirectory (one resolver call per DISTINCT subdirectory), while
// root-level files keep the destination folder's base metadata — and a
// resolver failure must abort the save before any upload starts, leaving the
// drawer open. Kept separate from DocumentUploadDrawer.initialFiles.test.tsx,
// which covers plain (flat) seeding.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const probe = vi.hoisted(() => ({
  scheduled: [] as { name: string; metadata: Record<string, unknown> }[],
  showError: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-redux", () => ({ useDispatch: () => () => {} }));
vi.mock("react-dropzone", () => ({
  useDropzone: () => ({ getRootProps: () => ({}), getInputProps: () => ({}), isDragActive: false }),
}));
vi.mock("@shared/utils/Portal", () => ({ Portal: ({ children }: { children: React.ReactNode }) => children }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: probe.showError }) }));
vi.mock("@shared/molecules/Select/Select", () => ({ default: () => null }));
vi.mock("@shared/molecules/UploadWarningBanner/UploadWarningBanner", () => ({ default: () => null }));
vi.mock("@hooks/useTeamCapabilities.ts", () => ({ useTeamCapabilities: () => ({ canUpdateResources: true }) }));
vi.mock("../../../../../slices/streamDocumentUpload", () => ({
  streamUploadOrProcessDocument: (file: File, _mode: string, metadata: Record<string, unknown>) => {
    probe.scheduled.push({ name: file.name, metadata });
    return Promise.resolve([]);
  },
}));
vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  // Precheck answers "allowed" so saves proceed; the denial path has its own
  // coverage in DocumentUploadDrawer.quotaPrecheck.test.tsx.
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
  probe.scheduled.length = 0;
  probe.showError.mockClear();
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

function render(ui: React.ReactElement) {
  act(() => {
    root.render(ui);
  });
}

function fileAt(name: string, path?: string): File {
  const file = new File(["x"], name);
  if (path) Object.defineProperty(file, "path", { value: path });
  return file;
}

async function clickSave() {
  const save = [...container.querySelectorAll("button")].find((b) => b.textContent?.includes("documentLibrary.save"));
  if (!save) throw new Error("save button not rendered");
  await act(async () => {
    save.click();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

describe("DocumentUploadDrawer nested-folder saves", () => {
  it("uploads each file under its subdirectory's tag, resolving each distinct subdirectory once", async () => {
    const ensureFolderPath = vi.fn(async (segments: string[]) => `tag-${segments.join("-")}`);
    render(
      <DocumentUploadDrawer
        isOpen
        onClose={() => {}}
        metadata={{ tags: ["tag-base"] }}
        ensureFolderPath={ensureFolderPath}
        initialFiles={[
          fileAt("root.pdf", "./root.pdf"),
          fileAt("a.pdf", "/batch/a.pdf"),
          fileAt("b.pdf", "/batch/sub/b.pdf"),
          fileAt("c.pdf", "/batch/sub/c.pdf"),
        ]}
      />,
    );

    await clickSave();

    expect(ensureFolderPath.mock.calls.map(([segments]) => segments)).toEqual([["batch"], ["batch", "sub"]]);
    const byName = Object.fromEntries(probe.scheduled.map((s) => [s.name, s.metadata.tags]));
    expect(byName["root.pdf"]).toEqual(["tag-base"]);
    expect(byName["a.pdf"]).toEqual(["tag-batch"]);
    expect(byName["b.pdf"]).toEqual(["tag-batch-sub"]);
    expect(byName["c.pdf"]).toEqual(["tag-batch-sub"]);
  });

  it("shows the subfolder hint only when structured files and a resolver are both present", () => {
    render(
      <DocumentUploadDrawer
        isOpen
        onClose={() => {}}
        ensureFolderPath={async () => null}
        initialFiles={[fileAt("a.pdf", "/batch/a.pdf")]}
      />,
    );
    expect(container.textContent).toContain("documentLibrary.nestedFoldersHint");
    expect(container.textContent).toContain("batch/a.pdf");

    render(<DocumentUploadDrawer isOpen onClose={() => {}} initialFiles={[fileAt("a.pdf", "/batch/a.pdf")]} />);
    expect(container.textContent).not.toContain("documentLibrary.nestedFoldersHint");
  });

  it("filters loose files out of the seed when requireFolderPerFile is set (tagless destination)", async () => {
    render(
      <DocumentUploadDrawer
        isOpen
        onClose={() => {}}
        requireFolderPerFile
        ensureFolderPath={async (segments: string[]) => `tag-${segments.join("-")}`}
        initialFiles={[fileAt("root.pdf", "./root.pdf"), fileAt("a.pdf", "/batch/a.pdf")]}
      />,
    );

    expect(container.textContent).toContain("batch/a.pdf");
    expect(container.textContent).not.toContain("root.pdf");

    await clickSave();
    expect(probe.scheduled.map((s) => s.name)).toEqual(["a.pdf"]);
    expect(probe.scheduled[0].metadata.tags).toEqual(["tag-batch"]);
  });

  it("aborts the save (nothing uploaded, drawer open) when folder resolution fails", async () => {
    const onClose = vi.fn();
    render(
      <DocumentUploadDrawer
        isOpen
        onClose={onClose}
        ensureFolderPath={async () => {
          throw new Error("boom");
        }}
        initialFiles={[fileAt("a.pdf", "/batch/a.pdf")]}
      />,
    );

    await clickSave();

    expect(probe.scheduled).toEqual([]);
    expect(onClose).not.toHaveBeenCalled();
    expect(probe.showError).toHaveBeenCalled();
  });
});
