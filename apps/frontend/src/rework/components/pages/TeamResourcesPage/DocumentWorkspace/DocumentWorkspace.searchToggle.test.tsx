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

// Coverage: the row "more" menu's searchable action relabels itself to
// "Include in search" for an already-excluded document (and back), and the
// bulk toolbar's search-toggle button mirrors the selection's state: hidden
// on a mixed selection (some excluded, some not — no single unambiguous
// direction), "Include in search" when every selected doc is excluded,
// "Exclude from search" when every one is searchable. Also: the row
// indicator icon and the "more" menu label must flip immediately on click,
// not only after a folder reload — toggleRetrievable only calls the
// backend, so DocumentWorkspace has to patch its own local doc list from
// the hook's returned next value.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-redux", () => ({ useSelector: () => [] }));

const doc = (uid: string, name: string, retrievable: boolean | undefined) => ({
  identity: { document_uid: uid, title: name, document_name: `${name}.pdf`, uploaded_by: null },
  file: { file_type: "pdf", file_size_bytes: 1024 },
  source: { date_added_to_kb: "2026-07-01T00:00:00Z", retrievable },
  processing: { stages: { raw: "done", vector: "done" } },
  tags: { tag_ids: ["tag-cir"] },
});

// A tabular dataset only ever completes the `sql` stage — `retrievable` stays
// false there by design (no vector chunks), not a real exclusion.
const tabularDoc = (uid: string, name: string) => ({
  identity: { document_uid: uid, title: name, document_name: `${name}.xlsx`, uploaded_by: null },
  file: { file_type: "xlsx", file_size_bytes: 2048 },
  source: { date_added_to_kb: "2026-07-01T00:00:00Z", retrievable: false },
  processing: { stages: { raw: "done", sql: "done" } },
  tags: { tag_ids: ["tag-cir"] },
});

// Mirrors the real hook: flips the doc's current value and returns the new
// one, which is exactly what DocumentWorkspace needs to patch its own state.
const toggleRetrievable = vi.fn(async (d: { source: { retrievable?: boolean } }) => !d.source.retrievable);

