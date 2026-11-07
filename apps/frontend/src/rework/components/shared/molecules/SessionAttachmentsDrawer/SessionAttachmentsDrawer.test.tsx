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

import { SessionAttachmentsDrawer } from "./SessionAttachmentsDrawer";

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
  act(() => root.render(<SessionAttachmentsDrawer {...props} />));
}
function button(label: string) {
  return Array.from(container.querySelectorAll("button")).find((element) => element.textContent === label)!;
}
async function click(element: Element) {
  expect(element).toBeTruthy();
  await act(async () => element.dispatchEvent(new MouseEvent("click", { bubbles: true })));
}
const text = () => container.textContent ?? "";
const previewButton = () => button("chatbot.sessionAttachments.preview");
const downloadButton = () => button("chatbot.sessionAttachments.download");

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  download.mockReset();
  viewer.props = null;
});

describe("conversation files drawer", () => {
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
    await click(previewButton());
    expect(viewer.props?.target?.sourceUrl).toBe("/control-plane/v1/spaces/space/sessions/session/files/deck/preview");
    await click(downloadButton());
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
    await click(previewButton());
    expect(viewer.props?.target).toMatchObject({ documentUid: "att-1", sessionId: "session" });
    await click(downloadButton());
    expect(download).toHaveBeenCalledWith(
      "/control-plane/v1/spaces/space/sessions/session/attachments/att-1/content",
      "notes.md",
    );
  });
  it("deletes independently of preview, and protects read-only and processing files", async () => {
    renderDrawer();
    await click(container.querySelector('button[aria-label="chatbot.attachmentChip.removeAria"]')!);
    expect(props.onDelete).toHaveBeenCalledWith("att-1");
    expect(viewer.props).toBeNull();
    rerender({ readOnly: true });
    expect(container.querySelector('button[aria-label="chatbot.attachmentChip.removeAria"]')).toBeNull();
    expect(previewButton()).toBeTruthy();
    rerender({ readOnly: false, attachments: [{ ...attachment, status: "ingesting" }] });
    expect(container.querySelector('button[aria-label="chatbot.attachmentChip.removeAria"]')).toBeNull();
    expect(previewButton()).toBeUndefined();
    expect(text()).toContain("chatbot.attachmentChip.processing");
  });
  it.each(["filesError", "attachmentsError"] as const)(
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
    await click(downloadButton());
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
    await click(downloadButton());
    expect(text()).toContain("downloadError");
    expect(downloadButton().disabled).toBe(true);
    await act(async () => finish());
    expect(text()).not.toContain("downloadError");
  });
  it("retains preview failure after closing and reopening until the viewer succeeds", async () => {
    renderDrawer({ files: [file], attachments: [] });
    await click(previewButton());
    act(() => viewer.props?.onError?.(new Error("secret internal URL")));
    act(() => viewer.props?.onClose());
    expect(text()).toContain("chatbot.sessionAttachments.previewError");
    expect(text()).not.toContain("secret");
    await click(previewButton());
    expect(text()).toContain("previewError");
    act(() => viewer.props?.onLoaded?.());
    expect(text()).not.toContain("previewError");
  });
  it("keeps refused deletion visible while retaining the file", async () => {
    renderDrawer({ onDelete: vi.fn().mockResolvedValue(false) });
    await click(container.querySelector('button[aria-label="chatbot.attachmentChip.removeAria"]')!);
    expect(text()).toContain("chatbot.sessionAttachments.deleteError");
    expect(text()).toContain("notes.md");
  });
  it("explains preparation failure beyond the badge and preserves the original download", () => {
    renderDrawer({ attachments: [{ ...attachment, status: "error", error: "unsupported_input" }] });
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("preparationError");
    expect(downloadButton()).toBeTruthy();
    expect(previewButton()).toBeUndefined();
  });
});
