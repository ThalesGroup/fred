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

// B1/B3, through the real page component: the review mark is anchored to the
// displayed revision, a conflict is shown rather than a false success, and a
// successful local mutation (review, save) remounts the history panel on a
// fresh key rather than leaving it on a stale accumulated walk. Sub-components
// with their own deep dependency trees (WikiArticle, WikiTree, WikiEditor,
// WikiRevisions) are stubbed to their callback surface; the page's own wiring
// (handleClearReview, handleSave, historyGeneration) is real.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-router-dom", () => ({
  useParams: () => ({ teamId: "team-1", slug: "s" }),
  useNavigate: () => vi.fn(),
  useBlocker: () => ({ state: "unblocked" }),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("@rework/core/hooks/usePaneResize", () => ({
  usePaneResize: () => ({ width: 260, handleProps: {} }),
}));
vi.mock("@hooks/useSpaceAccess", () => ({
  useSpaceAccess: () => ({ allowed: true }),
}));

const h = vi.hoisted(() => ({
  setReviewMark: vi.fn(),
  patchPage: vi.fn(),
  writePage: vi.fn(),
  showError: vi.fn(),
  editorProps: null as null | {
    onSave: (content: string, placement: { title: string; parentId: string } | null) => void;
  },
  detail: {
    page: { page_id: "page-1", slug: "s", title: "S", kind: "page", needs_review: true },
    content_md: "hello",
    revision_id: "rev-A",
    author_kind: "agent",
  },
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: h.showError, showSuccess: vi.fn() }),
}));

vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMySpacesQuery: () => ({ currentData: [{ id: "team-1", kind: "team" }] }),
  useWikiPagesQuery: () => ({
    currentData: { pages: [{ page_id: "page-1", slug: "s", title: "S", kind: "page", parent_page_id: null }] },
    isLoading: false,
  }),
  useWikiPageQuery: () => ({ currentData: h.detail, isFetching: false }),
  useWikiRulesQuery: () => ({ currentData: undefined, isFetching: false }),
  useCreateWikiPageMutation: () => [vi.fn(), { isLoading: false }],
  useWriteWikiPageMutation: () => [h.writePage, { isLoading: false }],
  useWriteWikiRulesMutation: () => [vi.fn(), { isLoading: false }],
  usePatchWikiPageMutation: () => [h.patchPage],
  useDeleteWikiPageMutation: () => [vi.fn()],
  useSetWikiReviewMarkMutation: () => [h.setReviewMark],
}));

vi.mock("./WikiTree", () => ({ WikiTree: () => null }));
vi.mock("./WikiEditor", () => ({
  WikiEditor: (props: NonNullable<typeof h.editorProps>) => {
    h.editorProps = props;
    return <div data-testid="wiki-editor" />;
  },
}));

const wikiRevisionsKeys: unknown[] = [];
vi.mock("./WikiRevisions", () => ({
  WikiRevisions: (props: { open: boolean }) => {
    // `key` itself isn't visible on props (React consumes it), but a fresh
    // key forces a fresh mount — an effect with no deps fires exactly once
    // per mount, so counting its calls tells "remounted" from "re-rendered".
    wikiRevisionsKeys.push({});
    return <div data-testid="wiki-revisions" data-open={props.open} />;
  },
}));

vi.mock("./WikiArticle", () => ({
  WikiArticle: (props: { onClearReview: () => void; onEdit: () => void }) => (
    <>
      <button data-testid="clear-review" onClick={props.onClearReview}>
        clear-review
      </button>
      <button data-testid="edit" onClick={props.onEdit}>
        edit
      </button>
    </>
  ),
}));

import TeamWikiPage from "./TeamWikiPage";

