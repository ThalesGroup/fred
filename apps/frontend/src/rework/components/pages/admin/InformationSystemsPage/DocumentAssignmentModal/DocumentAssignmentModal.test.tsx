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

// Regression coverage for the save semantics: `rags-services` has no
// per-document PATCH, only "add these role assignments" / "remove these role
// assignments" — so saving diffs the working selection against the
// assignment the SI had when the modal opened, touching only documents whose
// role actually changed (see DocumentAssignmentModal.tsx's own doc comment
// for why leaving unchanged documents out of both calls is what makes it
// safe to call add before remove).

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { InformationSystemSummary } from "../../../../../../slices/rags/ragsOpenApi";
import type { BrowseDocumentsResponse } from "../../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  browse: vi.fn(),
  browseResult: undefined as BrowseDocumentsResponse | undefined,
  addDocuments: vi.fn(() => ({ unwrap: () => Promise.resolve(undefined) })),
  removeDocuments: vi.fn(() => ({ unwrap: () => Promise.resolve(undefined) })),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key}:${JSON.stringify(opts)}` : key),
    i18n: { language: "en" },
  }),
}));

vi.mock("../../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [
    h.browse,
    { data: h.browseResult, isLoading: false },
  ],
}));

vi.mock("../../../../../../slices/rags/ragsOpenApi", () => ({
  useAddInformationSystemDocumentsMutation: () => [h.addDocuments, { isLoading: false }],
  useRemoveInformationSystemDocumentsMutation: () => [h.removeDocuments, { isLoading: false }],
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}));

import DocumentAssignmentModal from "./DocumentAssignmentModal";

let container: HTMLDivElement;
let root: Root;

function documentMetadata(uid: string, name: string) {
  return { identity: { document_uid: uid, document_name: name } } as BrowseDocumentsResponse["documents"][number];
}

function system(): InformationSystemSummary {
  return {
    information_system_uid: "si-1",
    information_system: "crm-legacy",
    library_tag_id: "tag-1",
    documents: { DAT: [{ document_uid: "doc-1", document_name: "A.pdf" }] },
  } as InformationSystemSummary;
}

function render() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<DocumentAssignmentModal open system={system()} onClose={vi.fn()} onUpdated={vi.fn()} />);
  });
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  document.querySelector("#modal-portal")?.remove();
  h.browse.mockClear();
  h.browseResult = undefined;
  h.addDocuments.mockClear();
  h.removeDocuments.mockClear();
});

// The modal renders entirely through `Portal` (`createPortal` into a
// `#modal-portal` div appended directly to `document.body`, same convention
// as CorpusAuditPage.test.tsx/ConfirmationDialog) — assert against the whole
// document, not the local `container`.
function findRowContaining(text: string): HTMLElement {
  const row = Array.from(document.querySelectorAll(".datatable-row, [class*='datatable-row']")).find((el) =>
    el.textContent?.includes(text),
  ) as HTMLElement | undefined;
  expect(row).toBeTruthy();
  return row!;
}

function pickRoleForRow(row: HTMLElement, roleLabel: string) {
  const trigger = row.querySelector("button[aria-haspopup='listbox']");
  expect(trigger).toBeTruthy();
  act(() => {
    trigger?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
  const option = Array.from(document.querySelectorAll("[role='option']")).find((el) => el.textContent === roleLabel);
  expect(option).toBeTruthy();
  act(() => {
    option?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

function clickSave() {
  const saveButton = Array.from(document.querySelectorAll("button")).find((b) => b.textContent === "common.save");
  expect(saveButton).toBeTruthy();
  act(() => {
    saveButton?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

describe("DocumentAssignmentModal", () => {
  it("browses the SI's own library (not some other tag) on open", () => {
    h.browseResult = { total: 0, documents: [] };
    render();
    expect(h.browse).toHaveBeenCalledWith({
      browseDocumentsByTagRequest: { tag_id: "tag-1", offset: 0, limit: 200 },
    });
  });

  it("pre-selects each document's role from the SI's current assignment", () => {
    h.browseResult = { total: 1, documents: [documentMetadata("doc-1", "A.pdf")] };
    render();
    const row = findRowContaining("A.pdf");
    expect(row.textContent).toContain("DAT");
  });

  it("leaves an unchanged document out of both calls, only touching the diff", async () => {
    h.browseResult = {
      total: 2,
      documents: [documentMetadata("doc-1", "A.pdf"), documentMetadata("doc-2", "B.pdf")],
    };
    render();

    // doc-1 keeps its original DAT role untouched; doc-2 (previously
    // unassigned) gets MEX — only doc-2 should appear in either payload, and
    // since nothing is being revoked, remove should not be called at all.
    pickRoleForRow(findRowContaining("B.pdf"), "MEX");
    clickSave();
    await act(async () => {
      await Promise.resolve();
    });

    expect(h.addDocuments).toHaveBeenCalledWith({
      informationSystemUid: "si-1",
      informationSystemDocumentsAdd: {
        documents: { MEX: [{ document_uid: "doc-2", document_name: "B.pdf" }] },
      },
    });
    expect(h.removeDocuments).not.toHaveBeenCalled();
  });

  it("removes the old role and adds the new one when a document's role changes", async () => {
    h.browseResult = { total: 1, documents: [documentMetadata("doc-1", "A.pdf")] };
    render();

    pickRoleForRow(findRowContaining("A.pdf"), "CMDB");
    clickSave();
    await act(async () => {
      await Promise.resolve();
    });

    expect(h.addDocuments).toHaveBeenCalledWith({
      informationSystemUid: "si-1",
      informationSystemDocumentsAdd: {
        documents: { CMDB: [{ document_uid: "doc-1", document_name: "A.pdf" }] },
      },
    });
    expect(h.removeDocuments).toHaveBeenCalledWith({
      informationSystemUid: "si-1",
      informationSystemDocumentsRemove: { documents: { DAT: ["doc-1"] } },
    });
  });

  it("unassigning a document (role -> none) drops it from the add payload entirely", async () => {
    h.browseResult = { total: 1, documents: [documentMetadata("doc-1", "A.pdf")] };
    render();

    pickRoleForRow(findRowContaining("A.pdf"), "rework.informationSystems.assignDocuments.roleNone");
    clickSave();
    await act(async () => {
      await Promise.resolve();
    });

    expect(h.removeDocuments).toHaveBeenCalledWith({
      informationSystemUid: "si-1",
      informationSystemDocumentsRemove: { documents: { DAT: ["doc-1"] } },
    });
    expect(h.addDocuments).not.toHaveBeenCalled();
  });
});
