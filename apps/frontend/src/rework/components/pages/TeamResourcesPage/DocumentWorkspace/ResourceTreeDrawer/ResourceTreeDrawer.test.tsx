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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TagNode } from "../../../../../../shared/utils/tagTree.ts";
import type { DocumentMetadata } from "../../../../../../slices/legacyKnowledgeFlow/knowledgeFlowOpenApi.ts";
import ResourceTreeDrawer from "./ResourceTreeDrawer.tsx";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

// Control Plane folders by parent id: "Library" holds one document, the root one more.
const entries = vi.hoisted(() => ({
  byParent: {
    root: [
      { kind: "folder", data: { id: "library-id", name: "Library", parent_id: null } },
      { kind: "document", data: { id: "doc-root", name: "Root.pdf", mime: "application/pdf" } },
    ],
    "library-id": [{ kind: "document", data: { id: "doc-inside", name: "Inside.docx", mime: null } }],
  } as Record<string, unknown[]>,
  queries: [] as Record<string, unknown>[],
}));
vi.mock("../../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useEntriesQuery: (query: { parentId?: string; offset: number; limit: number }) => {
    entries.queries.push(query);
    const items = entries.byParent[query.parentId ?? "root"] ?? [];
    return {
      currentData: {
        items: items.slice(query.offset, query.offset + query.limit),
        total: items.length,
        processing: {},
      },
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    };
  },
}));

function folder(name: string, full: string, tagId?: string, children: TagNode[] = []): TagNode {
  return {
    name,
    full,
    tagsHere: tagId ? ([{ id: tagId }] as TagNode["tagsHere"]) : [],
    children: new Map(children.map((child) => [child.name, child])),
  };
}

function documentWithName(name: string): DocumentMetadata {
  return {
    identity: { document_uid: name, document_name: name },
    file: { file_type: "pdf" },
  } as DocumentMetadata;
}

const tree = folder("", "", undefined, [folder("A", "A", "tag-a", [folder("B", "A/B", "tag-b")])]);

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function button(title: string): HTMLButtonElement {
  const result = container.querySelector<HTMLButtonElement>(`button[title="${title}"]`);
  if (!result) throw new Error(`Missing ${title}`);
  return result;
}

function click(element: Element) {
  act(() => element.dispatchEvent(new MouseEvent("click", { bubbles: true })));
}

