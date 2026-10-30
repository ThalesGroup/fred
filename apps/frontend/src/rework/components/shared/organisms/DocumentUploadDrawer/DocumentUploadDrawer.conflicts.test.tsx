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
// conflict has an answer; a file the user chooses to skip is never uploaded at
// all; and a conflict the server finds anyway, after the drawer asked, is
// reported as a question rather than as a failure.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

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
  dispatched: [] as { type: string; payload?: unknown }[],
  quotaPrecheck: vi.fn(),
  managerPreflight: vi.fn(),
  managerRun: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-redux", () => ({
  useDispatch: () => (action: { type: string; payload?: unknown }) =>
    action.type === "managerPreflight"
      ? { unwrap: () => probe.managerPreflight(action.payload) }
      : probe.dispatched.push(action),
}));
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
vi.mock("../../../../../slices/legacyControlPlane/legacyControlPlaneApiEnhancements", () => ({
  useGetTeamQuery: () => ({ data: undefined }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  enhancedControlPlaneApi: {
    endpoints: { preflight: { initiate: (payload: unknown) => ({ type: "managerPreflight", payload }) } },
  },
}));
vi.mock("../../../../features/imports/managerImportRun", () => ({ runManagerImport: probe.managerRun }));

import { DocumentUploadDrawer } from "./DocumentUploadDrawer";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  probe.sent.length = 0;
  probe.lateConflicts.length = 0;
  probe.nameCheck.mockReset();
  probe.quotaPrecheck.mockReset();
  probe.quotaPrecheck.mockReturnValue({ unwrap: () => Promise.resolve({ allowed: true }) });
  probe.showError.mockClear();
  probe.showInfo.mockClear();
  probe.dispatched.length = 0;
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

it("manager sends clean originals once while conflicts stay visible with replacement disabled", async () => {
  probe.managerRun.mockClear();
  probe.managerPreflight.mockResolvedValue({
    conflicts: ["existing.txt"],
    storage: { uploads_enabled: true, max_file_bytes: 104857600, quota_bytes: 1000, used_bytes: 1, reserved_bytes: 0 },
  });
  act(() =>
    root.render(
      <DocumentUploadDrawer
        isOpen
        onClose={() => {}}
        managerDestination={{ spaceId: "space", folderId: "folder" }}
        initialFiles={[new File(["old"], "existing.txt"), new File(["new"], "new.txt")]}
      />,
    ),
  );
  await click(button("documentLibrary.importCount"));
  expect(probe.managerRun).toHaveBeenCalledTimes(1);
  expect(probe.managerRun.mock.calls[0][2].map((entry: { file: File }) => entry.file.name)).toEqual(["new.txt"]);
  expect(container.textContent).not.toContain("documentLibrary.conflictReplaceAll");
  expect(container.querySelector('[role="group"]')?.textContent).toContain("existing.txt");
  await click(button("documentLibrary.conflictSkipAll"));
  await click(button("documentLibrary.importCount"));
  expect(probe.managerRun).toHaveBeenCalledTimes(1);
  expect(probe.nameCheck).not.toHaveBeenCalled();
  expect(probe.quotaPrecheck).not.toHaveBeenCalled();
  expect(probe.sent).toEqual([]);
});
