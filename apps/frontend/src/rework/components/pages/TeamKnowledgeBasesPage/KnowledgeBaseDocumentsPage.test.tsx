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
}));

vi.mock("../../../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts", () => ({
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation: () => [browseTrigger],
}));

import KnowledgeBaseDocumentsPage from "./KnowledgeBaseDocumentsPage.tsx";

function doc(name: string, uid: string) {
  return {
    identity: { document_name: name, document_uid: uid, title: null },
    source: { source_type: "pull", date_added_to_kb: "2026-09-14T08:00:00Z" },
    file: { file_size_bytes: 2048 },
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

  it("names the base and the kind it is", async () => {
    probe.page = { documents: [doc("a.md", "uid-1")], total: 1 };
    await render();

    expect(container.textContent).toContain("Local-2");
    expect(container.textContent).toContain("Local folder");
  });

  it("offers no action over a document", async () => {
    probe.page = { documents: [doc("report.pdf", "uid-1")], total: 1 };
    await render();

    expect(container.querySelectorAll("input[type=checkbox]")).toHaveLength(0);
    const labels = [...container.querySelectorAll("button")].map((button) => button.textContent ?? "");
    expect(labels.some((label) => /delete|rename|download|supprim/i.test(label))).toBe(false);
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
});
