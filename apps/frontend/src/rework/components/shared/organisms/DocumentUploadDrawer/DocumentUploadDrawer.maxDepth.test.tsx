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

// Depth guardrail (#2355): a file whose destination folder + own subdirectory
// chain would exceed MAX_FOLDER_DEPTH must be kept out of the drawer's list —
// out of a seeded drop silently (the seeding surface already toasted), and out
// of an in-drawer drop with a toast. Kept separate from the nested-folder save
// coverage (DocumentUploadDrawer.nestedFolders.test.tsx).

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const probe = vi.hoisted(() => ({
  showError: vi.fn(),
  dropzoneOptions: null as null | { onDrop?: (accepted: File[]) => void },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-redux", () => ({ useDispatch: () => () => {} }));
vi.mock("react-dropzone", () => ({
  useDropzone: (options: { onDrop?: (accepted: File[]) => void }) => {
    probe.dropzoneOptions = options;
    return { getRootProps: () => ({}), getInputProps: () => ({}), isDragActive: false };
  },
}));
vi.mock("@shared/utils/Portal", () => ({ Portal: ({ children }: { children: React.ReactNode }) => children }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: probe.showError }) }));
vi.mock("@shared/molecules/Select/Select", () => ({ default: () => null }));
vi.mock("@shared/molecules/UploadWarningBanner/UploadWarningBanner", () => ({ default: () => null }));
vi.mock("@hooks/useTeamCapabilities.ts", () => ({ useTeamCapabilities: () => ({ canUpdateResources: true }) }));
vi.mock("../../../../../slices/streamDocumentUpload", () => ({
  streamUploadOrProcessDocument: () => Promise.resolve([]),
}));
vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useGetTeamQuery: () => ({ data: undefined }),
}));
vi.mock("../../../../features/tasks/taskSlice", () => ({
  taskRegistered: (payload: unknown) => ({ type: "tasks/taskRegistered", payload }),
}));

import { DocumentUploadDrawer } from "./DocumentUploadDrawer";
import { MAX_FOLDER_DEPTH } from "./droppedPaths";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  probe.showError.mockClear();
  probe.dropzoneOptions = null;
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

/** A file sitting under `dirs` dropped-folder levels. */
function fileAtDepth(name: string, dirs: number): File {
  const file = new File(["x"], name);
  if (dirs > 0) {
    const chain = Array.from({ length: dirs }, (_, i) => `d${i}`).join("/");
    Object.defineProperty(file, "path", { value: `/${chain}/${name}` });
  }
  return file;
}

describe("DocumentUploadDrawer depth guardrail", () => {
  it("filters too-deep files out of the seed, counting the destination folder's depth", () => {
    render(
      <DocumentUploadDrawer
        isOpen
        onClose={() => {}}
        destinationPath="CIR/Sub"
        ensureFolderPath={async () => null}
        initialFiles={[fileAtDepth("ok.pdf", MAX_FOLDER_DEPTH - 2), fileAtDepth("deep.pdf", MAX_FOLDER_DEPTH - 1)]}
      />,
    );

    expect(container.textContent).toContain("ok.pdf");
    expect(container.textContent).not.toContain("deep.pdf");
  });

  it("rejects a too-deep in-drawer drop with a toast, keeping files within the cap", () => {
    render(<DocumentUploadDrawer isOpen onClose={() => {}} ensureFolderPath={async () => null} />);

    act(() => {
      probe.dropzoneOptions?.onDrop?.([
        fileAtDepth("ok.pdf", MAX_FOLDER_DEPTH),
        fileAtDepth("deep.pdf", MAX_FOLDER_DEPTH + 1),
      ]);
    });

    expect(container.textContent).toContain("ok.pdf");
    expect(container.textContent).not.toContain("deep.pdf");
    expect(probe.showError).toHaveBeenCalledWith(expect.objectContaining({ summary: "documentLibrary.tooDeepTitle" }));
  });
});