/** The tree starts folded into its rail; open it the way a person does. */
function openPanel() {
  click(container.querySelector('button[aria-label="rework.resources.tree.openPanel"]')!);
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

describe("ResourceTreeDrawer", () => {
  it("lists Control Plane folders and documents per open folder and opens down to the current one", () => {
    const navigate = vi.fn();
    const preview = vi.fn();
    entries.queries = [];
    const render = (currentAncestorIds: string[], currentFull: string | null) =>
      act(() =>
        root.render(
          <ResourceTreeDrawer
            root={folder("Resources", "")}
            rootLabel="Resources"
            rootFull={null}
            refreshVersion={0}
            sharedPages={{}}
            documentPatches={{}}
            reuseSharedPages={false}
            currentTagId={null}
            currentFull={currentFull}
            onNavigate={navigate}
            onPreview={preview}
            folderOptions={() => []}
            fileOptions={() => []}
            getFolderDropProps={() => ({})}
            onFolderAction={vi.fn()}
            onFileAction={vi.fn()}
            browseDocuments={vi.fn()}
            manager={{ spaceId: "space-1", currentAncestorIds }}
          />,
        ),
      );
    render([], null);
    openPanel();

    // The root is open: its folder comes before its document, and nothing inside Library is fetched yet.
    const titles = () => [...container.querySelectorAll("button[title]")].map((node) => node.getAttribute("title"));
    expect(titles()).toEqual(["Resources", "Library", "Root.pdf"]);
    expect(entries.queries.every((query) => query.parentId === undefined && query.order === "name_asc")).toBe(true);

    click(button("Library"));
    expect(navigate).toHaveBeenCalledWith("library-id");
    act(() => button("Root.pdf").dispatchEvent(new MouseEvent("dblclick", { bubbles: true })));
    expect(preview).toHaveBeenCalledWith(
      expect.objectContaining({ managerDocument: expect.objectContaining({ id: "doc-root" }) }),
    );

    // Inside a folder of Library, the tree opens Library to show where the table is.
    render(["library-id"], "child-id");
    expect(titles()).toEqual(["Resources", "Library", "Inside.docx", "Root.pdf"]);
    expect(entries.queries.some((query) => query.parentId === "library-id")).toBe(true);
  });

  it("expands nested folders, navigates the table and previews a file on double-click", async () => {
    const browse = vi.fn(async (tagId: string) => ({
      documents: [documentWithName(tagId === "tag-a" ? "A.pdf" : "B.pdf")],
      total: 1,
    }));
    const navigate = vi.fn();
    const preview = vi.fn();
    const folderAction = vi.fn();
    const fileAction = vi.fn();
    const render = (currentFull: string | null) =>
      act(() =>
        root.render(
          <ResourceTreeDrawer
            root={tree}
            rootLabel="Resources"
            rootFull={null}
            refreshVersion={0}
            sharedPages={{}}
            documentPatches={{}}
            reuseSharedPages={true}
            currentTagId={null}
            currentFull={currentFull}
            onNavigate={navigate}
            onPreview={preview}
            folderOptions={() => [{ key: "rename", value: "rename", label: "Rename" }]}
            fileOptions={() => [{ key: "download", value: "download", label: "Download" }]}
            getFolderDropProps={() => ({})}
            onFolderAction={folderAction}
            onFileAction={fileAction}
            browseDocuments={browse}
          />,
        ),
      );
    render(null);
    openPanel();

    expect(button("A")).toBeTruthy();
    expect(container.textContent).not.toContain("A.pdf");
    click(button("A").previousElementSibling!);
    await flush();
    expect(browse).toHaveBeenCalledWith("tag-a", 0, 50);
    expect(button("A.pdf")).toBeTruthy();
    expect(navigate).not.toHaveBeenCalled();

    act(() => button("A").dispatchEvent(new MouseEvent("dblclick", { bubbles: true })));
    expect(container.querySelector('button[title="A.pdf"]')).toBeNull();
    act(() => button("A").dispatchEvent(new MouseEvent("dblclick", { bubbles: true })));
    expect(button("A.pdf")).toBeTruthy();

    click(button("B"));
    render("A/B");
    await flush();
    expect(navigate).toHaveBeenCalledWith("A/B");
    expect(container.querySelector('button[title="B.pdf"]')).toBeNull();
    click(button("B").previousElementSibling!);
    await flush();
    expect(browse).toHaveBeenCalledWith("tag-b", 0, 50);
    expect(button("B.pdf")).toBeTruthy();
    act(() => button("B.pdf").dispatchEvent(new MouseEvent("dblclick", { bubbles: true })));
    expect(preview).toHaveBeenCalledWith(
      expect.objectContaining({ identity: expect.objectContaining({ document_uid: "B.pdf" }) }),
    );

    act(() => button("B.pdf").dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true })));
    click(document.querySelector('[role="menuitem"]')!);
    expect(fileAction).toHaveBeenCalledWith(
      expect.objectContaining({ identity: expect.objectContaining({ document_uid: "B.pdf" }) }),
      "tag-b",
      "download",
    );
    expect(document.activeElement).toBe(button("B.pdf"));
    act(() => button("B").dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true })));
    click(document.querySelector('[role="menuitem"]')!);
    expect(folderAction).toHaveBeenCalledWith(expect.objectContaining({ full: "A/B" }), "rename");

    act(() => button("B").dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true })));
    act(() => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
    expect(document.querySelector('[role="menuitem"]')).toBeNull();
    expect(document.activeElement).toBe(button("B"));
    expect(container.querySelector('aside[data-open="true"]')).toBeTruthy();

    expect(container.querySelector('nav[aria-label="rework.resources.tree.title"]')).toBeTruthy();
    expect(container.querySelector('[aria-label="rework.resources.tree.hide"]')).toBeNull();
    expect(button("B.pdf")).toBeTruthy();
  });

  it("keeps a single click for navigation and a double click for expansion", async () => {
    const browse = vi.fn(async () => ({ documents: [documentWithName("A.pdf")], total: 1 }));
    const navigate = vi.fn();
    const render = (currentFull: string | null) =>
      act(() =>
        root.render(
          <ResourceTreeDrawer
            root={tree}
            rootLabel="Resources"
            rootFull={null}
            refreshVersion={0}
            sharedPages={{}}
            documentPatches={{}}
            reuseSharedPages={true}
            currentTagId={null}
            currentFull={currentFull}
            onNavigate={navigate}
            onPreview={vi.fn()}
            folderOptions={() => []}
            fileOptions={() => []}
            getFolderDropProps={() => ({})}
            onFolderAction={vi.fn()}
            onFileAction={vi.fn()}
            browseDocuments={browse}
          />,
        ),
      );
    render(null);
    openPanel();
    click(button("A"));
    render("A");
    expect(navigate).toHaveBeenCalledWith("A");
    expect(button("A").getAttribute("aria-current")).toBe("page");
    expect(container.querySelector('button[title="A.pdf"]')).toBeNull();
    act(() => button("A").dispatchEvent(new MouseEvent("dblclick", { bubbles: true })));
    await flush();
    expect(button("A.pdf")).toBeTruthy();
  });

  it("does not reload expanded folders while the rail is collapsed", async () => {
    const browse = vi.fn(async () => ({ documents: [], total: 0 }));
    const render = (refreshVersion: number) =>
      act(() =>
        root.render(
          <ResourceTreeDrawer
            root={tree}
            rootLabel="Resources"
            rootFull={null}
            refreshVersion={refreshVersion}
            sharedPages={{}}
            documentPatches={{}}
            reuseSharedPages={false}
            currentTagId={null}
            currentFull={null}
            onNavigate={vi.fn()}
            onPreview={vi.fn()}
            folderOptions={() => []}
            fileOptions={() => []}
            getFolderDropProps={() => ({})}
            onFolderAction={vi.fn()}
            onFileAction={vi.fn()}
            browseDocuments={browse}
          />,
        ),
      );
    render(0);
    openPanel();
    click(button("A").previousElementSibling!);
    await flush();
    expect(browse).toHaveBeenCalledTimes(1);

    click(container.querySelector('button[aria-label="rework.resources.tree.closePanel"]')!);
    render(1);
    await flush();
    expect(browse).toHaveBeenCalledTimes(1);
    expect(container.querySelector("nav")).toBeNull();

    click(container.querySelector('button[aria-label="rework.resources.tree.openPanel"]')!);
    await flush();
    expect(browse).toHaveBeenCalledTimes(2);
    expect(button("A")).toBeTruthy();
  });

  it("applies successful metadata patches to tree-only files", async () => {
    const doc = { ...documentWithName("A.pdf"), source: { retrievable: true }, labels: ["Old"] } as DocumentMetadata;
    const browse = vi.fn(async () => ({ documents: [doc], total: 1 }));
    const fileAction = vi.fn();
    const render = (documentPatches: { [uid: string]: { retrievable?: boolean; labels?: string[] } }) =>
      act(() =>
        root.render(
          <ResourceTreeDrawer
            root={tree}
            rootLabel="Resources"
            rootFull={null}
            refreshVersion={0}
            sharedPages={{}}
            documentPatches={documentPatches}
            reuseSharedPages={true}
            currentTagId={null}
            currentFull={null}
            onNavigate={vi.fn()}
            onPreview={vi.fn()}
            folderOptions={() => []}
            fileOptions={(file) => [{ key: "searchable", value: "searchable", label: String(file.source.retrievable) }]}
            getFolderDropProps={() => ({})}
            onFolderAction={vi.fn()}
            onFileAction={fileAction}
            browseDocuments={browse}
          />,
        ),
      );
    render({});
    openPanel();
    click(button("A").previousElementSibling!);
    await flush();
    render({ "A.pdf": { retrievable: false, labels: ["New"] } });
    act(() => button("A.pdf").dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true })));
    expect(document.querySelector('[role="menuitem"]')?.textContent).toBe("false");
    click(document.querySelector('[role="menuitem"]')!);
    expect(fileAction).toHaveBeenCalledWith(
      expect.objectContaining({ source: expect.objectContaining({ retrievable: false }), labels: ["New"] }),
      "tag-a",
      "searchable",
    );
  });

  it("loads direct files in bounded pages", async () => {
    const first = Array.from({ length: 50 }, (_, index) => documentWithName(`File-${index}.pdf`));
    const browse = vi.fn(async (_tagId: string, offset: number) => ({
      documents: offset === 0 ? first : [documentWithName("File-50.pdf")],
      total: 51,
    }));
    act(() =>
      root.render(
        <ResourceTreeDrawer
          root={tree}
          rootLabel="Resources"
          rootFull={null}
          refreshVersion={0}
          sharedPages={{}}
          documentPatches={{}}
          reuseSharedPages={true}
          currentTagId={null}
          currentFull={null}
          onNavigate={vi.fn()}
          onPreview={vi.fn()}
          folderOptions={() => []}
          fileOptions={() => []}
          getFolderDropProps={() => ({})}
          onFolderAction={vi.fn()}
          onFileAction={vi.fn()}
          browseDocuments={browse}
        />,
      ),
    );
    openPanel();
    click(button("A").previousElementSibling!);
    await flush();
    expect(browse).toHaveBeenCalledTimes(1);
    expect(browse).toHaveBeenCalledWith("tag-a", 0, 50);
    expect(container.querySelector('button[title="File-50.pdf"]')).toBeNull();
    click(container.querySelector('[class*="more"]')!);
    await flush();
    expect(browse).toHaveBeenCalledWith("tag-a", 50, 50);
    expect(button("File-50.pdf")).toBeTruthy();
    expect(container.querySelectorAll('button[title^="File-"]')).toHaveLength(51);
  });
});
