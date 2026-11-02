// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { ChatAttachment } from "@rework/types/attachments";

const known = "chatbot.attachmentChip.failedReason.name_conflict";
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { defaultValue?: string }) =>
      key.includes("failedReason") && key !== known ? options?.defaultValue : key,
  }),
}));

import { AttachmentChips } from "./AttachmentChips";

const failed = (error?: string): ChatAttachment => ({
  id: "a",
  name: "README.md",
  size: 1,
  mime: "text/markdown",
  status: "error",
  error,
});
const render = (attachment: ChatAttachment) =>
  renderToStaticMarkup(<AttachmentChips attachments={[attachment]} onRemove={() => {}} />);

describe("AttachmentChips failure label", () => {
  it("names a known reason", () => {
    expect(render(failed("name_conflict"))).toContain(known);
  });

  it.each(["storage_unavailable", undefined])("falls back to the generic label (%s)", (error) => {
    expect(render(failed(error))).toContain("chatbot.attachmentChip.failed<");
  });
});
