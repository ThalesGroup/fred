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
    const tasks = await streamUploadOrProcessDocument([new File(["x"], "a.pdf")], "process", { tags: ["lib"] }, (t) =>
      discovered.push(t.taskId),
    );

    expect(tasks).toEqual([{ taskId: "t-1", documentUid: "doc-1", filename: "a.pdf" }]);
    expect(discovered).toEqual(["t-1"]); // callback fired once, on first sighting
  });

  it("discovers multiple distinct tasks in stream order, deduped", async () => {
    stubFetch([
      JSON.stringify({ task_id: "t-1", document_uid: "doc-1", filename: "a.pdf" }),
      JSON.stringify({ task_id: "t-2", document_uid: "doc-2", filename: "b.pdf" }),
      JSON.stringify({ task_id: "t-1", document_uid: "doc-1", filename: "a.pdf" }), // repeat, ignored
    ]);

    const discovered: ScheduledTask[] = [];
    const tasks = await streamUploadOrProcessDocument(
      [new File(["x"], "a.pdf"), new File(["x"], "b.pdf")],
      "process",
      {},
      (t) => discovered.push(t),
    );

    expect(tasks.map((t) => t.taskId)).toEqual(["t-1", "t-2"]);
    expect(discovered.map((t) => t.taskId)).toEqual(["t-1", "t-2"]);
    expect(discovered[0].documentUid).toBe("doc-1");
    expect(discovered.map((t) => t.filename)).toEqual(["a.pdf", "b.pdf"]);
  });

  it("returns [] and never calls back when no line carries a task_id", async () => {
    stubFetch([JSON.stringify({ step: "prep", status: "success", filename: "a" })]);
    const discovered: ScheduledTask[] = [];
    const tasks = await streamUploadOrProcessDocument([new File(["x"], "a")], "upload", {}, (t) => discovered.push(t));
    expect(tasks).toEqual([]);
    expect(discovered).toEqual([]);
  });

  it("calls onFileResolved for a plain success/finished line with no task_id, once per filename", async () => {
    stubFetch([
      JSON.stringify({ step: "upload preparation", status: "success", filename: "a.pdf" }),
      JSON.stringify({ step: "processing", status: "success", filename: "a.pdf" }),
      JSON.stringify({ step: "finished", status: "finished", filename: "a.pdf" }),
      JSON.stringify({ step: "upload preparation", status: "success", filename: "b.pdf" }),
    ]);

    const resolved: string[] = [];
    await streamUploadOrProcessDocument(
      [new File(["x"], "a.pdf"), new File(["x"], "b.pdf")],
      "upload",
      {},
      undefined,
      undefined,
      (filename) => resolved.push(filename),
    );

    // Fires on every such line, not deduped by filename — the caller (scheduleFiles)
    // only needs the first one per file to mark it done; repeats are harmless no-ops.
    expect(resolved).toEqual(["a.pdf", "a.pdf", "a.pdf", "b.pdf"]);
  });

  it("does not call onFileResolved for a filename that already has a task_id", async () => {
    stubFetch([JSON.stringify({ task_id: "t-1", document_uid: "doc-1", filename: "a.pdf" })]);

    const resolved: string[] = [];
    await streamUploadOrProcessDocument([new File(["x"], "a.pdf")], "process", {}, undefined, undefined, (filename) =>
      resolved.push(filename),
    );

    expect(resolved).toEqual([]);
  });

  it("rejects with the backend's error when the file fails before any task_id exists", async () => {
    // Real case: an unsupported extension (e.g. .json) raises during "upload
    // preparation" — the backend reports a "failed" progress line with no
    // task_id at all, since no task is ever created for it.
    stubFetch([
      JSON.stringify({
        step: "upload preparation",
        status: "failed",
        filename: "data.json",
        error: "No input processor configured for extension '.json' in pipeline 'profile-fast'",
      }),
    ]);

    await expect(streamUploadOrProcessDocument([new File(["x"], "data.json")], "process", {})).rejects.toThrow(
      "No input processor configured for extension '.json' in pipeline 'profile-fast'",
    );
  });

  it("attributes a failure to the file named on its own progress line, in upload-only mode where neither file ever gets a task_id", async () => {
    // Upload-only mode never emits a task_id at all — a.pdf's plain "success"
    // line (no task_id) must still count as resolved, so b.json's failure is
    // reported per file via onFileFailed rather than rejecting the whole batch.
    stubFetch([
      JSON.stringify({ step: "upload preparation", status: "success", filename: "a.pdf" }),
      JSON.stringify({
        step: "upload preparation",
        status: "failed",
        filename: "b.json",
        error: "No input processor configured for extension '.json' in pipeline 'profile-fast'",
      }),
    ]);

    const failed: { filename: string; message: string }[] = [];
    const tasks = await streamUploadOrProcessDocument(
      [new File(["x"], "a.pdf"), new File(["x"], "b.json")],
      "upload",
      {},
      undefined,
      (filename, message) => failed.push({ filename, message }),
    );

    expect(tasks).toEqual([]);
    expect(failed).toEqual([
      { filename: "b.json", message: "No input processor configured for extension '.json' in pipeline 'profile-fast'" },
    ]);
  });

  it("reports a failure that arrives after an earlier success line for the same filename (no task_id either time)", async () => {
    // e.g. per-file task creation silently fails (still emits a plain success
    // line) and the batch's later scheduler submission then fails too, with a
    // second, terminal "failed" line for the same file. The later status must
    // win — an early success line must not permanently suppress it.
    stubFetch([
      JSON.stringify({ step: "upload preparation", status: "success", filename: "a.pdf" }),
      JSON.stringify({ step: "queued for processing", status: "failed", filename: "a.pdf", error: "scheduler down" }),
    ]);

    const failed: { filename: string; message: string }[] = [];
    await expect(
      streamUploadOrProcessDocument([new File(["x"], "a.pdf")], "process", {}, undefined, (filename, message) =>
        failed.push({ filename, message }),
      ),
    ).rejects.toThrow("scheduler down");

    expect(failed).toEqual([{ filename: "a.pdf", message: "scheduler down" }]);
  });

  it("ignores the batch-level 'done' summary line for per-file attribution (it carries no filename)", async () => {
    // The stream's final line is `{step: "done", status, error}` with no
    // filename — it must not be misattributed to files[0] when the batch has
    // a mix of outcomes, or a genuinely successful first file would get
    // flipped to "failed" by this filename-less status: "failed" summary.
    stubFetch([
      JSON.stringify({ step: "upload preparation", status: "success", filename: "a.pdf" }),
      JSON.stringify({ step: "upload preparation", status: "failed", filename: "b.json", error: "bad extension" }),
      JSON.stringify({ step: "done", status: "failed" }),
    ]);

    const failed: { filename: string; message: string }[] = [];
    const tasks = await streamUploadOrProcessDocument(
      [new File(["x"], "a.pdf"), new File(["x"], "b.json")],
      "upload",
      {},
      undefined,
      (filename, message) => failed.push({ filename, message }),
    );

    expect(tasks).toEqual([]);
    expect(failed).toEqual([{ filename: "b.json", message: "bad extension" }]);
  });

  it("rejects with the first failure but still reports every failed file when none of them resolves", async () => {
    // Both files fail before either resolves — the promise must still reject
    // (nothing in the batch succeeded), but b.json's failure must not vanish
    // behind a.json's just because only one message can be thrown.
    stubFetch([
      JSON.stringify({
        step: "upload preparation",
        status: "failed",
        filename: "a.json",
        error: "unsupported extension a",
      }),
      JSON.stringify({
        step: "upload preparation",
        status: "failed",
        filename: "b.json",
        error: "unsupported extension b",
      }),
    ]);

    const failed: { filename: string; message: string }[] = [];
    await expect(
      streamUploadOrProcessDocument(
        [new File(["x"], "a.json"), new File(["x"], "b.json")],
        "upload",
        {},
        undefined,
        (filename, message) => failed.push({ filename, message }),
      ),
    ).rejects.toThrow("unsupported extension a");

    expect(failed).toEqual([
      { filename: "a.json", message: "unsupported extension a" },
      { filename: "b.json", message: "unsupported extension b" },
    ]);
  });

  it("reports a per-file failure via onFileFailed instead of swallowing it when another file in the batch succeeds", async () => {
    // b.json fails before it ever gets a task_id, but a.pdf succeeds — the
    // promise must not throw (the batch as a whole produced a task), and the
    // caller must still learn about b.json's failure instead of it vanishing.
    stubFetch([
      JSON.stringify({ step: "prep", status: "success", filename: "a.pdf", document_uid: "doc-1", task_id: "t-1" }),
      JSON.stringify({
        step: "upload preparation",
        status: "failed",
        filename: "b.json",
        error: "No input processor configured for extension '.json' in pipeline 'profile-fast'",
      }),
    ]);

    const failed: { filename: string; message: string }[] = [];
    const tasks = await streamUploadOrProcessDocument(
      [new File(["x"], "a.pdf"), new File(["x"], "b.json")],
      "process",
      {},
      undefined,
      (filename, message) => failed.push({ filename, message }),
    );

    expect(tasks).toEqual([{ taskId: "t-1", documentUid: "doc-1", filename: "a.pdf" }]);
    expect(failed).toEqual([
      { filename: "b.json", message: "No input processor configured for extension '.json' in pipeline 'profile-fast'" },
    ]);
  });

  it("does not reject on a later failure once a task_id was already discovered", async () => {
    // The tray/Activity SSE feed for that task_id is the source of truth once
    // a task exists — re-throwing here would double-report the same failure.
    stubFetch([
      JSON.stringify({ step: "prep", status: "success", filename: "a.pdf", document_uid: "doc-1", task_id: "t-1" }),
      JSON.stringify({
        step: "queued",
        status: "failed",
        filename: "a.pdf",
        error: "scheduling error",
        task_id: "t-1",
      }),
    ]);

    const onFileFailed = vi.fn();
    const tasks = await streamUploadOrProcessDocument(
      [new File(["x"], "a.pdf")],
      "process",
      {},
      undefined,
      onFileFailed,
    );
    expect(tasks).toEqual([{ taskId: "t-1", documentUid: "doc-1", filename: "a.pdf" }]);
    expect(onFileFailed).not.toHaveBeenCalled();
  });
});

describe("multipart filename pinning", () => {
  beforeEach(() => vi.restoreAllMocks());
  afterEach(() => vi.unstubAllGlobals());

  it("uploads a folder-originated file under its leaf name, never its relative path", async () => {
    // Browsers put the RELATIVE path (webkitRelativePath) in the multipart
    // filename for files picked out of a folder — the backend then 404s writing
    // temp storage under the missing subdirectories. The part filename must be
    // pinned to the leaf name.
    stubFetch([]);
    await streamUploadOrProcessDocument([new File(["x"], "data/sub/a.csv")], "process", {});

    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    const body = fetchMock.mock.calls[0][1].body as FormData;
    const part = body.get("files") as File;
    expect(part.name).toBe("a.csv");
  });
});
