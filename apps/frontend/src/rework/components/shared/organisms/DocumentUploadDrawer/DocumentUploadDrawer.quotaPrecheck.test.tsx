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

// Quota precheck at Save (#2360): ONE request with the batch's declared total
// must reject the whole batch before any tag creation or upload starts — the
// drawer stays open showing the server's numbers — while an "allowed" verdict
// (or a precheck transport error, the check being advisory) lets the save
// proceed. Editing the file list clears a shown denial.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const probe = vi.hoisted(() => ({
  scheduled: [] as string[],
  precheck: vi.fn(),
  ensureFolderPath: vi.fn(),
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
  streamUploadOrProcessDocument: (files: File[]) => {
    for (const file of files) probe.scheduled.push(file.name);
    return Promise.resolve([]);
  },
}));
vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useQuotaPrecheckKnowledgeFlowV1QuotaPrecheckPostMutation: () => [probe.precheck],
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
  probe.precheck.mockReset();
  probe.ensureFolderPath.mockClear();
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

function fileOfSize(name: string, size: number): File {
  const file = new File(["x"], name);
  Object.defineProperty(file, "size", { value: size });
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

const drawer = (
  <DocumentUploadDrawer
    isOpen
    onClose={() => {}}
    teamId="team-a"
    metadata={{ tags: ["tag-base"] }}
    ensureFolderPath={probe.ensureFolderPath}
    initialFiles={[fileOfSize("a.pdf", 60), fileOfSize("b.pdf", 40)]}
  />
);

describe("DocumentUploadDrawer quota precheck at Save", () => {
  it("sends ONE precheck with the batch's declared total and destination", async () => {
    probe.precheck.mockReturnValue({ unwrap: () => Promise.resolve({ allowed: true }) });
    render(drawer);

    await clickSave();

    expect(probe.precheck).toHaveBeenCalledTimes(1);
    expect(probe.precheck).toHaveBeenCalledWith({
      quotaPrecheckRequest: { tags: ["tag-base"], team_id: "team-a", total_size: 100 },
    });
    expect(probe.scheduled).toEqual(["a.pdf", "b.pdf"]);
  });

  it("a denial rejects the whole batch before any tag creation or upload, showing the server's numbers", async () => {
    probe.precheck.mockReturnValue({
      unwrap: () => Promise.resolve({ allowed: false, scope: "team", owner_id: "team-a", current: 950, limit: 1000 }),
    });
    render(drawer);

    await clickSave();

    expect(probe.scheduled).toEqual([]);
    expect(probe.ensureFolderPath).not.toHaveBeenCalled();
    expect(container.textContent).toContain("documentLibrary.storageQuotaExceededTitle");
    // Drawer stayed open (file list still rendered) with Save disabled.
    expect(container.textContent).toContain("a.pdf");
    const save = [...container.querySelectorAll("button")].find((b) => b.textContent?.includes("documentLibrary.save"));
    expect(save?.hasAttribute("disabled")).toBe(true);
  });

  it("a precheck transport error is advisory: the save proceeds to enforcement", async () => {
    probe.precheck.mockReturnValue({ unwrap: () => Promise.reject(new Error("503")) });
    render(drawer);

    await clickSave();

    expect(probe.scheduled).toEqual(["a.pdf", "b.pdf"]);
    expect(container.textContent).not.toContain("documentLibrary.storageQuotaExceededTitle");
  });

  it("removing a file clears a shown denial so the user can retry", async () => {
    probe.precheck.mockReturnValue({
      unwrap: () => Promise.resolve({ allowed: false, scope: "team", owner_id: "team-a", current: 950, limit: 1000 }),
    });
    render(drawer);
    await clickSave();
    expect(container.textContent).toContain("documentLibrary.storageQuotaExceededTitle");

    const removeA = [...container.querySelectorAll("button")].find(
      (b) => b.getAttribute("aria-label") === "Remove a.pdf",
    );
    if (!removeA) throw new Error("remove button not rendered");
    await act(async () => {
      removeA.click();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(container.textContent).not.toContain("documentLibrary.storageQuotaExceededTitle");
  });
});