vi.mock("../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  // The rollup reads the team's terminal ingestion history (#2384); no
  // history in these fixtures, so it falls back to the live task feed.
  useListTasksKnowledgeFlowV1TasksGetQuery: () => ({ data: undefined }),
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => ({
    data: [{ id: "tag-cir", name: "CIR", path: "", type: "document", item_ids: [] }],
    isLoading: false,
    refetch: () => {},
  }),
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [
    () => ({
      unwrap: async () => ({
        documents: [
          doc("uid-excluded-1", "Excluded one", false),
          doc("uid-excluded-2", "Excluded two", false),
          doc("uid-included", "Included doc", true),
          tabularDoc("uid-tabular", "Tabular doc"),
        ],
        total: 4,
      }),
    }),
  ],
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation: () => [vi.fn()],
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation: () => [vi.fn()],
  useCreateTagKnowledgeFlowV1TagsPostMutation: () => [vi.fn()],
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation: () => [vi.fn()],
  useCancelTaskKnowledgeFlowV1TasksTaskIdCancelPostMutation: () => [vi.fn()],
  useUpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutMutation: () => [
    vi.fn(() => ({ unwrap: async () => ({}) })),
  ],
}));
vi.mock("../../../../features/tasks/taskSlice", () => ({ selectActiveTasks: () => [], selectAllTasks: () => [] }));
vi.mock("../../../../features/tasks/useRefetchOnTaskSettled", () => ({ useRefetchOnTaskSettled: () => {} }));
vi.mock("../../../../features/tasks/useNotifyOnNewTaskTarget", () => ({ useNotifyOnNewTaskTarget: () => {} }));
vi.mock("../../../../../components/documents/common/useDocumentCommands", () => ({
  useDocumentCommands: () => ({
    previewTarget: null,
    closePreview: () => {},
    preview: () => {},
    download: async () => {},
    toggleRetrievable,
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

let container: HTMLDivElement;
let root: Root;

beforeEach(async () => {
  toggleRetrievable.mockClear();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(<DocumentWorkspace teamId="team-1" isPersonalTeam={false} />);
  });

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

// Row order matches the mocked `documents` array: excluded-1, excluded-2, included.
function rowCheckboxes(): HTMLInputElement[] {
  return [...container.querySelectorAll('input[type="checkbox"]')].slice(1) as HTMLInputElement[];
}

function selectRows(...indices: number[]) {
  const boxes = rowCheckboxes();
  act(() => {
    for (const i of indices) boxes[i].click();
  });
}

describe("DocumentWorkspace — row 'more' menu searchable label", () => {
  function moreButtons(): HTMLButtonElement[] {
    return [...container.querySelectorAll('button[aria-label="rework.resources.action.more"]')] as HTMLButtonElement[];
  }

  function openMenuAndReadSearchableLabel(button: HTMLButtonElement): string {
    act(() => {
      button.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });
    const items = [
      ...document.querySelectorAll(
        '[role="presentation"] [role="menuitem"], [role="presentation"] li, [role="presentation"] button',
      ),
    ];
    const item = items.find(
      (el) =>
        el.textContent?.includes("rework.resources.action.includeInSearch") ||
        el.textContent?.includes("rework.resources.action.searchable"),
    );
    if (!item) throw new Error("searchable/include menu item not found");
    return item.textContent ?? "";
  }

  it("shows 'Include in search' for a document already excluded", () => {
    const label = openMenuAndReadSearchableLabel(moreButtons()[0]);
    expect(label.endsWith("rework.resources.action.includeInSearch")).toBe(true);
  });

  it("shows 'Exclude from search' for a searchable document", () => {
    const label = openMenuAndReadSearchableLabel(moreButtons()[2]);
    expect(label.endsWith("rework.resources.action.searchable")).toBe(true);
  });

  it("omits the searchable/include-in-search option entirely for a tabular-only dataset", () => {
    act(() => {
      moreButtons()[3].dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });
    const items = [
      ...document.querySelectorAll(
        '[role="presentation"] [role="menuitem"], [role="presentation"] li, [role="presentation"] button',
      ),
    ];
    const item = items.find(
      (el) =>
        el.textContent?.includes("rework.resources.action.includeInSearch") ||
        el.textContent?.includes("rework.resources.action.searchable"),
    );
    expect(item).toBeUndefined();
  });
});

describe("DocumentWorkspace — bulk search-toggle button", () => {
  it("shows 'Include in search' when every selected doc is already excluded", () => {
    selectRows(0, 1);
    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.includeInSearch"]')).not.toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.excludeFromSearch"]')).toBeNull();
  });

  it("shows 'Exclude from search' when every selected doc is searchable", () => {
    selectRows(2);
    expect(
      container.querySelector('button[aria-label="rework.resources.bulkActions.excludeFromSearch"]'),
    ).not.toBeNull();
  });

  it("hides the button entirely on a mixed selection", () => {
    selectRows(0, 2);
    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.includeInSearch"]')).toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.excludeFromSearch"]')).toBeNull();
  });

  it("toggles every selected (all-excluded) doc back to searchable on click", () => {
    selectRows(0, 1);
    const button = container.querySelector(
      'button[aria-label="rework.resources.bulkActions.includeInSearch"]',
    ) as HTMLButtonElement;
    act(() => {
      button.click();
    });
    expect(toggleRetrievable).toHaveBeenCalledTimes(2);
  });

  it("ignores a tabular-only doc in the selection — still shows 'Include in search' for the two real exclusions, not hidden as a mixed selection", () => {
    selectRows(0, 1, 3); // two excluded + the tabular doc
    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.includeInSearch"]')).not.toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.excludeFromSearch"]')).toBeNull();
  });

  it("does not toggle the tabular doc when the bulk action fires on a mixed real+tabular selection", () => {
    selectRows(0, 1, 3);
    const button = container.querySelector(
      'button[aria-label="rework.resources.bulkActions.includeInSearch"]',
    ) as HTMLButtonElement;
    act(() => {
      button.click();
    });
    // Only the two real exclusions toggle — the tabular doc is skipped entirely.
    expect(toggleRetrievable).toHaveBeenCalledTimes(2);
  });

  it("hides the button entirely when only tabular-only docs are selected — nothing toggle-relevant", () => {
    selectRows(3);
    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.includeInSearch"]')).toBeNull();
    expect(container.querySelector('button[aria-label="rework.resources.bulkActions.excludeFromSearch"]')).toBeNull();
  });
});

describe("DocumentWorkspace — immediate UI update after toggling searchable", () => {
  function moreButtons(): HTMLButtonElement[] {
    return [...container.querySelectorAll('button[aria-label="rework.resources.action.more"]')] as HTMLButtonElement[];
  }

  async function clickSearchableMenuItem(button: HTMLButtonElement) {
    act(() => {
      button.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });
    const items = [
      ...document.querySelectorAll(
        '[role="presentation"] [role="menuitem"], [role="presentation"] li, [role="presentation"] button',
      ),
    ];
    const item = items.find(
      (el) =>
        el.textContent?.includes("rework.resources.action.includeInSearch") ||
        el.textContent?.includes("rework.resources.action.searchable"),
    );
    if (!item) throw new Error("searchable/include menu item not found");
    await act(async () => {
      item.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });
  }

  it("shows the excluded indicator right after excluding a row, with no reload", async () => {
    // "Included doc" (row 2) starts searchable — no indicator yet on its own row
    // (rows 0/1 already have one, unrelated to this action).
    const row = () => moreButtons()[2].closest('[class*="datatable-row"]');
    expect(row()?.querySelector('[aria-label="rework.resources.status.excludedFromSearch"]')).toBeNull();

    await clickSearchableMenuItem(moreButtons()[2]);

    expect(row()?.querySelector('[aria-label="rework.resources.status.excludedFromSearch"]')).not.toBeNull();
  });

  it("relabels the same row's menu item to 'Include in search' right after excluding it", async () => {
    await clickSearchableMenuItem(moreButtons()[2]);

    const label = await (async () => {
      act(() => {
        moreButtons()[2].dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
      });
      const items = [
        ...document.querySelectorAll(
          '[role="presentation"] [role="menuitem"], [role="presentation"] li, [role="presentation"] button',
        ),
      ];
      const item = items.find(
        (el) =>
          el.textContent?.includes("rework.resources.action.includeInSearch") ||
          el.textContent?.includes("rework.resources.action.searchable"),
      );
      return item?.textContent ?? "";
    })();

    expect(label.endsWith("rework.resources.action.includeInSearch")).toBe(true);
  });

  it("removes the excluded indicator right after re-including a row, with no reload", async () => {
    // "Excluded one" (row 0) starts excluded — indicator present.
    expect(
      moreButtons()[0]
        .closest('[class*="datatable-row"]')
        ?.querySelector('[aria-label="rework.resources.status.excludedFromSearch"]'),
    ).not.toBeNull();

    await clickSearchableMenuItem(moreButtons()[0]);

    expect(
      moreButtons()[0]
        .closest('[class*="datatable-row"]')
        ?.querySelector('[aria-label="rework.resources.status.excludedFromSearch"]'),
    ).toBeNull();
  });
});
