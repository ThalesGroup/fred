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

// Regression coverage: each attachment row used to be one <button> wrapping the
// delete IconButton - invalid HTML that React flags as a hydration error. The
// preview target and the delete control must stay siblings.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SessionAttachment } from "@rework/types/attachments";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// Only the attachment list is under test: the drawer chrome and the warning
// banner are reduced to their children, the preview modal to its open flag.
vi.mock("../InlineDrawer/InlineDrawer", () => ({
  InlineDrawer: ({ children }: { children: React.ReactNode }) => <aside>{children}</aside>,
}));
vi.mock("../MarkdownPreviewModal/MarkdownPreviewModal", () => ({
  MarkdownPreviewModal: ({ open }: { open: boolean }) => <div data-preview-open={open} />,
}));
vi.mock("@shared/molecules/UploadWarningBanner/UploadWarningBanner", () => ({
  default: () => null,
}));

import { SessionAttachmentsDrawer } from "./SessionAttachmentsDrawer";

const attachment: SessionAttachment = {
  attachmentId: "att-1",
  name: "diff_main_swift.md",
  mime: "text/markdown",
  sizeBytes: 1024,
  summaryMd: "# summary",
};

let container: HTMLDivElement;
let root: Root;

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

function renderDrawer(onDelete = vi.fn()) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<SessionAttachmentsDrawer open onClose={() => {}} attachments={[attachment]} onDelete={onDelete} />);
  });
  return onDelete;
}

function click(element: Element | null) {
  act(() => {
    element?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

function previewOpen(): string | null | undefined {
  return container.querySelector("[data-preview-open]")?.getAttribute("data-preview-open");
}

describe("SessionAttachmentsDrawer - attachment row markup", () => {
  it("never nests the delete button inside the preview button", () => {
    renderDrawer();

    expect(container.querySelectorAll("button")).toHaveLength(2);
    expect(container.querySelector("button button")).toBeNull();
  });

  it("opens the preview when the attachment itself is clicked", () => {
    renderDrawer();

    click(container.querySelector("button"));

    expect(previewOpen()).toBe("true");
  });

  it("deletes without opening the preview when the delete button is clicked", () => {
    const onDelete = renderDrawer();

    click(container.querySelector('button[aria-label="chatbot.sessionAttachments.deleteAria"]'));

    expect(onDelete).toHaveBeenCalledWith("att-1");
    expect(previewOpen()).toBe("false");
  });
});
