// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const { browse, pages, spaceContext } = vi.hoisted(() => ({
  browse: vi.fn(),
  pages: new Map<string, unknown>(),
  spaceContext: { currentData: [] as { id: string; name: string; path: string[] }[], isFetching: false },
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useLazyEntriesQuery: () => [browse],
  useMySpacesQuery: () => spaceContext,
}));

vi.mock("@shared/molecules/Select/Select", () => ({
  default: ({ options, onChange }: { options: { value: string; label: string }[]; onChange: (id: string) => void }) => (
    <div>
      {options.map((option) => (
        <button key={option.value} data-space={option.value} onClick={() => onChange(option.value)}>
          {option.label}
        </button>
      ))}
    </div>
  ),
}));

import { DocumentLibraryScopePicker } from "./DocumentLibraryScopePicker";
import type { DocumentLibrarySelection } from "./documentLibrarySelection";

const folder = (id: string, parentId: string | null = null) => ({
  kind: "folder",
  data: { id, name: id, space_id: "space-1", parent_id: parentId, path: id },
});
const doc = (id: string, parentId: string | null = "folder-1") => ({
  kind: "document",
  data: { id, name: `${id}.txt`, space_id: "space-1", folder_id: parentId },
});
const directory = (items: unknown[], total = items.length) => ({ items, total });
let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  spaceContext.currentData = ["space-1", "space-2"].map((id) => ({ id, name: id, path: [id] }));
  pages.clear();
  pages.set(":0", directory([folder("folder-1")]));
  pages.set("folder-1:0", directory([doc("doc-1"), doc("doc-2")], 3));
  pages.set("folder-1:2", directory([doc("doc-3")], 3));
  browse.mockReset();
  browse.mockImplementation(({ parentId = "", offset = 0 }) => ({
    unwrap: async () => {
      const page = pages.get(`${parentId}:${offset}`);
      if (!page || page instanceof Error) throw new Error("Failed directory read");
      return page;
    },
    abort: vi.fn(),
  }));
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

