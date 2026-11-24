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

import { configureStore } from "@reduxjs/toolkit";
import { Provider } from "react-redux";
import { act, type ComponentProps } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SessionAttachment } from "@rework/types/attachments";
import type { ConversationFile } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import type { DocumentPreviewDrawerProps } from "../DocumentPreviewDrawer/DocumentPreviewDrawer";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const download = vi.hoisted(() => vi.fn());
const viewer = vi.hoisted(() => ({ props: null as DocumentPreviewDrawerProps | null }));
vi.mock("../../../../../utils/downloadUtils", () => ({ downloadAuthed: download }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../InlineDrawer/InlineDrawer", () => ({
  InlineDrawer: ({ children }: { children: React.ReactNode }) => <aside>{children}</aside>,
}));
vi.mock("../DocumentPreviewDrawer/DocumentPreviewDrawer", () => ({
  default: (props: DocumentPreviewDrawerProps) => {
    viewer.props = props;
    return <div data-preview-open />;
  },
}));

import { writableFilename } from "@rework/features/capabilities/writable_document/writableDocumentUtils";
import { SessionAttachmentsDrawer } from "./SessionAttachmentsDrawer";
import writableDocumentReducer, {
  upsertFromPart,
} from "@rework/features/capabilities/writable_document/writableDocumentSlice";
import {
  writableDocumentCapabilityApi as documentsApi,
  type WritableDocumentResponse,
} from "@rework/features/capabilities/writable_document/api/writableDocumentCapabilityOpenApi";
import { capabilityRoutingSlice, setCapabilityBaseUrls } from "../../../../../common/capabilityRoutingSlice";
import { sidePanelOpenRequestSlice } from "@rework/features/capabilities/sidePanelOpenRequestSlice";

vi.mock("../../../../../security/KeycloakService", () => ({
  KeyCloakService: { GetToken: () => "document-token", ensureFreshToken: async () => true },
}));
vi.mock("../Toast/ToastProvider", () => ({ useToast: () => ({ showError: vi.fn() }) }));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../../../slices/controlPlane/controlPlaneApiEnhancements")>()),
  useMySpacesQuery: () => ({ currentData: [{ id: "space", kind: "team", name: "Cooking" }] }),
}));

vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-router-dom")>()),
  useParams: () => ({ teamId: "space" }),
}));
vi.mock("@rework/features/teamWiki/ConversationFilesWikiDialog", () => ({
  ConversationFilesWikiDialog: ({
    sessionId,
    files,
    onClose,
  }: {
    sessionId: string;
    files: { key: string }[];
    onClose: () => void;
  }) => (
    <div data-share-document={`${sessionId}/${files.map((file) => file.key).join(",")}`}>
      <button onClick={onClose}>cancel-share</button>
    </div>
  ),
}));

const makeStore = () =>
  configureStore({
    reducer: {
      writableDocument: writableDocumentReducer,
      capabilityRouting: capabilityRoutingSlice.reducer,
      capabilitySidePanelOpenRequest: sidePanelOpenRequestSlice.reducer,
      [documentsApi.reducerPath]: documentsApi.reducer,
    },
    middleware: (getDefault) => getDefault().concat(documentsApi.middleware),
  });
let store: ReturnType<typeof makeStore>;

