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

// The wiki's URL always names its page, through a real router: where the root
// leads, what Back does, and what happens after a deletion while the cached tree
// still lists the deleted page.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

interface FakePage {
  page_id: string;
  slug: string;
  title: string;
  kind: string;
  position: number;
}

const h = vi.hoisted(() => {
  const listeners = new Set<() => void>();
  return {
    pages: [] as FakePage[],
    setPages(next: FakePage[]) {
      this.pages = next;
      listeners.forEach((listener) => listener());
    },
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    refetch: vi.fn(),
  };
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("@rework/core/hooks/usePaneResize", () => ({
  usePaneResize: () => ({ width: 260, handleProps: {} }),
}));
vi.mock("@hooks/useSpaceAccess", () => ({
  useSpaceAccess: () => ({ allowed: true }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: vi.fn(), showSuccess: vi.fn() }),
}));
vi.mock("@shared/molecules/PageEmptyState/PageEmptyState", () => ({
  default: () => <div data-testid="empty-state" />,
}));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialog", () => ({
  ConfirmationDialog: (props: { open: boolean; title: string; onConfirm: () => void }) =>
    props.open ? (
      <button data-testid={props.title} onClick={props.onConfirm}>
        confirm
      </button>
    ) : null,
}));

vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", async () => {
  const { useSyncExternalStore } = await import("react");
  return {
    useMySpacesQuery: () => ({ currentData: [{ id: "team-1", kind: "team" }] }),
    useWikiPagesQuery: () => ({
      currentData: { pages: useSyncExternalStore(h.subscribe.bind(h), () => h.pages) },
      isLoading: false,
      refetch: h.refetch,
    }),
    useWikiPageQuery: ({ pageId }: { pageId: string }, { skip }: { skip: boolean }) => {
      const page = skip ? undefined : h.pages.find((candidate) => candidate.slug === pageId);
      return { currentData: page && { page, content_md: "", revision_id: "rev" }, isFetching: false };
    },
    useWikiRulesQuery: () => ({ currentData: undefined, isFetching: false }),
    useCreateWikiPageMutation: () => [vi.fn(), { isLoading: false }],
    useWriteWikiPageMutation: () => [vi.fn(), { isLoading: false }],
    useWriteWikiRulesMutation: () => [vi.fn(), { isLoading: false }],
    usePatchWikiPageMutation: () => [vi.fn()],
    useDeleteWikiPageMutation: () => [() => ({ unwrap: () => Promise.resolve({}) })],
    useSetWikiReviewMarkMutation: () => [vi.fn()],
  };
});

vi.mock("./WikiTree", () => ({ WikiTree: () => null }));
vi.mock("./WikiRevisions", () => ({ WikiRevisions: () => null }));
vi.mock("./WikiArticle", () => ({
  WikiArticle: (props: { onEdit: () => void; onNavigateRoot: () => void }) => (
    <>
      <button data-testid="edit" onClick={props.onEdit} />
      <button data-testid="root" onClick={props.onNavigateRoot} />
    </>
  ),
}));
vi.mock("./WikiEditor", () => ({
  WikiEditor: (props: { placement: { onDelete: () => void } }) => (
    <button data-testid="delete" onClick={props.placement.onDelete} />
  ),
}));

import TeamWikiPage from "./TeamWikiPage";

const page = (id: string, position: number): FakePage => ({
  page_id: `id-${id}`,
  slug: id,
  title: id,
  kind: "page",
  position,
});

describe("TeamWikiPage navigation", () => {
  let container: HTMLDivElement;
  let root: Root;
  let router: ReturnType<typeof createMemoryRouter>;

  const settle = () =>
    act(async () => {
      for (let i = 0; i < 20; i++) await Promise.resolve();
    });

  const open = async (...entries: string[]) => {
    router = createMemoryRouter(
      [
        { path: "/elsewhere", element: null },
        { path: "/team/:teamId/wiki", element: <TeamWikiPage /> },
        { path: "/team/:teamId/wiki/:slug", element: <TeamWikiPage /> },
      ],
      { initialEntries: entries, initialIndex: entries.length - 1 },
    );
    act(() => root.render(<RouterProvider router={router} />));
    await settle();
  };

  const go = async (to: string | number) => {
    await act(() => (typeof to === "number" ? router.navigate(to) : router.navigate(to)));
    await settle();
  };

  const click = async (testId: string) => {
    await act(async () => container.querySelector<HTMLButtonElement>(`[data-testid="${testId}"]`)!.click());
    await settle();
  };

  const deleteOpenPage = async () => {
    await click("edit");
    await click("delete");
    await click("rework.wiki.deleteDialog.title");
  };

  const path = () => router.state.location.pathname;

  beforeEach(() => {
    localStorage.clear();
    h.pages = [page("a", 0), page("b", 1)];
    h.refetch.mockReset();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
  });

  it("sends the root to the first page, then to the last page opened", async () => {
    await open("/team/team-1/wiki");
    expect(path()).toBe("/team/team-1/wiki/a");

    await go("/team/team-1/wiki/b");
    await go("/elsewhere");
    await go("/team/team-1/wiki");
    expect(path()).toBe("/team/team-1/wiki/b");
  });

  it("does not leave the root in the history, so Back is not stuck on it", async () => {
    await open("/elsewhere", "/team/team-1/wiki");
    expect(path()).toBe("/team/team-1/wiki/a");

    await go(-1);
    expect(path()).toBe("/elsewhere");
  });

  it("opens the first page when the reader asks for the wiki's root", async () => {
    await open("/team/team-1/wiki/b");
    await click("root");
    expect(path()).toBe("/team/team-1/wiki/a");
  });

  it("keeps a draft open when a move changes the wiki's first page", async () => {
    await open("/team/team-1/wiki");
    await click("edit");

    await act(async () => h.setPages([page("b", 0), page("a", 1)]));
    await settle();

    expect(path()).toBe("/team/team-1/wiki/a");
    expect(container.querySelector('[data-testid="delete"]')).not.toBeNull();
  });

  it("does not stay on a deleted page the cached tree still lists", async () => {
    h.refetch.mockImplementation(async () => h.setPages([page("b", 1)]));
    await open("/team/team-1/wiki/a");

    await deleteOpenPage();

    expect(h.refetch).toHaveBeenCalledTimes(1);
    expect(path()).toBe("/team/team-1/wiki/b");
  });

  it("stays on the root with the empty state after deleting the only page", async () => {
    h.pages = [page("a", 0)];
    h.refetch.mockImplementation(async () => h.setPages([]));
    await open("/team/team-1/wiki/a");

    await deleteOpenPage();

    expect(path()).toBe("/team/team-1/wiki");
    expect(container.querySelector('[data-testid="empty-state"]')).not.toBeNull();
  });
});
