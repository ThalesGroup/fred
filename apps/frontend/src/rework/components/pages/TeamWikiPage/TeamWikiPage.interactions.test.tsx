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
  useParams: () => ({ teamId: "team-1", slug: h.slug }),
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
  slug: "s",
  patchPage: vi.fn(),
  writePage: vi.fn(),
  showError: vi.fn(),
  editorProps: null as null | {
    onSave: (content: string, placement: { title: string; parentId: string } | null) => void;
    onTakeTheirs: (content: string) => void;
    onCancel: () => void;
    initialContent: string;
    initialFormat?: { body_md: string; frontmatter_prefix: string } | null;
    conflict: { currentContentMd: string } | null;
  },
  detail: {
    page: { page_id: "page-1", slug: "s", title: "S", kind: "page" },
    content_md: "hello",
    format: { body_md: "hello", frontmatter_prefix: "" } as { body_md: string; frontmatter_prefix: string } | null,
    revision_id: "rev-A",
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
  usePrepareWikiDocumentMutation: () => [vi.fn()],
  usePatchWikiPageMutation: () => [h.patchPage],
  useDeleteWikiPageMutation: () => [vi.fn()],
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
  WikiArticle: (props: { onEdit: () => void }) => (
    <button data-testid="edit" onClick={props.onEdit}>
      edit
    </button>
  ),
}));

import TeamWikiPage from "./TeamWikiPage";