const attachment: SessionAttachment = {
  attachmentId: "att-1",
  documentUid: "att-1",
  sessionId: "session",
  name: "notes.md",
  mime: "text/markdown",
  sizeBytes: 1024,
  summaryMd: "",
  status: "ready",
};
const file: ConversationFile = {
  document_id: "deck",
  content_id: "v1",
  preview_content_id: "pdf-v1",
  name: "Slides.pptx",
  path: "internal/Slides.pptx",
  mime: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  size: 2048,
  sha256: "hash",
  updated_at: "2026-11-07",
};
let container: HTMLDivElement;
let root: Root;
let props: ComponentProps<typeof SessionAttachmentsDrawer>;
function renderDrawer(overrides: Partial<typeof props> = {}) {
  store = makeStore();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  props = {
    open: true,
    onClose: vi.fn(),
    attachments: [attachment],
    onDelete: vi.fn(),
    spaceId: "space",
    sessionId: "session",
    ...overrides,
  };
  rerender();
}
function rerender(overrides: Partial<typeof props> = {}) {
  props = { ...props, ...overrides };
  act(() =>
    root.render(
      <Provider store={store}>
        <SessionAttachmentsDrawer {...props} />
      </Provider>,
    ),
  );
}
function button(label: string) {
  return Array.from(container.querySelectorAll("button")).find((element) => element.textContent === label)!;
}
async function click(element: Element) {
  expect(element).toBeTruthy();
  await act(async () => element.dispatchEvent(new MouseEvent("click", { bubbles: true })));
}
const text = () => container.textContent ?? "";
const previewButton = () =>
  container.querySelector<HTMLButtonElement>('button[aria-label="chatbot.sessionAttachments.preview"]');
const menuButton = () => container.querySelector<HTMLButtonElement>('button[aria-haspopup="listbox"]')!;
const option = (label: string) =>
  Array.from(document.querySelectorAll('[role="option"]')).find((element) => element.textContent?.includes(label));
async function selectAction(label: string) {
  await click(menuButton());
  await click(option(label)!);
}
const downloadFile = () => selectAction("chatbot.sessionAttachments.download");
const confirmDelete = () =>
  click(
    Array.from(document.querySelectorAll('[role="alertdialog"] button')).find(
      (el) => el.textContent === "rework.resources.action.delete",
    )!,
  );
