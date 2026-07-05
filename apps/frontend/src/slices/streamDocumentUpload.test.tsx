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

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("../security/KeycloakService", () => ({
  KeyCloakService: { GetToken: () => "test-token" },
}));

import { streamUploadOrProcessDocument, type ScheduledTask } from "./streamDocumentUpload";

/** Build a Response whose body streams the given lines as NDJSON. */
function ndjsonResponse(lines: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      const enc = new TextEncoder();
      for (const line of lines) controller.enqueue(enc.encode(line + "\n"));
      controller.close();
    },
  });
  return new Response(body, { status: 200 });
}

function stubFetch(lines: string[]): void {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ndjsonResponse(lines)));
}

describe("streamUploadOrProcessDocument", () => {
  beforeEach(() => vi.restoreAllMocks());
  afterEach(() => vi.unstubAllGlobals());

  it("reports a task once despite its id repeating across progress lines", async () => {
    // The real backend emits the same task_id on preparation, queued and processing
    // lines (and one finished line with no id). The correlation must stay stable and
    // deduped: one task, its documentUid from the first sighting.
    stubFetch([
      JSON.stringify({ step: "prep", status: "success", filename: "a.pdf", document_uid: "doc-1", task_id: "t-1" }),
      JSON.stringify({ step: "queued", status: "success", filename: "a.pdf", document_uid: "doc-1", task_id: "t-1" }),
      JSON.stringify({ step: "finished", status: "success", filename: "a.pdf" }),
      JSON.stringify({
        step: "processing",
        status: "in_progress",
        filename: "a.pdf",
        document_uid: "doc-1",
        task_id: "t-1",
      }),
    ]);

    const discovered: string[] = [];
    const tasks = await streamUploadOrProcessDocument(new File(["x"], "a.pdf"), "process", { tags: ["lib"] }, (t) =>
      discovered.push(t.taskId),
    );

    expect(tasks).toEqual([{ taskId: "t-1", documentUid: "doc-1" }]);
    expect(discovered).toEqual(["t-1"]); // callback fired once, on first sighting
  });

  it("discovers multiple distinct tasks in stream order, deduped", async () => {
    stubFetch([
      JSON.stringify({ task_id: "t-1", document_uid: "doc-1" }),
      JSON.stringify({ task_id: "t-2", document_uid: "doc-2" }),
      JSON.stringify({ task_id: "t-1", document_uid: "doc-1" }), // repeat, ignored
    ]);

    const discovered: ScheduledTask[] = [];
    const tasks = await streamUploadOrProcessDocument(new File(["x"], "a"), "process", {}, (t) => discovered.push(t));

    expect(tasks.map((t) => t.taskId)).toEqual(["t-1", "t-2"]);
    expect(discovered.map((t) => t.taskId)).toEqual(["t-1", "t-2"]);
    expect(discovered[0].documentUid).toBe("doc-1");
  });

  it("returns [] and never calls back when no line carries a task_id", async () => {
    stubFetch([JSON.stringify({ step: "prep", status: "success", filename: "a" })]);
    const discovered: ScheduledTask[] = [];
    const tasks = await streamUploadOrProcessDocument(new File(["x"], "a"), "upload", {}, (t) => discovered.push(t));
    expect(tasks).toEqual([]);
    expect(discovered).toEqual([]);
  });
});
