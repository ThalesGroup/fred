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

// Coverage for the `initialFiles` prop: files dropped on a folder row (upstream,
// DocumentWorkspace) must arrive pre-listed when the drawer opens, so the user
// only has to pick mode/profile and save — instead of landing on an empty
// dropzone and re-picking the files they just dropped. Kept separate from
// DocumentUploadDrawer.test.tsx, whose scheduleFile contract tests run without
// a DOM.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-redux", () => ({ useDispatch: () => () => {} }));
vi.mock("react-dropzone", () => ({
  useDropzone: () => ({ getRootProps: () => ({}), getInputProps: () => ({}), isDragActive: false }),
}));
vi.mock("@shared/utils/Portal", () => ({ Portal: ({ children }: { children: React.ReactNode }) => children }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({}) }));
vi.mock("@shared/molecules/Select/Select", () => ({ default: () => null }));
// Not under test here — and its bootstrap query (RTK) would need a Redux Provider.
vi.mock("@shared/molecules/UploadWarningBanner/UploadWarningBanner", () => ({ default: () => null }));
vi.mock("@hooks/useTeamCapabilities.ts", () => ({ useTeamCapabilities: () => ({ canUpdateResources: true }) }));
vi.mock("../../../../../slices/streamDocumentUpload", () => ({ streamUploadOrProcessDocument: vi.fn() }));
vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useGetTeamQuery: () => ({ data: undefined }),
}));
vi.mock("../../../../features/tasks/taskSlice", () => ({
  taskRegistered: (payload: unknown) => ({ type: "tasks/taskRegistered", payload }),
}));

import { DocumentUploadDrawer } from "./DocumentUploadDrawer";

let container: HTMLDivElement;
let root: Root;

function render(ui: React.ReactElement) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(ui);
  });
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

describe("DocumentUploadDrawer initialFiles seeding", () => {
  it("opens with the provided files already listed and save enabled", () => {
    render(
      <DocumentUploadDrawer
        isOpen
        onClose={() => {}}
        initialFiles={[new File(["a"], "a.pdf"), new File(["b"], "b.docx")]}
      />,
    );

    expect(container.textContent).toContain("a.pdf");
    expect(container.textContent).toContain("b.docx");
    const save = [...container.querySelectorAll("button")].find((b) => b.textContent?.includes("documentLibrary.save"));
    expect(save?.disabled).toBe(false);
  });

  it("still opens on the empty dropzone without initialFiles", () => {
    render(<DocumentUploadDrawer isOpen onClose={() => {}} />);

    expect(container.textContent).toContain("documentLibrary.dropFiles");
  });
});