const deleteFile = async () => {
  await selectAction("rework.resources.action.delete");
  await confirmDelete();
};

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  download.mockReset();
  viewer.props = null;
  store.dispatch(documentsApi.util.resetApiState());
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("conversation files drawer", () => {
  it("lists three workspace files with dates alongside CP attachments, and reads the current bytes", async () => {
    const filesUrl = "/native/v1/agents/sessions/session/workspace/files";
    renderDrawer({
      files: [file],
      workspaceFilesUrl: filesUrl,
      workspaceFiles: [
        { path: "compliance-matrix.csv", name: "compliance-matrix.csv", size: 1024, modified: "2026-11-12T08:00:00Z" },
        { path: "bid-recommendation.md", name: "bid-recommendation.md", size: 12, modified: "2026-11-12T08:01:00Z" },
        { path: "plans/response plan.md", name: "response plan.md", size: 23, modified: "2026-11-12T08:02:00Z" },
      ],
    });
    expect(container.querySelectorAll("section")).toHaveLength(3);
    expect(container.querySelectorAll("time")).toHaveLength(3);
    expect(container.querySelector("time")?.dateTime).toBe("2026-11-12T08:00:00Z");
    for (const name of [
      "compliance-matrix.csv",
      "bid-recommendation.md",
      "response plan.md",
      "Slides.pptx",
      "notes.md",
    ])
      expect(text()).toContain(name);
    expect(text()).toContain("1 kB");
    await click(previewButton()!);
    expect(viewer.props?.target).toMatchObject({
      sourceFormat: "text",
      sourceUrl: filesUrl.replace("/files", "/content?path=compliance-matrix.csv"),
    });
    await downloadFile();
    expect(download).toHaveBeenCalledWith(
      filesUrl.replace("/files", "/content?path=compliance-matrix.csv"),
      "compliance-matrix.csv",
    );
  });
  it.each([
    { mime: "application/zip", preview_content_id: null, preview: false },
    { mime: "application/pdf", preview_content_id: null, preview: true },
  ])("offers preview only when available: $mime", async ({ mime, preview_content_id, preview }) => {
    renderDrawer({ files: [{ ...file, mime, preview_content_id }], attachments: [] });
    expect(!!previewButton()).toBe(preview);
    const name = container.querySelector<HTMLElement>('span[tabindex="0"]')!;
    await click(name);
    expect(viewer.props).toBeNull();
    await downloadFile();
    expect(download).toHaveBeenCalledOnce();
    await click(menuButton());
    expect(option("rework.resources.action.delete")).toBeUndefined();
  });
  it("keeps unavailable attachment bytes out of preview and download actions", async () => {
    renderDrawer({ attachments: [{ ...attachment, documentUid: undefined, status: "uploading" }] });
    expect(previewButton()).toBeNull();
    expect(text()).toContain("chatbot.attachmentChip.uploading");
    await click(menuButton());
    expect(option("chatbot.sessionAttachments.download")).toBeUndefined();
    expect(option("rework.resources.action.delete")).toBeTruthy();
    rerender({ readOnly: true });
    expect(menuButton()).toBeNull();
  });
  it.each(["filesLoading", "isLoading", "workspaceLoading"] as const)(
    "preserves %s and disables retry during loading",
    (loadingProp) => {
      renderDrawer({
        attachments: [],
        [loadingProp]: true,
        filesError: { status: 503 },
        attachmentsError: { status: 503 },
        workspaceError: { status: 503 },
        onRetryFiles: vi.fn(),
        onRetryAttachments: vi.fn(),
      });
      expect(container.querySelector('[role="status"]')?.textContent).toContain("chatbot.sessionAttachments.loading");
      expect(text()).not.toContain("chatbot.sessionAttachments.empty");
      expect(
        Array.from(container.querySelectorAll("button")).filter(
          (element) => element.textContent === "common.retry" && element.disabled,
        ),
      ).toHaveLength(1);
    },
  );
  it("exposes long names on a focusable label and supports keyboard menu actions", async () => {
    const name = `${"very-long-file-name-".repeat(20)}.md`;
    renderDrawer({ attachments: [{ ...attachment, name }] });
    const label = container.querySelector<HTMLElement>('span[tabindex="0"]')!;
    expect(label.textContent).toBe(name);
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
      label.focus();
    });
    expect(document.querySelector('[role="tooltip"]')?.textContent).toBe(name);
    await click(menuButton());
    const menu = document.querySelector('[role="listbox"]')!;
    await act(async () => {
      menu.dispatchEvent(new KeyboardEvent("keydown", { key: "Home", bubbles: true }));
      menu.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    });
    await act(async () => {
      menu.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    });
    expect(download).toHaveBeenCalledOnce();
    expect(props.onDelete).not.toHaveBeenCalled();
  });
  it("keeps human Wiki sharing available when agent execution is disabled", async () => {
    renderDrawer({ readOnly: true, attachments: [], files: [file] });
    await click(menuButton());
    expect(option("chatbot.sessionAttachments.share.action")).toBeTruthy();
    await click(option("chatbot.sessionAttachments.share.action")!);
    expect(container.querySelector("[data-share-document]")).not.toBeNull();
  });
  it("shows a single simple empty state", () => {
    renderDrawer({ attachments: [] });
    expect(text()).toContain("chatbot.sessionAttachments.empty");
    expect(container.querySelector("section")).toBeNull();
  });
  it("shows only created files and restores their preview and download from the catalogue", async () => {
    renderDrawer({ attachments: [], files: [file] });
    expect(container.querySelectorAll("section")).toHaveLength(1);
    expect(text()).toContain("chatbot.sessionAttachments.deliverables");
    expect(text()).not.toContain("chatbot.sessionAttachments.sources");
    expect(text()).not.toContain("internal/");
    expect(text()).not.toContain("readyHint");
    expect(text()).toContain("2 kB");
    await click(previewButton()!);
    expect(viewer.props?.target?.sourceUrl).toBe("/control-plane/v1/spaces/space/sessions/session/files/deck/preview");
    await downloadFile();
    expect(download).toHaveBeenCalledWith(
      "/control-plane/v1/spaces/space/sessions/session/files/deck/content",
      "Slides.pptx",
    );
  });
  it("shows both named sections with separate actions and no nested buttons", () => {
    renderDrawer({ files: [file] });
    expect(container.querySelectorAll("section")).toHaveLength(2);
    expect(container.querySelector("button button")).toBeNull();
  });
  it("keeps attachment previews in their owning conversation and downloads through that boundary", async () => {
    renderDrawer();
    await click(previewButton()!);
    expect(viewer.props?.target).toMatchObject({ documentUid: "att-1", sessionId: "session" });
    await downloadFile();
    expect(download).toHaveBeenCalledWith(
      "/control-plane/v1/spaces/space/sessions/session/attachments/att-1/content",
      "notes.md",
    );
  });
  it("confirms before deleting a deliverable and clears its selection", async () => {
    const remove = vi.fn().mockResolvedValue(undefined);
    renderDrawer({ attachments: [], files: [file], onDeleteFile: remove });
    await selectAction("rework.resources.action.delete");
    expect(remove).not.toHaveBeenCalled();
    expect(document.querySelector('[role="alertdialog"]')).toBeTruthy();
    await confirmDelete();
    expect(remove).toHaveBeenCalledWith("deck");
    expect(document.querySelector('[role="alertdialog"]')).toBeNull();
  });
  it("routes workspace deletion to its owner", async () => {
    const remove = vi.fn().mockResolvedValue(undefined);
    renderDrawer({
      attachments: [],
      workspaceFiles: [{ path: "docs/note.md", name: "note.md", size: 3, modified: null }],
      onDeleteWorkspaceFile: remove,
    });
    await deleteFile();
    expect(remove).toHaveBeenCalledWith("docs/note.md");
  });
  it("deletes independently of preview, and protects read-only and processing files", async () => {
    renderDrawer();
    await deleteFile();
    expect(props.onDelete).toHaveBeenCalledWith("att-1");
    expect(viewer.props).toBeNull();
    rerender({ readOnly: true });
    await click(menuButton());
    expect(option("rework.resources.action.delete")).toBeUndefined();
    await click(menuButton());
    expect(previewButton()).toBeTruthy();
    rerender({ readOnly: false, attachments: [{ ...attachment, status: "ingesting" }] });
    await click(menuButton());
    expect(option("rework.resources.action.delete")).toBeUndefined();
    await click(menuButton());
    expect(previewButton()).toBeNull();
    expect(text()).toContain("chatbot.attachmentChip.processing");
  });
  it.each(["filesError", "attachmentsError", "workspaceError"] as const)(
    "never presents %s as an empty conversation",
    async (errorProp) => {
      const retry = vi.fn();
      renderDrawer({
        attachments: [],
        [errorProp]: { status: 503, data: { detail: "secret traceback" } },
        onRetryFiles: retry,
        onRetryAttachments: retry,
      });
      expect(container.querySelector('[role="alert"]')).not.toBeNull();
      expect(text()).toContain("HTTP 503");
      expect(text()).not.toContain("secret");
      expect(text()).not.toContain("chatbot.sessionAttachments.empty");
      await click(button("common.retry"));
      expect(retry).toHaveBeenCalledOnce();
    },
  );
  it("keeps a failed download visible through a pending retry, clearing only after success", async () => {
    download.mockRejectedValueOnce(new Error("Download failed (403)"));
    renderDrawer({ files: [file], attachments: [] });
    await downloadFile();
    expect(text()).toContain("chatbot.sessionAttachments.downloadError (HTTP 403)");
    rerender({ open: false });
    rerender({ open: true });
    expect(text()).toContain("downloadError");
    let finish!: () => void;
    download.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve;
        }),
    );
    await downloadFile();
    expect(text()).toContain("downloadError");
    expect(menuButton().disabled).toBe(true);
    expect(menuButton().getAttribute("aria-busy")).toBe("true");
    await click(menuButton());
    expect(download).toHaveBeenCalledTimes(2);
    await act(async () => finish());
    expect(text()).not.toContain("downloadError");
    expect(menuButton().disabled).toBe(false);
  });
  it("retains preview failure after closing and reopening until the viewer succeeds", async () => {
    renderDrawer({ files: [file], attachments: [] });
    await click(previewButton()!);
    act(() => viewer.props?.onError?.(new Error("secret internal URL")));
    act(() => viewer.props?.onClose());
    expect(text()).toContain("chatbot.sessionAttachments.previewError");
    expect(text()).not.toContain("secret");
    await click(previewButton()!);
    expect(text()).toContain("previewError");
    act(() => viewer.props?.onLoaded?.());
    expect(text()).not.toContain("previewError");
  });
  it("keeps refused deletion visible while retaining the file", async () => {
    renderDrawer({ onDelete: vi.fn().mockResolvedValue(false) });
    await deleteFile();
    expect(text()).toContain("chatbot.sessionAttachments.deleteError");
    expect(text()).toContain("notes.md");
  });
  it("explains preparation failure and preserves the original download", async () => {
    renderDrawer({ attachments: [{ ...attachment, status: "error", error: "unsupported_input" }] });
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("preparationError");
    await downloadFile();
    expect(download).toHaveBeenCalledOnce();
    expect(previewButton()).toBeNull();
  });
});

