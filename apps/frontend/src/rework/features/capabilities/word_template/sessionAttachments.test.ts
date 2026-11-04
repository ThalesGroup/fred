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

// Attached Word files: each .docx attached in the chat is copied to the
// capability;
// other files are ignored; a failure never rejects.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: { GetToken: () => "tok", ensureFreshToken: () => Promise.resolve(true) },
}));

import { wordTemplateCapabilityApi } from "./api/wordTemplateCapabilityOpenApi";
import { wordTemplateCapability } from "./plugin";
import { captureWordAttachment } from "./sessionAttachments";
import { attachedBaseFilename, previewVersionKey } from "./sessionDocument";

const dispatch = vi.fn();
const context = { capabilityId: "word_template", baseUrl: "/cap", teamId: "t", sessionId: "s 1", dispatch };

describe("word_template chat attachments", () => {
  const fetchMock = vi.fn();
  const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);

  beforeEach(() => {
    fetchMock.mockReset();
    warn.mockClear();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("uploads an attached .docx with the bearer and a bounded wait", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ attachment_id: "doc1", filename: "Report.docx" }), { status: 201 }),
    );

    const result = await captureWordAttachment(new File(["x"], "Report.DOCX", { type: "" }), context);

    expect(result).toEqual({ attachment_id: "doc1", filename: "Report.docx" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/cap/sessions/s%201/attachments");
    expect(init.method).toBe("POST");
    expect(init.headers.Authorization).toBe("Bearer tok");
    expect(init.body).toBeInstanceOf(FormData);
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });

  it("recognises a Word file by its MIME type too", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ attachment_id: "doc2", filename: "f" }), { status: 201 }),
    );
    const type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

    await captureWordAttachment(new File(["x"], "no-extension", { type }), context);

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("ignores any other file", async () => {
    expect(await captureWordAttachment(new File(["x"], "notes.pdf", { type: "application/pdf" }), context)).toBeNull();
    expect(await captureWordAttachment(new File(["x"], "old.doc", { type: "application/msword" }), context)).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("logs a failed upload and never rejects (the chat send goes on)", async () => {
    fetchMock.mockResolvedValueOnce(new Response("{}", { status: 415 }));
    fetchMock.mockRejectedValueOnce(new DOMException("timed out", "TimeoutError"));

    const file = new File(["x"], "a.docx");
    await expect(captureWordAttachment(file, context)).resolves.toBeNull();
    await expect(wordTemplateCapability.onChatAttachment?.(file, context)).resolves.toBeUndefined();
    expect(warn).toHaveBeenCalledTimes(2);
  });

  it("forgets the kept file through the generated client when the user removes it", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ attachment_id: "doc1", filename: "a.docx" }), { status: 201 }),
    );
    const forget = await wordTemplateCapability.onChatAttachment?.(new File(["x"], "a.docx"), context);
    if (typeof forget !== "function") throw new Error("expected a forget callback");
    const initiate = vi.spyOn(wordTemplateCapabilityApi.endpoints.deleteWordTemplateAttachment, "initiate");

    dispatch.mockReturnValueOnce({ unwrap: () => Promise.resolve(null) });
    await forget();
    expect(initiate).toHaveBeenCalledWith({ sessionId: "s 1", attachmentId: "doc1" });
    expect(fetchMock).toHaveBeenCalledTimes(1); // the upload only: no hand-made DELETE

    // Still the document's base (409): kept, and not an error.
    dispatch.mockReturnValueOnce({ unwrap: () => Promise.reject({ status: 409 }) });
    await expect(forget()).resolves.toBeUndefined();
    expect(warn).not.toHaveBeenCalled();
  });
});

describe("word_template attached base in the pane", () => {
  it("keys the preview on the base and names an attached base", () => {
    const template = { session_id: "s", template_key: "k", base_kind: "template" as const, base_ref: "k" };
    const attached = {
      session_id: "s",
      base_kind: "attachment" as const,
      base_ref: "doc1",
      base_filename: "Weekly.docx",
      edit_count: 0,
    };
    expect(previewVersionKey(attached)).not.toBeNull();
    expect(previewVersionKey(attached)).not.toBe(previewVersionKey({ ...template, edit_count: 0 }));
    expect(attachedBaseFilename(attached)).toBe("Weekly.docx");
    expect(attachedBaseFilename(template)).toBeNull();
    expect(attachedBaseFilename(undefined)).toBeNull();
  });
});
