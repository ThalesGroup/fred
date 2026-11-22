// @vitest-environment jsdom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act, type ComponentProps } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { WikiArticle } from "./WikiArticle";
import type { DocumentViewer } from "@shared/organisms/DocumentViewer/DocumentViewer";
const state = vi.hoisted(() => ({
  download: vi.fn().mockResolvedValue(undefined),
  preview: null as ComponentProps<typeof DocumentViewer> | null,
  read: vi.fn(),
  avatar: vi.fn(() => ({ currentData: "data:image/png;base64,cGhvdG8=" })),
}));
vi.mock("../../../../utils/downloadUtils", () => ({ downloadAuthed: state.download }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: vi.fn() }) }));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useLazyWikiPageQuery: () => [state.read],
  useGetUserAvatarQuery: state.avatar,
  useListAgentInstancesQuery: () => ({
    currentData: { items: [{ agent_instance_id: "agent-pal", display_name: "Pal renamed", role: "programmation" }] },
  }),
}));
vi.mock("@shared/organisms/DocumentViewer/DocumentViewer", () => ({
  DocumentViewer: (props: ComponentProps<typeof DocumentViewer>) => {
    state.preview = props;
    return null;
  },
}));
vi.mock("../../../../hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({ agentIconName: "smart_toy" }),
}));
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const container = document.createElement("div");
let root: ReturnType<typeof createRoot>;
afterEach(async () => {
  await act(async () => root.unmount());
});
it.each(["text/markdown", "text/plain", "text/csv"])(
  "opens and downloads a retained %s copy through Wiki authorization, without a private conversation URL",
  async (mime) => {
    state.download.mockClear();
    root = createRoot(container);
    const props: ComponentProps<typeof WikiArticle> = {
      spaceId: "space",
      pages: [],
      canEdit: false,
      isRules: false,
      onEdit: vi.fn(),
      onDelete: vi.fn(),
      onOpenHistory: vi.fn(),
      onNavigate: vi.fn(),
      onNavigateRoot: vi.fn(),
      detail: {
        page: {
          page_id: "file",
          slug: "file",
          title: "Mayonnaise.md",
          kind: "file",
          position: 0,
          updated_by: "writer",
          author_user_id: "writer",
          mime,
        },
        content_md: "",
        revision_id: "revision",
        has_preview: false,
      },
    };
    await act(async () => root.render(<WikiArticle {...props} />));
    const click = async (label: string) => {
      await act(async () =>
        [...container.querySelectorAll("button")]
          .find((button) => button.getAttribute("aria-label")?.startsWith(label))!
          .click(),
      );
    };
    expect(state.preview).toMatchObject({
      documentUid: "revision",
      fileName: "Mayonnaise.md",
      sourceUrl: "/control-plane/v1/spaces/space/wiki/revisions/revision/content",
      sourceFormat: "text",
    });
    await click("documentLibrary.download");
    expect(state.download).toHaveBeenCalledExactlyOnceWith(
      "/control-plane/v1/spaces/space/wiki/revisions/revision/content",
      "Mayonnaise.md",
    );
    await act(async () => root.render(<WikiArticle {...props} detail={{ ...props.detail, revision_id: "other" }} />));
    expect(state.preview?.documentUid).toBe("other");
    expect(state.preview?.sourceUrl).toBe("/control-plane/v1/spaces/space/wiki/revisions/other/content");
  },
);

const file = (id: string, parent = "parent") => ({
  page_id: id,
  slug: `slug-${id}`,
  title: `${id}.md`,
  kind: "file",
  parent_page_id: parent,
  position: 0,
  updated_by: "writer",
  author_user_id: "writer",
  mime: "text/markdown",
});
const articleProps = (): ComponentProps<typeof WikiArticle> => ({
  spaceId: "space",
  pages: [],
  canEdit: false,
  isRules: false,
  onEdit: vi.fn(),
  onDelete: vi.fn(),
  onOpenHistory: vi.fn(),
  onNavigate: vi.fn(),
  onNavigateRoot: vi.fn(),
  detail: {
    page: { ...file("parent"), kind: "page" },
    content_md: "Tutorial",
    revision_id: "parent-rev",
    has_preview: false,
  },
});

