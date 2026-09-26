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

// Coverage for "Relaunch ingestion" — the row's "more" menu entry and its
// counterpart in the bulk bar. The action targets documents whose ingestion
// failed or never ran; a document that is already ingested must not offer it,
// and a mixed selection must relaunch only the ones that qualify.

import { act } from "react";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { taskSlice, taskRegistered, taskEventReceived } from "../../../../features/tasks/taskSlice";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// Interpolated counts ride the key so a test can assert the number the bar
// actually renders, which is the eligible count and not the selection size.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { count?: number }) => (opts?.count === undefined ? key : `${key}:${opts.count}`),
    i18n: { language: "en" },
  }),
}));
interface ProcessCall {
  processDocumentsRequest: { files: { document_uid: string; profile?: string }[]; relaunch?: boolean };
}
const processDocuments = vi.hoisted(() =>
  vi.fn((request: ProcessCall) => ({
    unwrap: async () => ({
      workflow_id: "wf-1",
      task_ids: Object.fromEntries(
        request.processDocumentsRequest.files.map((file) => [file.document_uid, `task-${file.document_uid}`]),
      ),
    }),
  })),
);

const doc = (uid: string, name: string, stages: Record<string, string>) => ({
  identity: { document_uid: uid, title: name, document_name: `${name}.pdf`, uploaded_by: null },
  file: { file_type: "pdf", file_size_bytes: 1024 },
  source: { date_added_to_kb: "2026-07-01T00:00:00Z", source_tag: "push" },
  processing: { stages, profile: uid === "uid-raw" ? null : "rich" },
  tags: { tag_ids: ["tag-cir"] },
});

vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  // `scope=team` returns in-flight tasks too, which is how a TEAMMATE's
  // running ingestion ("uid-teammate") becomes visible at all — it is absent
  // from the user-scoped SSE store below.
  useListTasksKnowledgeFlowV1TasksGetQuery: () => ({
    data: {
      tasks: [
        {
          task_id: "old-orphan",
          kind: "ingestion",
          state: "failed",
          updated_at: "2026-07-01T00:00:00Z",
          target: { type: "document", id: "uid-orphan" },
        },
        {
          task_id: "task-2",
          kind: "ingestion",
          state: "running",
          updated_at: "2026-07-02T00:00:00Z",
          target: { type: "document", id: "uid-teammate", label: "Teammate doc" },
        },
      ],
    },
  }),
  useListTagsQuery: () => ({
    data: [{ id: "tag-cir", name: "CIR", path: "", type: "document", item_ids: [] }],
    isLoading: false,
    refetch: () => {},
  }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [
    () => ({
      unwrap: async () => ({
        documents: [
          doc("uid-ready", "Ready doc", { raw: "done", vector: "done" }),
          doc("uid-raw", "Raw doc", {}),
          doc("uid-failed", "Failed doc", { raw: "failed" }),
          doc("uid-running", "Running doc", { raw: "in_progress" }),
          doc("uid-teammate", "Teammate doc", { raw: "in_progress" }),
          doc("uid-orphan", "Unconfirmed doc", { raw: "done", preview: "in_progress" }),
        ],
        total: 6,
      }),
    }),
  ],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [vi.fn()],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [processDocuments],
  useCreateTagMutation: () => [vi.fn()],
  useDeleteTagMutation: () => [vi.fn()],
  useCancelTaskKnowledgeFlowV1TasksTaskIdCancelPostMutation: () => [vi.fn()],
  useUpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutMutation: () => [
    vi.fn(() => ({ unwrap: async () => ({}) })),
  ],
}));
vi.mock("../../../../features/tasks/useRefetchOnTaskSettled", () => ({ useRefetchOnTaskSettled: () => {} }));
vi.mock("../../../../features/tasks/useNotifyOnNewTaskTarget", () => ({ useNotifyOnNewTaskTarget: () => {} }));
vi.mock("../../../../../components/documents/common/useDocumentCommands", () => ({
  useDocumentCommands: () => ({
    previewTarget: null,
    closePreview: () => {},
    preview: () => {},
    download: async () => {},
    toggleRetrievable: async () => {},
    removeFromLibrary: async () => {},
  }),
}));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({ showConfirmationDialog: () => {} }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({}) }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useGetTeamQuery: () => ({ data: { id: "team-1" } }),
  useUsersByIdsQuery: () => ({ data: [] }),
}));
vi.mock("@hooks/useTeamCapabilities.ts", () => ({
  useTeamCapabilities: () => ({ canUpdateResources: true }),
}));
vi.mock("../CreateFolderModal/CreateFolderModal.tsx", () => ({ default: () => null }));
vi.mock("@shared/organisms/DocumentUploadDrawer/DocumentUploadDrawer.tsx", () => ({
  DocumentUploadDrawer: () => null,
}));
vi.mock("@shared/organisms/DocumentViewer/DocumentViewer.tsx", () => ({ DocumentViewer: () => null }));
vi.mock("@shared/molecules/InlineDrawer/InlineDrawer.tsx", () => ({ InlineDrawer: () => null }));