describe("TeamWikiPage — interactions", () => {
  let container: HTMLDivElement;
  let root: Root;

  const settle = async () => {
    await act(async () => {
      for (let i = 0; i < 10; i++) await Promise.resolve();
    });
  };

  beforeEach(() => {
    h.slug = "s";
    h.detail.page = { page_id: "page-1", slug: "s", title: "S", kind: "page" };
    h.detail.content_md = "hello";
    h.detail.format = { body_md: "hello", frontmatter_prefix: "" };
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
          data: {
            detail: "stale",
            current_revision_id: "rev-B",
            current_content_md: "---\ntype: topic\n---\nB",
            current_format: { body_md: "B", frontmatter_prefix: "---\ntype: topic\n---\n" },
          },
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

  it.each(["\n", "\r\n"])("passes the complete %j source and its format snapshot to the editor", async (newline) => {
    const prefix = [
      "---",
      "type: topic",
      "x-extra:",
      "  huge: 123456789012345678901234567890",
      "  nested: [a, {precise: 0.1234567890123456789}]",
      "---",
      "",
    ].join(newline);
    h.detail.format = { body_md: "hello", frontmatter_prefix: prefix };
    h.detail.content_md = prefix + "hello";
    h.writePage.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    await openEditor();
    expect(h.editorProps!.initialContent).toBe(prefix + "hello");
    expect(h.editorProps!.initialFormat).toEqual(h.detail.format);
    await act(async () => h.editorProps!.onSave(prefix + "new text", null));
    expect(h.writePage).toHaveBeenLastCalledWith({
      spaceId: "team-1",
      pageId: "page-1",
      updateWikiContentRequest: { content_md: prefix + "new text", base_revision_id: "rev-A" },
    });
  });

  it("edits the raw stored text when its header has no format view", async () => {
    const stored = "---\nstatus: null\n---\nbody";
    h.detail.content_md = stored;
    h.detail.format = null;
    h.writePage.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    await openEditor();
    expect(h.editorProps!.initialContent).toBe(stored);
    await save(null);
    expect(h.writePage).toHaveBeenLastCalledWith({
      spaceId: "team-1",
      pageId: "page-1",
      updateWikiContentRequest: { content_md: "new text", base_revision_id: "rev-A" },
    });
  });

  it("rebases on the raw newer text when the conflict has no format view", async () => {
    h.detail.format = { body_md: "hello", frontmatter_prefix: "---\ntype: topic\n---\n" };
    const theirs = "---\nstatus: null\n---\nTheirs";
    h.writePage
      .mockReturnValueOnce({
        unwrap: () =>
          Promise.reject({
            status: 409,
            data: { current_revision_id: "rev-B", current_content_md: theirs, current_format: null },
          }),
      })
      .mockReturnValueOnce({ unwrap: () => Promise.resolve({}) });
    await openEditor();
    await save(null);
    expect(h.showError).not.toHaveBeenCalled();
    expect(h.editorProps!.conflict!.currentContentMd).toBe(theirs);
    await save(null);
    expect(h.writePage).toHaveBeenLastCalledWith({
      spaceId: "team-1",
      pageId: "page-1",
      updateWikiContentRequest: { content_md: "new text", base_revision_id: "rev-B" },
    });
  });

  it("loads a conflict body with the prefix and revision of the same snapshot", async () => {
    h.detail.format = { body_md: "hello", frontmatter_prefix: "---\ntype: topic\n---\n" };
    const prefix = "---\r\ntype: decision\r\nx-number: 12345678901234567890123456789\r\n---\r\n";
    h.writePage
      .mockReturnValueOnce({
        unwrap: () =>
          Promise.reject({
            status: 409,
            data: {
              current_revision_id: "rev-B",
              current_content_md: prefix + "Theirs",
              current_format: { body_md: "Theirs", frontmatter_prefix: prefix },
            },
          }),
      })
      .mockReturnValueOnce({ unwrap: () => Promise.resolve({}) });
    await openEditor();
    await save(null);
    expect(h.editorProps!.conflict!.currentContentMd).toBe(prefix + "Theirs");
    await act(async () => h.editorProps!.onTakeTheirs(h.editorProps!.conflict!.currentContentMd));
    expect(h.editorProps!.initialContent).toBe(prefix + "Theirs");
    expect(h.editorProps!.initialFormat).toEqual({ body_md: "Theirs", frontmatter_prefix: prefix });
    await act(async () => h.editorProps!.onSave(prefix + "new text", null));
    expect(h.writePage).toHaveBeenLastCalledWith({
      spaceId: "team-1",
      pageId: "page-1",
      updateWikiContentRequest: { content_md: prefix + "new text", base_revision_id: "rev-B" },
    });
  });

  it("ignores a late conflict after navigating to another editor", async () => {
    let reject!: (reason: unknown) => void;
    const pending = new Promise((_, fail) => {
      reject = fail;
    });
    h.writePage.mockReturnValue({ unwrap: () => pending });
    await openEditor();
    await save(null);
    h.slug = "other";
    h.detail.page = { page_id: "page-2", slug: "other", title: "Other", kind: "page" };
    h.detail.format = { body_md: "Other body", frontmatter_prefix: "---\ntype: reference\n---\n" };
    h.detail.content_md = "---\ntype: reference\n---\nOther body";
    mount();
    await settle();
    await act(async () => container.querySelector<HTMLButtonElement>('[data-testid="edit"]')!.click());
    await settle();
    await act(async () =>
      reject({
        status: 409,
        data: {
          current_revision_id: "late",
          current_content_md: "Old page",
          current_format: { frontmatter_prefix: "---\ntype: decision\n---\n", body_md: "Old page" },
        },
      }),
    );
    expect(h.editorProps!.initialContent).toBe(h.detail.content_md);
    expect(h.editorProps!.conflict).toBeNull();
    h.writePage.mockReturnValue({ unwrap: () => Promise.resolve({}) });
    await save(null);
    expect(h.writePage).toHaveBeenLastCalledWith({
      spaceId: "team-1",
      pageId: "page-2",
      updateWikiContentRequest: { content_md: "new text", base_revision_id: "rev-A" },
    });
  });

  it.each(["conflict", "success", "metadata"])(
    "ignores an old %s after closing and reopening the same page",
    async (outcome) => {
      let resolve!: (value: unknown) => void;
      let reject!: (reason: unknown) => void;
      const pending = new Promise((done, fail) => {
        resolve = done;
        reject = fail;
      });
      h.patchPage.mockReturnValue({ unwrap: () => pending });
      h.writePage.mockReturnValue({ unwrap: () => pending });
      await openEditor();
      await save(outcome === "metadata" ? { title: "Old rename", parentId: "" } : null);
      await act(async () => h.editorProps!.onCancel());
      await openEditor();
      await act(async () =>
        outcome === "conflict"
          ? reject({
              status: 409,
              data: {
                current_revision_id: "late",
                current_content_md: "Old page",
                current_format: { frontmatter_prefix: "---\ntype: decision\n---\n", body_md: "Old page" },
              },
            })
          : resolve({}),
      );
      expect(container.querySelector('[data-testid="wiki-editor"]')).not.toBeNull();
      expect(h.editorProps!.initialContent).toBe("hello");
      expect(h.editorProps!.conflict).toBeNull();
      if (outcome === "metadata") expect(h.writePage).not.toHaveBeenCalled();
      h.writePage.mockReturnValue({ unwrap: () => Promise.resolve({}) });
      await save(null);
      expect(h.writePage).toHaveBeenLastCalledWith({
        spaceId: "team-1",
        pageId: "page-1",
        updateWikiContentRequest: { content_md: "new text", base_revision_id: "rev-A" },
      });
    },
  );

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