async function renderPicker(
  value: DocumentLibrarySelection,
  extra: Partial<Parameters<typeof DocumentLibraryScopePicker>[0]> = {},
) {
  const onChange = vi.fn();
  await act(async () =>
    root.render(<DocumentLibraryScopePicker spaceId="space-1" value={value} onChange={onChange} {...extra} />),
  );
  return onChange;
}
async function expand() {
  await act(async () => container.querySelector<HTMLButtonElement>("button[aria-expanded]")?.click());
}
async function expandFolder(name: string) {
  await act(async () =>
    container.querySelector<HTMLButtonElement>(`button[aria-label="rework.expand ${name}"]`)?.click(),
  );
}
async function loadMore() {
  const more = Array.from(container.querySelectorAll("button")).find(
    (button) => button.textContent === "dataHub.loadMore",
  );
  await act(async () => more?.click());
}
function deferredDirectory() {
  let resolve!: (value: ReturnType<typeof directory>) => void;
  const promise = new Promise<ReturnType<typeof directory>>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
function checkbox(label: string) {
  return container.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`)!;
}

describe("Weaver document picker", () => {
  it("uses the canonical space and navigates mixed pages including root documents", async () => {
    pages.set(":0", directory([folder("folder-1"), doc("root-doc", null)]));
    await renderPicker({ folderIds: [], documentIds: ["root-doc"] });
    expect(checkbox("root-doc.txt").checked).toBe(true);
    expect(browse).toHaveBeenCalledWith(expect.objectContaining({ id: "space-1", offset: 0 }));
    await expand();
    expect(checkbox("doc-3.txt")).toBeNull();
    const more = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent === "dataHub.loadMore",
    );
    await act(async () => more?.click());
    expect(checkbox("doc-3.txt")).not.toBeNull();
  });

  it("shows direct documents covered by a selected folder", async () => {
    await renderPicker({ folderIds: ["folder-1"], documentIds: [] });
    await expand();
    expect(checkbox("folder-1").checked).toBe(false);
    expect(checkbox("folder-1").indeterminate).toBe(true);
    expect(checkbox("doc-1.txt").checked).toBe(true);
    expect(checkbox("doc-2.txt").checked).toBe(true);
    await loadMore();
    expect(checkbox("folder-1").checked).toBe(true);
  });

  it("replaces a folder with ALL other direct documents, keeping subfolders and outside picks", async () => {
    const onChange = await renderPicker({ folderIds: ["folder-1", "child"], documentIds: ["doc-1", "outside"] });
    await expand();
    await act(async () => checkbox("doc-1.txt").click());
    expect(onChange).toHaveBeenCalledExactlyOnceWith({
      folderIds: ["child"],
      documentIds: ["outside", "doc-2", "doc-3"],
    });
    expect(browse).toHaveBeenCalledWith(expect.objectContaining({ parentId: "folder-1", offset: 2 }));
  });

  it("selects the complete subtree and removes redundant explicit document picks atomically", async () => {
    pages.set("folder-1:0", directory([folder("child", "folder-1"), doc("doc-1")], 3));
    pages.set("folder-1:2", directory([doc("doc-2")], 3));
    pages.set("child:0", directory([doc("child-doc", "child")]));
    const onChange = await renderPicker({ folderIds: [], documentIds: ["doc-2", "child-doc", "outside"] });
    await act(async () => checkbox("folder-1").click());
    expect(onChange).toHaveBeenCalledExactlyOnceWith({ folderIds: ["folder-1", "child"], documentIds: ["outside"] });
  });

  it("leaves the selection unchanged if a later page fails", async () => {
    pages.set("folder-1:2", new Error("Unavailable"));
    const onChange = await renderPicker({ folderIds: ["folder-1"], documentIds: [] });
    await expand();
    await act(async () => checkbox("doc-1.txt").click());
    expect(onChange).not.toHaveBeenCalled();
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("documentSelectionFailed");
  });

  it("rejects detectable directory changes between selection pages", async () => {
    pages.set("folder-1:2", directory([doc("doc-3")], 4));
    const onChange = await renderPicker({ folderIds: ["folder-1"], documentIds: [] });
    await expand();
    await act(async () => checkbox("doc-1.txt").click());
    expect(onChange).not.toHaveBeenCalled();
  });

  it("keeps pinned folders untouchable from a document row", async () => {
    const onChange = await renderPicker(
      { folderIds: ["folder-1"], documentIds: [] },
      { disableLibrarySelection: true },
    );
    await expand();
    expect(checkbox("folder-1").disabled).toBe(true);
    expect(checkbox("doc-1.txt").disabled).toBe(true);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("allows read-only navigation while all selection controls are disabled", async () => {
    const onChange = await renderPicker({ folderIds: [], documentIds: [] }, { disabled: true });
    await expand();
    expect(checkbox("doc-1.txt").disabled).toBe(true);
    expect(checkbox("folder-1").disabled).toBe(true);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("discards loaded entries when changing space", async () => {
    await renderPicker({ folderIds: [], documentIds: [] });
    await expand();
    pages.set(":0", directory([]));
    await renderPicker({ folderIds: [], documentIds: [] }, { spaceId: "space-2" });
    expect(checkbox("doc-1.txt")).toBeNull();
    expect(browse).toHaveBeenLastCalledWith(expect.objectContaining({ id: "space-2" }));
  });
  it("keeps an asynchronous edit across equivalent recreated values and uses the latest callback", async () => {
    const initial = { folderIds: ["outside-a", "outside-b"], documentIds: ["outside-doc"] };
    const firstCallback = await renderPicker(initial);
    const pending = deferredDirectory();
    pages.set("folder-1:0", pending.promise);
    await act(async () => checkbox("folder-1").click());
    const latestCallback = await renderPicker({
      folderIds: ["outside-b", "outside-a", "outside-a"],
      documentIds: ["outside-doc"],
    });
    await act(async () => pending.resolve(directory([doc("doc-1")])));
    expect(firstCallback).not.toHaveBeenCalled();
    expect(latestCallback).toHaveBeenCalledExactlyOnceWith({
      folderIds: ["outside-a", "outside-b", "folder-1"],
      documentIds: ["outside-doc"],
    });
  });

  it.each(["folders", "documents", "disabled", "pinned", "selection-round-trip", "disabled-round-trip"])(
    "does not apply a pending selection after a committed %s change",
    async (transition) => {
      const initial = { folderIds: ["folder-1"], documentIds: ["outside-doc"] };
      const onChange = await renderPicker(initial);
      const pending = deferredDirectory();
      pages.set("folder-1:0", pending.promise);
      await act(async () => checkbox("folder-1").click());
      const next =
        transition === "folders" || transition === "selection-round-trip"
          ? { ...initial, folderIds: ["another-folder"] }
          : transition === "documents"
            ? { ...initial, documentIds: ["another-doc"] }
            : initial;
      await renderPicker(next, {
        onChange,
        disabled: transition === "disabled" || transition === "disabled-round-trip",
        disableLibrarySelection: transition === "pinned",
      });
      if (transition.endsWith("round-trip")) await renderPicker(initial, { onChange });
      await act(async () => pending.resolve(directory([doc("doc-1")])));
      expect(onChange).not.toHaveBeenCalled();
    },
  );

  it("does not apply a pending selection after switching spaces even if its request completes", async () => {
    const onChange = await renderPicker({ folderIds: [], documentIds: [] });
    const pending = deferredDirectory();
    pages.set("folder-1:0", pending.promise);
    await act(async () => checkbox("folder-1").click());
    await renderPicker({ folderIds: [], documentIds: [] }, { spaceId: "space-2", onChange });
    // The mock intentionally allows completion after abort: the component must
    // guard its callback independently of transport cancellation.
    await act(async () => pending.resolve(directory([doc("doc-1")])));
    expect(onChange).not.toHaveBeenCalled();
  });

  it.each([false, true])(
    "makes a restored subtree click independent of navigation (complete selection: %s)",
    async (complete) => {
      pages.set("folder-1:0", directory([folder("kept", "folder-1")], 2));
      pages.set("folder-1:1", directory([folder("excluded", "folder-1")], 2));
      pages.set("kept:0", directory([]));
      pages.set("excluded:0", directory([]));
      const restored = {
        folderIds: complete ? ["folder-1", "kept", "excluded"] : ["folder-1", "kept"],
        documentIds: [],
      };
      const onChange = await renderPicker(restored);
      // A restored folder id alone cannot prove that the whole subtree is picked.
      expect(checkbox("folder-1").checked).toBe(false);
      expect(checkbox("folder-1").indeterminate).toBe(true);
      expect(checkbox("folder-1").getAttribute("aria-description")).toContain("documentSelectionUnknown");
      await act(async () => checkbox("folder-1").click());
      const closedResult = onChange.mock.calls[0][0];
      onChange.mockClear();

      await expand();
      expect(checkbox("folder-1").checked).toBe(false);
      await act(async () => checkbox("folder-1").click());
      expect(onChange).toHaveBeenCalledExactlyOnceWith(closedResult);
      onChange.mockClear();

      await loadMore();
      // Even all direct entries do not prove that the child subtrees are complete.
      expect(checkbox("folder-1").checked).toBe(false);
      await expandFolder("kept");
      await expandFolder("excluded");
      expect(checkbox("folder-1").checked).toBe(complete);
      expect(checkbox("folder-1").indeterminate).toBe(!complete);
      expect(checkbox("folder-1").hasAttribute("aria-description")).toBe(false);
      await act(async () => checkbox("folder-1").click());
      expect(onChange).toHaveBeenCalledExactlyOnceWith(closedResult);
      expect(closedResult).toEqual({ folderIds: complete ? [] : ["folder-1", "kept", "excluded"], documentIds: [] });
    },
  );

  it("does not infer a full subtree from loaded selected children while a grandchild is unknown or excluded", async () => {
    pages.set("folder-1:0", directory([folder("child", "folder-1"), doc("doc-1")]));
    pages.set("child:0", directory([folder("grandchild", "child")]));
    pages.set("grandchild:0", directory([]));
    const onChange = await renderPicker({ folderIds: ["folder-1", "child"], documentIds: [] });
    await expand();
    expect(checkbox("doc-1.txt").checked).toBe(true);
    expect(checkbox("folder-1").checked).toBe(false);
    expect(checkbox("child").checked).toBe(false);
    await expandFolder("child");
    expect(checkbox("child").checked).toBe(false);
    await expandFolder("grandchild");
    expect(checkbox("folder-1").indeterminate).toBe(true);
    expect(checkbox("child").indeterminate).toBe(true);
    expect(checkbox("grandchild").checked).toBe(false);
    await act(async () => checkbox("folder-1").click());
    expect(onChange).toHaveBeenCalledExactlyOnceWith({
      folderIds: ["folder-1", "child", "grandchild"],
      documentIds: [],
    });
  });

  it("does not claim an unloaded restored document's ancestor is unselected", async () => {
    await renderPicker({ folderIds: [], documentIds: ["doc-3"] });
    expect(checkbox("folder-1").indeterminate).toBe(true);
    await expand();
    expect(checkbox("folder-1").checked).toBe(false);
    expect(checkbox("folder-1").indeterminate).toBe(true);
    await loadMore();
    expect(checkbox("folder-1").indeterminate).toBe(true);
    expect(checkbox("folder-1").hasAttribute("aria-description")).toBe(false);
    expect(checkbox("doc-3.txt").checked).toBe(true);
  });
});

it("offers only the current search path and preserves combined selections across parent navigation", async () => {
  spaceContext.currentData = [
    { id: "parent", name: "Parent", path: ["parent"] },
    { id: "space-1", name: "Team", path: ["parent", "space-1"] },
    { id: "sibling", name: "Sibling", path: ["parent", "sibling"] },
    { id: "child", name: "Project", path: ["parent", "space-1", "child"] },
  ];
  const selection = { folderIds: ["folder-1"], documentIds: ["parent-document"] };
  const onChange = await renderPicker(selection);
  expect([...container.querySelectorAll("[data-space]")].map((element) => element.getAttribute("data-space"))).toEqual([
    "parent",
    "space-1",
  ]);
  await act(async () => container.querySelector<HTMLButtonElement>('[data-space="parent"]')!.click());
  expect(browse).toHaveBeenLastCalledWith(expect.objectContaining({ id: "parent", offset: 0 }));
  expect(onChange).not.toHaveBeenCalled();
  await act(async () => container.querySelector<HTMLButtonElement>('[data-space="space-1"]')!.click());
  expect(browse).toHaveBeenLastCalledWith(expect.objectContaining({ id: "space-1", offset: 0 }));
  expect(onChange).not.toHaveBeenCalled();
});
