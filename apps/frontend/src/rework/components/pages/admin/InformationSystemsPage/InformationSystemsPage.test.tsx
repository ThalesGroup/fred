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

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { InformationSystemSummary } from "../../../../../slices/rags/ragsOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  summary: { data: undefined, isLoading: false, isError: false, refetch: vi.fn() } as {
    data?: InformationSystemSummary[];
    isLoading: boolean;
    isError: boolean;
    refetch: () => void;
  },
  deleteSystem: vi.fn(() => ({ unwrap: () => Promise.resolve(undefined) })),
  confirmOnConfirm: undefined as (() => void | Promise<void>) | undefined,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key}:${JSON.stringify(opts)}` : key),
    i18n: { language: "en" },
  }),
}));

vi.mock("../../../../../slices/rags/ragsOpenApi", () => ({
  useGetInformationSystemsSummaryQuery: () => h.summary,
  useDeleteInformationSystemMutation: () => [h.deleteSystem, { isLoading: false }],
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}));

// Captures the dialog's onConfirm so the test can trigger it directly,
// mirroring PromptsPage.test.tsx's convention for this same provider.
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({
    showConfirmationDialog: (options: { onConfirm: () => void | Promise<void> }) => {
      h.confirmOnConfirm = options.onConfirm;
    },
  }),
}));

// The create/assign sub-modals have their own dedicated test files — stub
// them here so this file only exercises the list page itself.
vi.mock("./CreateInformationSystemDialog/CreateInformationSystemDialog.tsx", () => ({
  default: () => null,
}));
vi.mock("./DocumentAssignmentModal/DocumentAssignmentModal.tsx", () => ({
  default: () => null,
}));

import InformationSystemsPage from "./InformationSystemsPage";

let container: HTMLDivElement;
let root: Root;

function render() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<InformationSystemsPage />);
  });
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  h.summary = { data: undefined, isLoading: false, isError: false, refetch: vi.fn() };
  h.deleteSystem.mockClear();
  h.confirmOnConfirm = undefined;
});

function system(over: Partial<InformationSystemSummary> & Pick<InformationSystemSummary, "information_system_uid">) {
  return {
    information_system: "crm-legacy",
    library_tag_id: "tag-1",
    ...over,
  } as InformationSystemSummary;
}

describe("InformationSystemsPage loading, error and empty states", () => {
  it("shows the loading state while the summary is loading", () => {
    h.summary = { data: undefined, isLoading: true, isError: false, refetch: vi.fn() };
    render();
    expect(container.textContent).toContain("rework.informationSystems.loading");
  });

  it("shows the service notice when the summary fails to load", () => {
    h.summary = { data: undefined, isLoading: false, isError: true, refetch: vi.fn() };
    render();
    expect(container.textContent).toContain("rework.serviceNotice.ragsServices.title");
  });

  it("shows the empty state with no information systems", () => {
    h.summary = { data: [], isLoading: false, isError: false, refetch: vi.fn() };
    render();
    expect(container.textContent).toContain("rework.informationSystems.empty");
  });
});

describe("InformationSystemsPage table", () => {
  it("renders one row per system with document/similarity/contradiction counts", () => {
    h.summary = {
      data: [
        system({
          information_system_uid: "si-1",
          information_system: "crm-legacy",
          documents: { DAT: [{ document_uid: "doc-1", document_name: "Arch.pdf" }], MEX: [], CMDB: [] },
          assessment: { similarities: 3, contradictions: 1 },
        }),
      ],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
    render();

    expect(container.textContent).toContain("crm-legacy");
    expect(container.textContent).toContain("3");
    expect(container.textContent).toContain("1");
    // documentCount sums across every role — one document in DAT here.
    const docCountButton = Array.from(container.querySelectorAll("button")).find((b) => b.textContent === "1");
    expect(docCountButton).toBeTruthy();
  });
});

describe("InformationSystemsPage delete flow", () => {
  function clickByLabel(label: string) {
    const el = Array.from(container.querySelectorAll("button")).find(
      (b) => b.getAttribute("aria-label") === label || b.getAttribute("title") === label,
    );
    expect(el).toBeTruthy();
    act(() => {
      el?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });
  }

  it("does not call the delete mutation before the confirmation dialog is confirmed", () => {
    h.summary = {
      data: [system({ information_system_uid: "si-1", information_system: "crm-legacy" })],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
    render();

    clickByLabel("rework.informationSystems.table.delete");

    expect(h.confirmOnConfirm).toBeTruthy();
    expect(h.deleteSystem).not.toHaveBeenCalled();
  });

  it("calls the delete mutation with the system's uid once the dialog is confirmed", async () => {
    h.summary = {
      data: [system({ information_system_uid: "si-1", information_system: "crm-legacy" })],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
    render();

    clickByLabel("rework.informationSystems.table.delete");
    await act(async () => {
      await h.confirmOnConfirm?.();
    });

    expect(h.deleteSystem).toHaveBeenCalledTimes(1);
    expect(h.deleteSystem).toHaveBeenCalledWith({ informationSystemUid: "si-1" });
  });
});