import DocumentWorkspace from "./DocumentWorkspace";

const RELAUNCH_KEY = "rework.resources.action.relaunchIngestion";
const BULK_RELAUNCH_KEY = "rework.resources.bulkActions.relaunchIngestion";

let container: HTMLDivElement;
let root: Root;
const createStore = () => configureStore({ reducer: { tasks: taskSlice.reducer } });
let store: ReturnType<typeof createStore>;

beforeEach(async () => {
  processDocuments.mockClear();
  store = createStore();
  store.dispatch(
    taskRegistered({
      taskId: "task-1",
      kind: "ingestion",
      target: { type: "document", id: "uid-running", label: "Running doc" },
    }),
  );
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(
      <Provider store={store}>
        <DocumentWorkspace teamId="team-1" isPersonalTeam={false} />
      </Provider>,
    );
  });

  // Navigate into "CIR" — its documents only load once it's the current folder.
  const cir = [...container.querySelectorAll("button")].find((b) => b.textContent?.includes("CIR"));
  if (!cir) throw new Error('"CIR" folder row not rendered');
  await act(async () => {
    cir.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  document.querySelectorAll('[role="presentation"]').forEach((el) => el.remove());
});

function click(el: Element | null) {
  act(() => {
    el?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

function moreButtons(): HTMLButtonElement[] {
  return [...container.querySelectorAll(`button[aria-label="rework.resources.action.more"]`)] as HTMLButtonElement[];
}

/** The menu portals into document.body, outside `container`. */
function openMenuLabels(button: HTMLButtonElement): string[] {
  click(button);
  return [...document.querySelectorAll('[role="presentation"] li, [role="presentation"] button')].map(
    (el) => el.textContent ?? "",
  );
}

describe("DocumentWorkspace row menu — relaunch ingestion", () => {
  // Row order matches the mocked `documents` array.
  it("does not offer it on an already-ingested document", () => {
    expect(openMenuLabels(moreButtons()[0]).some((label) => label.includes(RELAUNCH_KEY))).toBe(false);
  });

  it("offers it on a document that was never ingested", () => {
    expect(openMenuLabels(moreButtons()[1]).some((label) => label.includes(RELAUNCH_KEY))).toBe(true);
  });

  it("offers it on a document whose ingestion failed", () => {
    expect(openMenuLabels(moreButtons()[2]).some((label) => label.includes(RELAUNCH_KEY))).toBe(true);
  });

  it("does not offer it while an ingestion is genuinely running", () => {
    expect(openMenuLabels(moreButtons()[3]).some((label) => label.includes(RELAUNCH_KEY))).toBe(false);
  });

  it("does not offer it while a TEAMMATE is ingesting the document", () => {
    expect(openMenuLabels(moreButtons()[4]).some((label) => label.includes(RELAUNCH_KEY))).toBe(false);
  });

  it("does not relaunch processing metadata even with an old failed task and no live task", () => {
    expect(openMenuLabels(moreButtons()[5]).some((label) => label.includes(RELAUNCH_KEY))).toBe(false);
  });

  it("cancels unknown-profile selection without submitting", async () => {
    click(moreButtons()[1]);
    const entry = [...document.querySelectorAll('[role="presentation"] li')].find((el) =>
      el.textContent?.includes(RELAUNCH_KEY),
    );
    click(entry!);
    const dialog = document.querySelector('[role="dialog"]')!;
    expect(dialog).not.toBeNull();
    const cancel = [...dialog.querySelectorAll("button")].find((button) => button.textContent === "common.cancel");
    await act(async () => {
      click(cancel!);
    });
    expect(processDocuments).not.toHaveBeenCalled();
    expect(document.querySelector('[role="dialog"]')).toBeNull();
  });

  it("registers the returned task and preserves the known profile", async () => {
    const item = [...document.querySelectorAll('[role="presentation"] li, [role="presentation"] button')];
    click(moreButtons()[2]);
    const entry = [...document.querySelectorAll('[role="presentation"] li, [role="presentation"] button')]
      .filter((el) => !item.includes(el))
      .find((el) => el.textContent?.includes(RELAUNCH_KEY));
    if (!entry) throw new Error("relaunch entry not found");
    await act(async () => {
      click(entry);
    });

    expect(processDocuments).toHaveBeenCalledOnce();
    const files = processDocuments.mock.calls[0][0].processDocumentsRequest.files;
    expect(files.map((file) => file.document_uid)).toEqual(["uid-failed"]);
    expect(files[0].profile).toBe("rich");
    expect(store.getState().tasks.byId["task-uid-failed"].state).toBe("pending");
    expect(openMenuLabels(moreButtons()[2]).some((label) => label.includes(RELAUNCH_KEY))).toBe(false);
    await act(async () => {
      store.dispatch(
        taskEventReceived({
          kind: "ingestion",
          task_id: "task-uid-failed",
          state: "failed",
          seq: 1,
          timestamp: new Date().toISOString(),
          progress: null,
          step: null,
          error: "failed",
          detail: null,
        }),
      );
    });
    click(moreButtons()[2]);
    expect(openMenuLabels(moreButtons()[2]).some((label) => label.includes(RELAUNCH_KEY))).toBe(true);
  });
});

describe("DocumentWorkspace bulk bar — relaunch ingestion", () => {
  function selectAllRows() {
    const selectAll = container.querySelector('input[type="checkbox"]');
    if (!selectAll) throw new Error("select-all checkbox not rendered");
    act(() => {
      (selectAll as HTMLInputElement).click();
    });
  }

  it("counts only the relaunchable documents of a mixed selection", () => {
    selectAllRows();
    const button = container.querySelector(`button[aria-label="${BULK_RELAUNCH_KEY}:2"]`);

    // Five rows selected — one ingested, one running for us, one running for a
    // teammate, two stuck.
    expect(button).not.toBeNull();
  });

  it("asks for unknown profiles and preserves known profiles in a mixed batch", async () => {
    selectAllRows();
    click(container.querySelector(`button[aria-label="${BULK_RELAUNCH_KEY}:2"]`));
    expect(processDocuments).not.toHaveBeenCalled();
    const dialog = document.querySelector('[role="dialog"]')!;
    const confirm = [...dialog.querySelectorAll("button")].find((button) => button.textContent === RELAUNCH_KEY)!;
    expect(confirm.disabled).toBe(true);
    click(dialog.querySelector('button[aria-haspopup="listbox"]'));
    const medium = [...document.querySelectorAll('[role="presentation"] li')].find((node) =>
      node.textContent?.includes("documentLibrary.profileMedium"),
    );
    expect(medium).toBeDefined();
    click(medium!);
    await act(async () => {
      click(confirm);
    });

    expect(processDocuments).toHaveBeenCalledOnce();
    const files = processDocuments.mock.calls[0][0].processDocumentsRequest.files;
    expect(files.map((file) => file.document_uid).sort()).toEqual(["uid-failed", "uid-raw"]);
    expect(files.find((file) => file.document_uid === "uid-raw")?.profile).toBe("medium");
    expect(files.find((file) => file.document_uid === "uid-failed")?.profile).toBe("rich");
  });

  it("hides the action when every selected document is already ingested", () => {
    const boxes = [...container.querySelectorAll('input[type="checkbox"]')];
    act(() => {
      (boxes[1] as HTMLInputElement).click();
    });

    expect(container.querySelector(`button[aria-label^="${BULK_RELAUNCH_KEY}"]`)).toBeNull();
  });
});