describe("editable documents in conversation files", () => {
  const baseUrl = "http://pod.test/capabilities/writable_document";
  const doc = (overrides: Partial<WritableDocumentResponse> = {}): WritableDocumentResponse => ({
    session_id: "session",
    document_id: "d1",
    title: "Draft",
    content_md: "# Draft",
    updated_at: "2026-11-21T10:00:00Z",
    updated_by: "agent",
    ...overrides,
  });
  let requests: { request: Request; resolve: (response: Response) => void }[];
  const documentRows = () =>
    container.querySelectorAll('section[aria-label="capability.writable_document.files.title"] span[tabindex="0"]');
  const openDocument = () => container.querySelector('button[aria-label="capability.writable_document.card.open"]')!;
  async function mountDocuments(overrides: Partial<typeof props> = {}, routed = true) {
    requests = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (input: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((resolve) => {
            requests.push({ request: input instanceof Request ? input : new Request(input, init), resolve });
          }),
      ),
    );
    renderDrawer({ attachments: [], capabilityIds: ["writable_document"], ...overrides });
    if (routed)
      await act(async () => {
        store.dispatch(setCapabilityBaseUrls({ writable_document: baseUrl }));
      });
    await act(async () => {});
  }
  async function answer(index: number, body: unknown, status = 200) {
    await act(async () => {
      requests[index].resolve(
        new Response(status === 204 ? null : JSON.stringify(body), {
          status,
          headers: { "Content-Type": "application/json" },
        }),
      );
    });
    await act(async () => {});
  }
  function stream(document: WritableDocumentResponse) {
    act(() => {
      store.dispatch(
        upsertFromPart({
          sessionId: document.session_id,
          doc: {
            ...document,
            type: "writable_document",
            updated_at: document.updated_at!,
          },
        }),
      );
    });
  }

  it("reports files while closed and selects multiple documents for one publish action", async () => {
    const count = vi.fn();
    await mountDocuments({ open: false, onFileCount: count });
    await answer(0, [doc(), doc({ document_id: "d2", title: "Word.docx" })]);
    expect(count).toHaveBeenLastCalledWith("session", 2);
    rerender({ open: true });
    const boxes = container.querySelectorAll<HTMLInputElement>('section input[type="checkbox"]');
    await click(boxes[0]);
    const publish = [...container.querySelectorAll("button")].find((item) =>
      item.textContent?.includes("chatbot.sessionAttachments.share.action"),
    )!;
    await click(publish);
    expect(
      container.querySelector('[data-share-document="session/writable_document:d1,writable_document:d2"]'),
    ).not.toBeNull();
    rerender({ sessionId: "other" });
    expect(container.querySelector("[data-share-document]")).toBeNull();
    expect(count).toHaveBeenLastCalledWith("other", 0);
  });

  it("confirms existence in the catalogue and preserves a newer streamed title", async () => {
    await mountDocuments();
    expect(text()).toContain("chatbot.sessionAttachments.loading");
    expect(text()).not.toContain("chatbot.sessionAttachments.empty");
    expect(text()).not.toContain("capability.writable_document.empty");
    stream(doc({ title: "Updated title", updated_at: "2026-11-21T11:00:00Z" }));
    expect(documentRows()).toHaveLength(0);
    await answer(0, [doc()]);
    expect(documentRows()).toHaveLength(1);
    expect(documentRows()[0].textContent).toContain(writableFilename("Updated title"));
    expect(documentRows()[0].textContent).not.toContain("Draft");
    expect(requests.map(({ request }) => request.method)).toEqual(["GET"]);
    expect(store.getState().writableDocument.selectedId).toBeNull();
  });

  it("rehydrates a persisted document, opens its existing editor, and keeps the other file families", async () => {
    const title = "Very long document title ".repeat(20);
    await mountDocuments({
      attachments: [attachment],
      files: [file],
      workspaceFiles: [{ path: "notes.txt", name: "notes.txt", size: 12, modified: "2026-11-21T10:00:00Z" }],
    });
    await answer(0, [doc({ document_id: "persisted", title }), doc({ document_id: "second", title: "Second" })]);
    expect(container.querySelectorAll("section")).toHaveLength(4);
    expect(text()).toContain("notes.md");
    expect(text()).toContain("Slides.pptx");
    expect(text()).toContain("notes.txt");
    expect(documentRows()[0].textContent).toContain(writableFilename(title));
    expect(documentRows()[0].getAttribute("tabindex")).toBe("0");
    expect(documentRows()[0].textContent).toContain(".md");
    await click(openDocument());
    expect(store.getState().writableDocument.selectedId).toBe("persisted");
    expect(store.getState().capabilitySidePanelOpenRequest).toEqual({
      key: "writable_document:writable_document_pane",
      requestId: 1,
    });
    expect(requests).toHaveLength(1);
  });

  it("never displays the previous conversation, including its late list response", async () => {
    await mountDocuments();
    stream(doc({ title: "Previous conversation" }));
    expect(documentRows()).toHaveLength(0);
    rerender({ sessionId: "other" });
    expect(text()).not.toContain(writableFilename("Previous conversation"));
    await act(async () => {});
    await answer(0, [doc({ title: "Late previous title" })]);
    expect(documentRows()).toHaveLength(0);
    expect(text()).not.toContain(writableFilename("Late previous title"));
    await answer(1, [doc({ session_id: "other", document_id: "other-doc", title: "Current conversation" })]);
    expect(documentRows()).toHaveLength(1);
    expect(text()).toContain(writableFilename("Current conversation"));
    expect(text()).not.toContain(writableFilename("Previous conversation"));
  });

  it("shares one existing row through its menu and clears the dialog when the conversation changes", async () => {
    await mountDocuments();
    await answer(0, [doc({ title: "Recette simple de mayonnaise" })]);
    const menu = container.querySelector(
      'button[aria-label="rework.resources.action.more: Recette_simple_de_mayonnaise.md"]',
    )!;
    await click(menu);
    await click(option("chatbot.sessionAttachments.share.action")!);
    expect(container.querySelector('[data-share-document="session/writable_document:d1"]')).not.toBeNull();
    expect(documentRows()).toHaveLength(1);
    expect(requests).toHaveLength(1);
    await click(button("cancel-share"));
    expect(container.querySelector("[data-share-document]")).toBeNull();
    await click(menu);
    await click(option("chatbot.sessionAttachments.share.action")!);
    rerender({ sessionId: "other" });
    expect(container.querySelector("[data-share-document]")).toBeNull();
  });

  it("distinguishes list failure from empty content and retries without exposing server details", async () => {
    await mountDocuments();
    await answer(0, { detail: "secret server detail" }, 503);
    expect(text()).toContain("capability.writable_document.files.error");
    expect(text()).not.toContain("secret");
    expect(text()).not.toContain("chatbot.sessionAttachments.empty");
    expect(text()).not.toContain("capability.writable_document.empty");
    await click(button("common.retry"));
    await answer(1, []);
    expect(text()).toContain("capability.writable_document.empty");
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });

  it("respects capability availability independently of the import tool", async () => {
    await mountDocuments({}, false);
    stream(doc());
    expect(documentRows()).toHaveLength(0);
    expect(text()).toContain("capability.writable_document.files.unavailable");
    expect(requests).toHaveLength(0);
    rerender({ capabilityIds: ["open_writable_document"] });
    expect(text()).not.toContain("capability.writable_document.files.title");
    expect(requests).toHaveLength(0);
  });

  it("refreshes the shared list after a user edit without duplicating the live document", async () => {
    await mountDocuments();
    stream(doc());
    await answer(0, [doc()]);
    let save: Promise<unknown>;
    await act(async () => {
      save = store.dispatch(
        documentsApi.endpoints.updateWritableDocument.initiate({
          sessionId: "session",
          documentId: "d1",
          writableDocumentUpdate: { title: "User title", content_md: "User text" },
        }),
      );
    });
    const updated = doc({
      title: "User title",
      content_md: "User text",
      updated_by: "user",
      updated_at: "2026-11-21T12:00:00Z",
    });
    expect(requests[1].request.method).toBe("PUT");
    await answer(1, updated);
    await act(async () => {
      await save;
    });
    expect(requests[2].request.method).toBe("GET");
    await answer(2, [updated]);
    expect(documentRows()).toHaveLength(1);
    expect(documentRows()[0].textContent).toContain(writableFilename("User title"));
  });

  it("deletes a saved document and never restores it from replayed history", async () => {
    await mountDocuments();
    await answer(0, [doc()]);
    await deleteFile();
    expect(requests[1].request.method).toBe("DELETE");
    expect(requests[1].request.url).toBe(`${baseUrl}/sessions/session/documents/d1`);
    await answer(1, null, 204);
    expect(requests[2].request.method).toBe("GET");
    await answer(2, []);
    expect(documentRows()).toHaveLength(0);
    expect(document.querySelector('[role="alertdialog"]')).toBeNull();
    stream(doc());
    await act(async () => {});
    expect(documentRows()).toHaveLength(0);
    await answer(3, []);
    expect(documentRows()).toHaveLength(0);
  });

  it.each([
    ["Report.docx", "docx"],
    ["Report.md", "md"],
  ])("exports %s through the existing authenticated download", async (title, format) => {
    await mountDocuments();
    await answer(0, [doc({ title })]);
    const save = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const blobUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:document");
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    await click(container.querySelector('button[aria-label="capability.writable_document.download"]')!);
    expect(requests[1].request.url).toBe(`${baseUrl}/sessions/session/documents/d1/export?format=${format}`);
    expect(requests[1].request.headers.get("Authorization")).toBe("Bearer document-token");
    expect(requests[1].request.method).toBe("GET");
    await answer(1, "exported content");
    expect(blobUrl).toHaveBeenCalledOnce();
    expect(save).toHaveBeenCalledOnce();
    expect(revoke).toHaveBeenCalledWith("blob:document");
    expect(download).not.toHaveBeenCalled();
  });
});
