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

// Dismissal is explicit only: an outside (backdrop) click never closes the
// drawer, the cancel button always does, and Escape only while nothing is picked.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  // Renders the count too: the action button's whole job is to say how many
  // files it is about to import.
  useTranslation: () => ({
    t: (key: string, o?: { count?: number }) => (o?.count ? `${key}:${o.count}` : key),
    i18n: { language: "en" },
  }),
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
vi.mock("../../../../../slices/streamDocumentUpload", () => ({
  leafFileName: (file: File) => file.name.split("/").pop() || file.name,
  streamUploadOrProcessDocument: vi.fn(),
}));
vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  // Precheck answers "allowed" so saves proceed; the denial path has its own
  // coverage in DocumentUploadDrawer.quotaPrecheck.test.tsx.
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

function button(label: string) {
  return [...container.querySelectorAll("button")].find((b) => b.textContent === label);
}

function pressEscape() {
  act(() => {
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
  });
}

describe("DocumentUploadDrawer dismissal", () => {
  it("stays open on an outside click and closes on cancel", () => {
    const onClose = vi.fn();
    render(<DocumentUploadDrawer isOpen onClose={onClose} initialFiles={[new File(["a"], "a.pdf")]} />);

    const overlay = container.querySelector('[role="dialog"]')?.parentElement as HTMLElement;
    act(() => {
      overlay.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    expect(onClose).not.toHaveBeenCalled();

    act(() => {
      button("documentLibrary.cancel")?.click();
    });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("ignores Escape once files are selected", () => {
    const onClose = vi.fn();
    render(<DocumentUploadDrawer isOpen onClose={onClose} initialFiles={[new File(["a"], "a.pdf")]} />);

    pressEscape();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("closes on Escape while nothing is selected", () => {
    const onClose = vi.fn();
    render(<DocumentUploadDrawer isOpen onClose={onClose} />);

    pressEscape();
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
