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

import { describe, expect, it } from "vitest";
import type { SessionAttachment } from "@rework/types/attachments";
import type { ChatMessage } from "../../../../slices/runtime/runtimeOpenApi";
import { buildAttachmentsMarkdown, excludeDeletedAttachments, splitSessionAttachments } from "./useChatAttachments";

describe("buildAttachmentsMarkdown", () => {
  it("announces persisted attachments to the runtime", () => {
    const attachment = {
      attachmentId: "attachment-1",
      name: "report.pdf",
    } as SessionAttachment;

    expect(buildAttachmentsMarkdown([attachment], [])).toContain("- report.pdf: conversation document");
  });

  it("carries the internal document uid so document tools can resolve the file", () => {
    const attachment = {
      attachmentId: "attachment-1",
      name: "report.pdf",
      documentUid: "554ab873903c40fdad52f36e2cffb501",
    } as SessionAttachment;

    expect(buildAttachmentsMarkdown([attachment], [])).toContain(
      "- report.pdf [554ab873903c40fdad52f36e2cffb501]: conversation document",
    );
  });

  it("returns null once the last attachment has been deleted", () => {
    const attachment = {
      attachmentId: "attachment-1",
      name: "report.pdf",
    } as SessionAttachment;
    const remaining = excludeDeletedAttachments([attachment], new Set(["attachment-1"]));

    expect(buildAttachmentsMarkdown(remaining, [])).toBeNull();
  });
});

describe("splitSessionAttachments", () => {
  const row = (attachmentId: string, createdAt: string): SessionAttachment => ({
    attachmentId,
    name: `${attachmentId}.pdf`,
    summaryMd: "",
    createdAt,
  });
  const userMessage = (timestamp: string, attachmentIds?: string[]): ChatMessage =>
    ({
      session_id: "s-1",
      exchange_id: timestamp,
      rank: 0,
      timestamp,
      role: "user",
      channel: "final",
      parts: [],
      metadata: attachmentIds
        ? { extras: { attachments: attachmentIds.map((id) => ({ attachment_id: id, name: `${id}.pdf` })) } }
        : {},
    }) as ChatMessage;
  const ids = (rows: SessionAttachment[]) => rows.map((attachment) => attachment.attachmentId);

  it("treats every row of a conversation without messages as a draft", () => {
    const { sent, drafts } = splitSessionAttachments([row("a", "2026-11-08T10:00:00Z")], []);
    expect(ids(sent)).toEqual([]);
    expect(ids(drafts)).toEqual(["a"]);
  });

  it("counts a row as sent once a user message lists it", () => {
    const { sent, drafts } = splitSessionAttachments(
      [row("a", "2026-11-08T10:00:00Z"), row("b", "2026-11-08T10:00:01Z")],
      [userMessage("2026-11-08T09:00:00Z", ["a"])],
    );
    expect(ids(sent)).toEqual(["a"]);
    expect(ids(drafts)).toEqual(["b"]);
  });

  it("ignores HITL answers, steered text and the optimistic row for the legacy cutoff", () => {
    const hitlAnswer = { ...userMessage("2026-11-08T12:00:00Z"), channel: "hitl_response" } as ChatMessage;
    const steered = { ...userMessage("2026-11-08T12:00:00Z"), metadata: { extras: { steered_message_id: "m" } } };
    const optimistic = { ...userMessage("2026-11-08T12:00:00Z"), metadata: { extras: { optimistic_user: true } } };
    const { drafts } = splitSessionAttachments(
      [row("dropped", "2026-11-08T11:00:00Z")],
      [userMessage("2026-11-08T10:00:00Z"), hitlAnswer, steered as ChatMessage, optimistic as ChatMessage],
    );
    expect(ids(drafts)).toEqual(["dropped"]);
  });

  it("counts rows older than the latest user message as sent, for messages stored without the list", () => {
    const { sent, drafts } = splitSessionAttachments(
      [row("old", "2026-11-08T09:00:00Z"), row("new", "2026-11-08T11:00:00Z")],
      [userMessage("2026-11-08T10:00:00Z")],
    );
    expect(ids(sent)).toEqual(["old"]);
    expect(ids(drafts)).toEqual(["new"]);
  });

  it("keeps drafts older than a new message with an explicit empty file list", () => {
    const { sent, drafts } = splitSessionAttachments(
      [row("draft", "2026-11-08T11:00:00Z")],
      [userMessage("2026-11-08T10:00:00Z"), userMessage("2026-11-08T12:00:00Z", [])],
    );
    expect(ids(sent)).toEqual([]);
    expect(ids(drafts)).toEqual(["draft"]);
  });
});
