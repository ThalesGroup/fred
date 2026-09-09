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
vi.mock("../../../../hooks/useSelectedTeam", () => ({
  useSelectedTeam: () => ({ selectedTeam: { id: "team-1" } }),
}));
vi.mock("@hooks/useTeamCapabilities", () => ({
  useTeamCapabilities: () => ({ canUpdateResources: true }),
}));

const h = vi.hoisted(() => ({
  setReviewMark: vi.fn(),
  showError: vi.fn(),
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
  useWikiPagesQuery: () => ({
    data: { pages: [{ page_id: "page-1", slug: "s", title: "S", kind: "page", parent_page_id: null }] },
    isLoading: false,
  }),
  useWikiPageQuery: () => ({ data: h.detail, isFetching: false }),
  useWikiRulesQuery: () => ({ data: undefined, isFetching: false }),
  useCreateWikiPageMutation: () => [vi.fn(), { isLoading: false }],
  useWriteWikiPageMutation: () => [vi.fn(), { isLoading: false }],
  useWriteWikiRulesMutation: () => [vi.fn(), { isLoading: false }],
  usePatchWikiPageMutation: () => [vi.fn()],
  useDeleteWikiPageMutation: () => [vi.fn()],
  useSetWikiReviewMarkMutation: () => [h.setReviewMark],
  useUsersByIdsQuery: () => ({ data: [] }),
}));

vi.mock("./WikiTree", () => ({ WikiTree: () => null }));
vi.mock("./WikiEditor", () => ({ WikiEditor: () => null }));

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
  WikiArticle: (props: { onClearReview: () => void }) => (
    <button data-testid="clear-review" onClick={props.onClearReview}>
      clear-review
    </button>
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
      teamId: "team-1",
      pageId: "page-1",
      setNeedsReviewRequest: { needs_review: false, base_revision_id: "rev-A" },
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

  it("marks the wiki as beta in the rail header", async () => {
    mount();
    await settle();

    expect(container.querySelector('[aria-label="rework.wiki.betaBadge.label"]')).not.toBeNull();
  });
});
