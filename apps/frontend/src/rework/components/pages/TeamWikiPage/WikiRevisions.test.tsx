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

// B2/B3: the real `enhancedControlPlaneApi` store, not hand-mocked hook
// returns — a mock can't prove a tag actually triggers a refetch, or that
// reopening the panel really issues a fresh request. Only `KeycloakService`
// (token plumbing, irrelevant here) and `useToast` (asserted on directly) are
// mocked; the query/mutation hooks, the cache, and the tag machinery are real.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: {
    ensureFreshToken: async () => true,
    GetToken: () => "test-token",
    CallLogout: vi.fn(),
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const showError = vi.fn();
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError, showSuccess: vi.fn() }),
}));

import { enhancedControlPlaneApi } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { WikiRevisions } from "./WikiRevisions";

interface FakeRevision {
  revision_id: string;
  status: string;
  author_user_id: string;
  author_kind: string;
  agent_instance_id: string | null;
  session_id: string | null;
  created_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
}

const PAGE_SIZE = 2;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

describe("WikiRevisions — against the real controlPlaneApi store", () => {
  let allRevisions: FakeRevision[];
  let restoreShouldFail: boolean;
  let revisionsGetCount: number;
  let store: ReturnType<typeof makeStore>;
  let container: HTMLDivElement;
  let root: Root;

  function makeStore() {
    return configureStore({
      reducer: { [enhancedControlPlaneApi.reducerPath]: enhancedControlPlaneApi.reducer },
      middleware: (getDefaultMiddleware) => getDefaultMiddleware().concat(enhancedControlPlaneApi.middleware),
    });
  }

  function seedRevisions(count: number) {
    allRevisions = Array.from({ length: count }, (_, i) => ({
      revision_id: `rev-${count - i}`,
      status: "published",
      author_user_id: "alice",
      author_kind: "human",
      agent_instance_id: null,
      session_id: null,
      created_at: new Date(2026, 0, count - i).toISOString(),
      reviewed_at: null,
      reviewed_by: null,
    }));
  }

  function revisionsPage(cursor: string | null) {
    const startIndex = cursor ? allRevisions.findIndex((r) => r.revision_id === cursor) + 1 : 0;
    const slice = allRevisions.slice(startIndex, startIndex + PAGE_SIZE);
    const reachedEnd = startIndex + PAGE_SIZE >= allRevisions.length;
    return {
      revisions: slice,
      contents: Object.fromEntries(slice.map((r) => [r.revision_id, `content of ${r.revision_id}`])),
      next_cursor: reachedEnd || slice.length === 0 ? null : slice[slice.length - 1].revision_id,
    };
  }

  async function route(input: string | Request, init?: RequestInit): Promise<Response> {
    // `fetchBaseQuery` calls the global `fetch` with a `Request` object in
    // this RTK Query version, not a bare URL string plus init.
    const asRequest = input instanceof Request ? input : null;
    const u = new URL(typeof input === "string" ? input : input.url, "http://localhost");
    const method = (asRequest?.method ?? init?.method ?? "GET").toUpperCase();
    const rawBody = asRequest ? await asRequest.clone().text() : String(init?.body ?? "");

    if (u.pathname.endsWith("/revisions") && method === "GET") {
      revisionsGetCount += 1;
      const cursor = u.searchParams.get("cursor");
      return jsonResponse(revisionsPage(cursor));
    }
    if (u.pathname.endsWith("/review") && method === "POST") {
      const body = JSON.parse(rawBody || "{}") as { needs_review: boolean; base_revision_id?: string | null };
      const current = allRevisions[0];
      if (body.base_revision_id !== current.revision_id) {
        return jsonResponse(
          { detail: "stale", current_revision_id: current.revision_id, current_content_md: "current" },
          409,
        );
      }
      current.reviewed_at = body.needs_review ? null : "2026-09-08T10:00:00Z";
      current.reviewed_by = body.needs_review ? null : "bob";
      return jsonResponse({
        page_id: "page-1",
        slug: "s",
        title: "S",
        kind: "page",
        needs_review: body.needs_review,
      });
    }
    if (u.pathname.endsWith("/restore") && method === "POST") {
      if (restoreShouldFail) return jsonResponse({ detail: "boom" }, 500);
      return jsonResponse({
        page: { page_id: "page-1", slug: "s", title: "S", kind: "page", needs_review: false },
        content_md: "restored",
        revision_id: "rev-restored",
      });
    }
    if (u.pathname.endsWith("/users/by-ids")) {
      return jsonResponse([]);
    }
    throw new Error(`Unhandled fetch ${method} ${u.pathname}`);
  }

  function renderPanel(props: Partial<{ open: boolean; currentRevisionId: string | null }> = {}) {
    act(() => {
      root.render(
        <Provider store={store}>
          <WikiRevisions
            open={props.open ?? true}
            teamId="team-1"
            pageId="page-1"
            currentRevisionId={props.currentRevisionId ?? allRevisions[0]?.revision_id ?? null}
            canRestore
            onClose={() => {}}
          />
        </Provider>,
      );
    });
  }

  const settle = async () => {
    await act(async () => {
      for (let i = 0; i < 15; i++) {
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
    });
  };

  const findButtonByText = (text: string) =>
    Array.from(container.querySelectorAll("button")).find((b) => b.textContent === text) ?? null;

  const revisionRowCount = () => container.querySelectorAll("ul li").length;

  beforeEach(() => {
    seedRevisions(5);
    restoreShouldFail = false;
    revisionsGetCount = 0;
    showError.mockClear();
    vi.stubGlobal("fetch", (input: string | Request, init?: RequestInit) => route(input, init));
    store = makeStore();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it("a review mark's HISTORY tag makes an already-open panel refetch and show the certification", async () => {
    renderPanel();
    await settle();
    expect(revisionRowCount()).toBe(PAGE_SIZE); // base page only, no review entry yet

    // Simulates what TeamWikiPage's handleClearReview does: dispatch the real
    // mutation with the currently-displayed revision as its base.
    await act(async () => {
      await store.dispatch(
        enhancedControlPlaneApi.endpoints.setReviewMarkControlPlaneV1TeamsTeamIdWikiPagesPageIdReviewPost.initiate({
          teamId: "team-1",
          pageId: "page-1",
          setNeedsReviewRequest: { needs_review: false, base_revision_id: allRevisions[0].revision_id },
        }),
      );
    });
    await settle();

    // Without the HISTORY-${teamId}-${pageId} tag on setReviewMark, this
    // panel's own subscribed query never refetches and the count stays at
    // PAGE_SIZE with no review entry.
    expect(revisionRowCount()).toBe(PAGE_SIZE + 1);
    expect(container.textContent).toContain("rework.wiki.history.event.review");
  });

  it("reopening the panel restarts the walk from the first page", async () => {
    renderPanel();
    await settle();

    const loadOlder = findButtonByText("rework.wiki.history.loadMore");
    expect(loadOlder).not.toBeNull();
    act(() => {
      loadOlder!.click();
    });
    await settle();
    expect(revisionRowCount()).toBe(PAGE_SIZE * 2); // two pages accumulated

    renderPanel({ open: false });
    await settle();
    renderPanel({ open: true });
    await settle();

    // The accumulated walk was dropped — back to just the first page.
    expect(revisionRowCount()).toBe(PAGE_SIZE);
  });

  it("reopening on the first page with no mutation still issues a fresh GET and shows the same history", async () => {
    renderPanel();
    await settle();
    expect(revisionRowCount()).toBe(PAGE_SIZE);
    const getsBefore = revisionsGetCount;

    renderPanel({ open: false });
    await settle();
    renderPanel({ open: true });
    await settle();

    // `fetchCursor` never changed (it was already the base page), so an arg
    // change alone would never have triggered this request.
    expect(revisionsGetCount).toBeGreaterThan(getsBefore);
    // Identical content must still render — not an empty panel because RTK
    // Query's structural sharing reused the same object reference.
    expect(revisionRowCount()).toBe(PAGE_SIZE);
  });

  it("a server-side change while closed, with no local invalidation, is visible after reopening", async () => {
    renderPanel();
    await settle();
    expect(revisionRowCount()).toBe(PAGE_SIZE);
    expect(container.textContent).not.toContain("carol");

    renderPanel({ open: false });
    await settle();

    // Purely server-side: nothing here dispatches a mutation or invalidates
    // any RTK Query tag — the only thing that changes is what the next GET
    // for this same page returns.
    allRevisions.unshift({
      revision_id: "rev-new",
      status: "published",
      author_user_id: "carol",
      author_kind: "human",
      agent_instance_id: null,
      session_id: null,
      created_at: new Date(2026, 5, 1).toISOString(),
      reviewed_at: null,
      reviewed_by: null,
    });

    renderPanel({ open: true, currentRevisionId: "rev-new" });
    await settle();

    expect(container.textContent).toContain("carol");
  });

  it("a failed restore shows an error and leaves the history exactly as it was", async () => {
    restoreShouldFail = true;
    renderPanel();
    await settle();

    const restoreButtons = Array.from(container.querySelectorAll('[aria-label="rework.wiki.history.restore"]'));
    expect(restoreButtons.length).toBeGreaterThan(0);
    await act(async () => {
      (restoreButtons[0] as HTMLElement).click();
      await Promise.resolve();
    });
    await settle();

    expect(showError).toHaveBeenCalledTimes(1);
    expect(showError.mock.calls[0][0]).toMatchObject({ summary: "rework.wiki.errors.restore" });
    // No false success: still the pre-restore first page, not reset to empty
    // and not showing a phantom new revision.
    expect(revisionRowCount()).toBe(PAGE_SIZE);
  });
});