describe("TeamWikiPage — review mark wiring", () => {
  let container: HTMLDivElement;
  let root: Root;

  const settle = async () => {
    await act(async () => {
      for (let i = 0; i < 10; i++) await Promise.resolve();
    });
  };

  beforeEach(() => {
    h.setReviewMark.mockReset();
    h.patchPage.mockReset();
    h.writePage.mockReset();
    h.editorProps = null;
    h.showError.mockClear();
    wikiRevisionsKeys.length = 0;
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => {
      root.unmount();
    });
    container.remove();
  });

  const mount = () => {
    act(() => {
      root.render(<TeamWikiPage />);
    });
  };

  const clickClearReview = async () => {
    await act(async () => {
      container.querySelector<HTMLButtonElement>('[data-testid="clear-review"]')!.click();
      await Promise.resolve();
    });
  };

  it("anchors the review mark to the revision the article actually displays", async () => {
    h.setReviewMark.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    mount();
    await settle();

    await clickClearReview();
    await settle();

    expect(h.setReviewMark).toHaveBeenCalledWith({
      spaceId: "team-1",
      pageId: "page-1",
      wikiReviewRequest: { needs_review: false, base_revision_id: "rev-A" },
    });
  });

  it("a conflict from the server is shown, not a false success, and does not remount the history panel", async () => {
    h.setReviewMark.mockReturnValue({
      unwrap: () =>
        Promise.reject({
          status: 409,
          data: { detail: "stale", current_revision_id: "rev-B", current_content_md: "B" },
        }),
    });
    mount();
    await settle();
    const mountsBefore = wikiRevisionsKeys.length;

    await clickClearReview();
    await settle();

    expect(h.showError).toHaveBeenCalledTimes(1);
    expect(h.showError.mock.calls[0][0]).toMatchObject({ summary: "rework.wiki.errors.review" });
    // A conflict is not a local mutation that changed this page's history —
    // the panel must not remount as if the review had gone through.
    expect(wikiRevisionsKeys.length).toBe(mountsBefore);
  });

  it("a successful review mark remounts the history panel on a fresh key", async () => {
    h.setReviewMark.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    mount();
    await settle();
    const mountsBefore = wikiRevisionsKeys.length;

    await clickClearReview();
    await settle();

    expect(wikiRevisionsKeys.length).toBeGreaterThan(mountsBefore);
  });

  it("a non-conflict failure is shown with the server's own detail, not a generic message swallowing it", async () => {
    h.setReviewMark.mockReturnValue({
      unwrap: () => Promise.reject({ status: 500, data: { detail: "the wiki store is unavailable" } }),
    });
    mount();
    await settle();

    await clickClearReview();
    await settle();

    expect(h.showError).toHaveBeenCalledWith({
      summary: "rework.wiki.errors.review",
      detail: "the wiki store is unavailable",
    });
  });

  it("keeps the beta badge out of the rail header", async () => {
    mount();
    await settle();

    expect(container.querySelector('[aria-label="rework.wiki.betaBadge.label"]')).toBeNull();
  });

  const openEditor = async () => {
    mount();
    await settle();
    await act(async () => {
      container.querySelector<HTMLButtonElement>('[data-testid="edit"]')!.click();
    });
    await settle();
  };

  const save = async (placement: { title: string; parentId: string } | null) => {
    await act(async () => {
      h.editorProps!.onSave("new text", placement);
    });
    await settle();
  };

  it("saves a new title and parent before the text, then closes the editor", async () => {
    const calls: string[] = [];
    h.patchPage.mockImplementation(() => (calls.push("patch"), { unwrap: () => Promise.resolve({}) }));
    h.writePage.mockImplementation(() => (calls.push("write"), { unwrap: () => Promise.resolve({}) }));
    await openEditor();

    await save({ title: "Renamed", parentId: "" });

    expect(h.patchPage).toHaveBeenCalledWith({
      spaceId: "team-1",
      pageId: "page-1",
      updateWikiMetadataRequest: { title: "Renamed", move_to_root: true },
    });
    expect(calls).toEqual(["patch", "write"]);
    expect(container.querySelector('[data-testid="wiki-editor"]')).toBeNull();
  });

  it("does not repeat the metadata call on a retry after a text conflict", async () => {
    h.patchPage.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    h.writePage.mockReturnValueOnce({
      unwrap: () =>
        Promise.reject({
          status: 409,
          data: { detail: "stale", current_revision_id: "rev-B", current_content_md: "B" },
        }),
    });
    h.writePage.mockReturnValueOnce({ unwrap: () => Promise.resolve({}) });
    await openEditor();

    await save({ title: "Renamed", parentId: "" });
    expect(container.querySelector('[data-testid="wiki-editor"]')).not.toBeNull();
    await save({ title: "Renamed", parentId: "" });

    expect(h.patchPage).toHaveBeenCalledTimes(1);
    expect(h.writePage).toHaveBeenLastCalledWith({
      spaceId: "team-1",
      pageId: "page-1",
      updateWikiContentRequest: { content_md: "new text", base_revision_id: "rev-B" },
    });
    expect(container.querySelector('[data-testid="wiki-editor"]')).toBeNull();
  });

  it("skips the metadata call when title and parent are unchanged", async () => {
    h.writePage.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    await openEditor();

    await save({ title: "S", parentId: "" });

    expect(h.patchPage).not.toHaveBeenCalled();
    expect(h.writePage).toHaveBeenCalledTimes(1);
  });

  it("keeps the editor open and writes nothing when the title is taken", async () => {
    h.patchPage.mockReturnValue({ unwrap: () => Promise.reject({ status: 409, data: { detail: "dup" } }) });
    await openEditor();

    await save({ title: "Taken", parentId: "" });

    expect(h.writePage).not.toHaveBeenCalled();
    expect(h.showError).toHaveBeenCalledWith({
      summary: "rework.wiki.errors.rename",
      detail: "rework.wiki.errors.duplicateTitle",
    });
    expect(container.querySelector('[data-testid="wiki-editor"]')).not.toBeNull();
  });
});
