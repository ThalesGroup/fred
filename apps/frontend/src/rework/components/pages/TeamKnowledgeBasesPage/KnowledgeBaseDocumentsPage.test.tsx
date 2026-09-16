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

// A base's documents are shown and nothing is offered over them: they belong
// to a source it mirrors, so a removal here would last only until the next run.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const probe = vi.hoisted(() => ({
  instance: undefined as Record<string, unknown> | undefined,
  /** Every browse request the page made, in order. */
  browsed: [] as Record<string, unknown>[],
  page: { documents: [] as Record<string, unknown>[], total: 0 },
  browseRejects: false,
  uploaders: [] as { id: string; [key: string]: unknown }[],
  /** Every batched uid lookup the page made — one per page, never per row. */
  uploaderLookups: [] as string[][],
  previewed: [] as Record<string, unknown>[],
  preview: (doc: Record<string, unknown>) => {
    probe.previewed.push(doc);
  },
}));

// One trigger for the life of the module, as RTK Query guarantees. A fresh
// function each render would re-run the page's load effect for ever — that is
// a property of the double, not of the page, and the real client is stable.
const browseTrigger = vi.hoisted(() => (args: Record<string, unknown>) => {
  probe.browsed.push(args);
  return {
    unwrap: () => (probe.browseRejects ? Promise.reject(new Error("listing failed")) : Promise.resolve(probe.page)),
  };
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("react-router-dom", () => ({
  useParams: () => ({ teamId: "team-1", instanceId: "kb-1" }),
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => <a href={to}>{children}</a>,
}));

vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements.ts", () => ({
  useKnowledgeBaseQuery: () => ({ data: probe.instance, isLoading: false, isError: !probe.instance }),
  useUsersByIdsQuery: (args: { ids: string[] }) => {
    probe.uploaderLookups.push(args.ids);
    return { data: probe.uploaders, isFetching: false };
  },
}));

vi.mock("../../../../components/documents/common/useDocumentCommands", () => ({
  useDocumentCommands: () => ({ preview: probe.preview, previewTarget: null, closePreview: () => {} }),
}));

vi.mock("../../../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts", () => ({
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [browseTrigger],
}));

import KnowledgeBaseDocumentsPage from "./KnowledgeBaseDocumentsPage.tsx";

function doc(name: string, uid: string, overrides: Record<string, unknown> = {}) {
  return {
    identity: { document_name: name, document_uid: uid, title: null, uploaded_by: null },
    source: { source_type: "pull", date_added_to_kb: "2026-09-14T08:00:00Z" },
    file: { file_size_bytes: 2048 },
    processing: { stages: { vector: "done" } },
    ...overrides,
  };
}

let container: HTMLDivElement;
let root: Root;

async function render() {
  await act(async () => {
    root.render(<KnowledgeBaseDocumentsPage />);
  });
}

beforeEach(() => {
  probe.instance = {
    id: "kb-1",
    library_id: "lib-1",
    library_name: "Local-2",
    definition_name: "Local folder",
  };
  probe.browsed = [];
  probe.page = { documents: [], total: 0 };
  probe.browseRejects = false;
  probe.uploaders = [];
  probe.uploaderLookups = [];
  probe.previewed = [];
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("KnowledgeBaseDocumentsPage", () => {
  it("browses the base's own library and nothing else", async () => {
    probe.page = { documents: [doc("report.pdf", "uid-1")], total: 1 };
    await render();

    expect(probe.browsed).toHaveLength(1);
    expect(probe.browsed[0]).toMatchObject({
      browseDocumentsByTagRequest: { tag_id: "lib-1", offset: 0 },
    });
    expect(container.textContent).toContain("report.pdf");
  });

  it("asks for the whole library, not just its top folder", async () => {
    // A base mirrors its source's shape, so asking for the library tag alone
    // returned only the files at the root of that source — most bases looked empty.
    probe.page = { documents: [doc("specs/api/openapi.md", "uid-1")], total: 1 };
    await render();

    expect(probe.browsed[0].browseDocumentsByTagRequest.include_descendants).toBe(true);
    expect(container.textContent).not.toContain("rework.knowledgeBases.documents.empty");
  });

  it("names the base and the kind it is", async () => {
    probe.page = { documents: [doc("a.md", "uid-1")], total: 1 };
    await render();

    expect(container.textContent).toContain("Local-2");
    expect(container.textContent).toContain("Local folder");
  });

  it("offers no action that changes a document", async () => {
    probe.page = { documents: [doc("report.pdf", "uid-1")], total: 1 };
    await render();

    expect(container.querySelectorAll("input[type=checkbox]")).toHaveLength(0);
    const labels = [...container.querySelectorAll("button")].flatMap((button) => [
      button.textContent ?? "",
      button.getAttribute("aria-label") ?? "",
    ]);
    expect(labels.some((label) => /delete|rename|download|supprim/i.test(label))).toBe(false);
  });

  it("still lets a reader open a document", async () => {
    probe.page = { documents: [doc("report.pdf", "uid-1")], total: 1 };
    await render();

    const open = [...container.querySelectorAll("button")].find(
      (button) => button.getAttribute("aria-label") === "rework.resources.action.preview",
    );
    expect(open).toBeDefined();
    act(() => open!.click());
    expect(probe.previewed).toHaveLength(1);
  });

  it("says so when the base holds nothing yet", async () => {
    await render();
    expect(container.textContent).toContain("rework.knowledgeBases.documents.empty");
  });

  it("reports a failed listing instead of an empty base", async () => {
    probe.browseRejects = true;
    await render();

    expect(container.textContent).toContain("rework.knowledgeBases.documents.loadFailed");
    expect(container.textContent).not.toContain("rework.knowledgeBases.documents.empty");
  });

  it("resolves every uploader in one lookup, not one per row", async () => {
    probe.uploaders = [{ id: "u-1", first_name: "Priya", last_name: "N" }];
    probe.page = {
      documents: [
        doc("a.md", "uid-1", { identity: { document_name: "a.md", document_uid: "uid-1", uploaded_by: "u-1" } }),
        doc("b.md", "uid-2", { identity: { document_name: "b.md", document_uid: "uid-2", uploaded_by: "u-1" } }),
      ],
      total: 2,
    };
    await render();

    const asked = probe.uploaderLookups.filter((ids) => ids.length > 0);
    expect(asked.every((ids) => ids.length === 1)).toBe(true);
    expect(asked[asked.length - 1]).toEqual(["u-1"]);
  });

  it("shows what a document settled at", async () => {
    probe.page = {
      documents: [doc("failed.pdf", "uid-1", { processing: { stages: { vector: "failed" } } })],
      total: 1,
    };
    await render();

    // The chip renders; its own tests cover which stage means which status.
    expect(container.querySelector("[class*='statusChip'], [class*='chip']")).not.toBeNull();
  });
});