it("lists only directly attached files and downloads the child's published revision without opening it", async () => {
  const props = articleProps();
  props.pages = [
    {
      ...file("first"),
      agent_name: "Pal",
      agent_instance_id: "agent-pal",
      author_name: "Alice",
      size: 2048,
      updated_at: "2026-11-22T10:30:00Z",
    },
    { ...file("second"), author_name: "Bob", size: 0 },
    file("other", "elsewhere"),
    file("nested", "first"),
    { ...file("subpage"), kind: "page" },
  ];
  state.read.mockReturnValue({ unwrap: async () => ({ page: file("second"), revision_id: "child-rev" }) });
  state.download.mockClear();
  root = createRoot(container);
  await act(async () => root.render(<WikiArticle {...props} />));
  const buttons = () => [...container.querySelectorAll("button")];
  expect(container.textContent).toContain("first.md");
  expect(container.textContent).toContain("Pal");
  expect(container.textContent).toContain("code");
  expect(container.textContent).not.toContain("(agent)");
  expect(container.textContent).not.toContain("Pal renamed");
  expect(container.textContent).toContain("Bob");
  expect(container.textContent).toContain("22/11/26");
  expect(container.textContent).toContain("2 kB");
  expect(container.textContent).toContain("second.md");
  expect(container.textContent).not.toContain("other.md");
  expect(container.textContent).not.toContain("nested.md");
  expect(container.textContent).not.toContain("subpage.md");
  expect(container.querySelector('[aria-haspopup="listbox"]')).toBeNull();
  await act(async () =>
    buttons()
      .find((button) => button.textContent?.includes("first.md"))!
      .click(),
  );
  expect(props.onNavigate).toHaveBeenCalledWith("slug-first");
  await act(async () =>
    buttons()
      .find((button) => button.getAttribute("aria-label") === "documentLibrary.download: second.md")!
      .click(),
  );
  expect(state.read).toHaveBeenCalledWith({ spaceId: "space", pageId: "slug-second" });
  expect(state.download).toHaveBeenCalledExactlyOnceWith(
    "/control-plane/v1/spaces/space/wiki/revisions/child-rev/content",
    "second.md",
  );
  expect(props.onNavigate).toHaveBeenCalledTimes(1);
  await act(async () =>
    buttons()
      .find((button) => button.getAttribute("aria-label") === "chatbot.sessionAttachments.preview: second.md")!
      .click(),
  );
  expect(props.onNavigate).toHaveBeenLastCalledWith("slug-second");
});

it.each([
  ["application/pdf", false, "/content"],
  ["application/vnd.openxmlformats-officedocument.wordprocessingml.document", true, "/preview"],
])("uses the retained PDF for %s", async (mime, hasPreview, suffix) => {
  const props = articleProps();
  props.detail = { ...props.detail, page: { ...file("document"), mime }, has_preview: hasPreview };
  root = createRoot(container);
  await act(async () => root.render(<WikiArticle {...props} />));
  expect(state.preview?.sourceUrl).toBe(`/control-plane/v1/spaces/space/wiki/revisions/parent-rev${suffix}`);
  expect(state.preview?.sourceFormat).toBeUndefined();
});

it("keeps unsupported files downloadable without attempting a private or invalid preview", async () => {
  const props = articleProps();
  props.detail.page = { ...file("slides"), mime: "application/octet-stream" };
  state.preview = null;
  root = createRoot(container);
  await act(async () => root.render(<WikiArticle {...props} />));
  expect(state.preview).toBeNull();
  expect(container.textContent).toContain("rework.wiki.files.noPreview");
  expect(container.querySelector('[aria-label="documentLibrary.download: slides.md"]')).not.toBeNull();
});

it("offers deletion to editors from the file menu without exposing editing", async () => {
  const props = articleProps();
  props.canEdit = true;
  props.detail.page = file("document");
  root = createRoot(container);
  document.body.append(container);
  await act(async () => root.render(<WikiArticle {...props} />));
  expect(container.textContent).not.toContain("rework.wiki.article.edit");
  await act(async () => container.querySelector<HTMLButtonElement>('[aria-haspopup="listbox"]')!.click());
  await act(async () => document.querySelector<HTMLElement>('[role="option"]')!.click());
  expect(props.onDelete).toHaveBeenCalledExactlyOnceWith(props.detail.page);
  container.remove();
});

it("shows the revision author's real avatar in the metadata, not the publisher's", async () => {
  const props = articleProps();
  props.detail.page = {
    ...file("document"),
    author_user_id: "ada",
    author_name: "Ada",
    updated_by: "bob",
    updated_by_name: "Bob",
  };
  state.avatar.mockClear();
  root = createRoot(container);
  await act(async () => root.render(<WikiArticle {...props} />));
  expect(state.avatar).toHaveBeenCalledWith({ spaceId: "space", userId: "ada" }, expect.anything());
  expect(container.querySelector("header img")?.getAttribute("src")).toBe("data:image/png;base64,cGhvdG8=");
  expect(container.querySelector("header")?.textContent).toContain("Ada");
  expect(container.querySelector("header")?.textContent).not.toContain("Bob");
});

it("keeps an absent agent's retained name with the shared fallback pictogram", async () => {
  const props = articleProps();
  props.detail.page = { ...file("document"), agent_instance_id: "gone", agent_name: "Retired agent" };
  state.avatar.mockClear();
  root = createRoot(container);
  await act(async () => root.render(<WikiArticle {...props} />));
  expect(container.querySelector("header")?.textContent).toContain("Retired agent");
  expect(container.querySelector("header")?.textContent).toContain("smart_toy");
  expect(state.avatar).not.toHaveBeenCalled();
});
