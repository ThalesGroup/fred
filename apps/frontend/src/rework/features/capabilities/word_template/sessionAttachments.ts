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

// Word files attached in the chat, kept by word_template: the platform
// keeps no attachment bytes, so each .docx attached in a
// chat where the capability is active is copied to
// `POST /sessions/{id}/attachments`. The agent may later make it the
// document's base. Raw `fetch` is the sanctioned exception - a multipart
// upload the generated client can't express; the response TYPE still comes
// from the generated client.

import { KeyCloakService } from "../../../../security/KeycloakService";
import type { ChatAttachmentContext } from "../types";
import { wordTemplateCapabilityApi, type WordTemplateAttachmentResponse } from "./api/wordTemplateCapabilityOpenApi";

const WORD_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
// The attachment waits for this upload before turning "ready" (so the agent
// sees the file on the very next message): it must never hang forever.
export const ATTACHMENT_UPLOAD_TIMEOUT_MS = 30_000;

export const isWordFile = (file: File) => file.type === WORD_TYPE || file.name.toLowerCase().endsWith(".docx");

/**
 * `onChatAttachment` handler: uploads an attached .docx (by MIME type or
 * extension), ignores any other file. Never rejects - a failed or timed-out
 * upload is logged and the chat attachment goes on as usual.
 */
export async function captureWordAttachment(
  file: File,
  { baseUrl, sessionId }: ChatAttachmentContext,
): Promise<WordTemplateAttachmentResponse | null> {
  if (!isWordFile(file)) return null;
  try {
    const form = new FormData();
    form.append("file", file, file.name);
    const res = await fetch(`${baseUrl}/sessions/${encodeURIComponent(sessionId)}/attachments`, {
      method: "POST",
      headers: await freshAuthHeader(),
      body: form,
      signal: AbortSignal.timeout(ATTACHMENT_UPLOAD_TIMEOUT_MS),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as WordTemplateAttachmentResponse;
  } catch (error) {
    console.warn(`[word_template] could not keep the attached file ${file.name}`, error);
    return null;
  }
}

/** The bearer header, refreshed first: a chat can sit idle past the token's life. */
export async function freshAuthHeader(): Promise<{ Authorization: string }> {
  await KeyCloakService.ensureFreshToken(30);
  return { Authorization: `Bearer ${KeyCloakService.GetToken() ?? ""}` };
}

/**
 * Forgets a kept .docx when the user removes it from the chat. The server
 * keeps it (409) while it is the document's base; never rejects.
 */
export async function forgetWordAttachment(
  { dispatch, sessionId }: ChatAttachmentContext,
  attachmentId: string,
): Promise<void> {
  try {
    await dispatch(
      wordTemplateCapabilityApi.endpoints.deleteWordTemplateAttachment.initiate({ sessionId, attachmentId }),
    ).unwrap();
  } catch (error) {
    if (isGone(error)) return;
    console.warn(`[word_template] could not forget the attached file ${attachmentId}`, error);
  }
}

/** 404 (already gone) or 409 (kept: the document uses it): nothing to forget. */
export function isGone(error: unknown): boolean {
  const status = (error as { status?: unknown } | null)?.status;
  return status === 404 || status === 409;
}
