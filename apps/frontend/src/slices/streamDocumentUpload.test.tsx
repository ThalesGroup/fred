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
import { configureStore } from "@reduxjs/toolkit";

vi.mock("../security/KeycloakService", () => ({
  KeyCloakService: { GetToken: vi.fn(), ensureFreshToken: vi.fn() },
}));
vi.mock("../rework/features/imports/unfinishedImports", () => ({
  noteImportStarted: vi.fn(),
  noteImportSettled: vi.fn(),
  noteImportFailed: vi.fn(),
}));

import { KeyCloakService } from "../security/KeycloakService";
import { streamUploadOrProcessDocument, type ScheduledTask } from "./streamDocumentUpload";
import { cancelImport, canCancelImport, clearHeldImports, runImport } from "../rework/features/imports/importRun";
import { taskSlice } from "../rework/features/tasks/taskSlice";

beforeEach(() => {
  clearHeldImports();
  vi.restoreAllMocks();
  vi.mocked(KeyCloakService.GetToken).mockReset().mockReturnValue("test-token");
  vi.mocked(KeyCloakService.ensureFreshToken).mockReset().mockResolvedValue(true);
});
afterEach(() => vi.unstubAllGlobals());

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

  it("calls onFileResolved only on the terminal 'finished' line, not an earlier 'success' one", async () => {
    // The no-scheduler process path (and upload-only mode) emits an
    // intermediate "success" line for the upload-prep step before the file is
    // actually processed — onFileResolved must not fire until "finished",
    // or the caller (scheduleFiles) could consider the batch done while a
    // file is still mid-processing (a real bug an external review caught).
    stubFetch([
      JSON.stringify({ step: "upload preparation", status: "success", filename: "a.pdf" }),
      JSON.stringify({ step: "processing", status: "success", filename: "a.pdf" }),
      JSON.stringify({ step: "finished", status: "finished", filename: "a.pdf" }),
      JSON.stringify({ step: "upload preparation", status: "success", filename: "b.pdf" }),
      JSON.stringify({ step: "finished", status: "finished", filename: "b.pdf" }),
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

    expect(resolved).toEqual(["a.pdf", "b.pdf"]);
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
    const resolved: string[] = [];
    await expect(
      streamUploadOrProcessDocument(
        [new File(["x"], "a.pdf")],
        "process",
        {},
        undefined,
        (filename, message) => failed.push({ filename, message }),
        (filename) => resolved.push(filename),
      ),
    ).rejects.toThrow("scheduler down");

    expect(failed).toEqual([{ filename: "a.pdf", message: "scheduler down" }]);
    expect(resolved).toEqual([]); // never reached "finished" — must not be reported resolved
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
    // The task SSE feed is the source of truth once a task exists;
    // re-throwing here would double-report the same failure.
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

describe("the server's own explanation", () => {
  it("keeps the reason a refused upload came with", async () => {
    // Quota and permission checks run before the stream opens and answer with
    // an ordinary error. Throwing away the body left the user reading a status
    // code for the most common reason an import is refused.
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: "Storage quota exceeded for team fredlab: limit is 10 GB." }), {
          status: 400,
          statusText: "Bad Request",
        }),
    ) as unknown as typeof fetch;

    await expect(streamUploadOrProcessDocument([new File(["x"], "a.pdf")], "process")).rejects.toThrow(
      /Storage quota exceeded/,
    );
  });
});

describe("upload authentication recovery", () => {
  it.each(["upload", "process"] as const)("waits for renewal before reading the %s request's token", async (mode) => {
    const fetch = vi.fn().mockResolvedValue(ndjsonResponse([]));
    vi.stubGlobal("fetch", fetch);
    let finishRefresh!: (fresh: boolean) => void;
    vi.mocked(KeyCloakService.ensureFreshToken).mockReturnValueOnce(
      new Promise<boolean>((resolve) => {
        finishRefresh = resolve;
      }),
    );

    const upload = streamUploadOrProcessDocument([new File(["x"], "a.pdf")], mode);
    expect(fetch).not.toHaveBeenCalled();
    expect(KeyCloakService.GetToken).not.toHaveBeenCalled();
    vi.mocked(KeyCloakService.GetToken).mockReturnValue("renewed-token");
    finishRefresh(true);
    await upload;

    expect(KeyCloakService.ensureFreshToken).toHaveBeenCalledExactlyOnceWith(30);
    expect(fetch).toHaveBeenCalledExactlyOnceWith(
      mode === "upload" ? "/knowledge-flow/v1/upload-documents" : "/knowledge-flow/v1/upload-process-documents",
      expect.objectContaining({ headers: { Authorization: "Bearer renewed-token" } }),
    );
  });

  it.each(["upload", "process"] as const)(
    "renews a rejected %s request once without changing its payload",
    async (mode) => {
      const fetch = vi
        .fn()
        .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Token expired" }), { status: 401 }))
        .mockResolvedValueOnce(
          ndjsonResponse([
            JSON.stringify({ filename: "a.pdf", task_id: "task-a", document_uid: "doc-a" }),
            JSON.stringify({ filename: "a.pdf", task_id: "task-a", document_uid: "doc-a" }),
            JSON.stringify({ filename: "b.pdf", step: "finished", status: "finished" }),
          ]),
        );
      vi.stubGlobal("fetch", fetch);
      vi.mocked(KeyCloakService.ensureFreshToken).mockImplementation(async (validity) => {
        vi.mocked(KeyCloakService.GetToken).mockReturnValue(validity === 0 ? "retry-token" : "first-token");
        return true;
      });
      const discovered = vi.fn();
      const resolved = vi.fn();
      const failed = vi.fn();
      const beforeSend = vi.fn((files: File[]) => files);
      const metadata = { tags: ["folder"], profile: "fast", conflict_decisions: { "a.pdf": "overwrite" } };

      const tasks = await streamUploadOrProcessDocument(
        [new File(["first"], "sub/a.pdf"), new File(["second"], "b.pdf")],
        mode,
        metadata,
        discovered,
        failed,
        resolved,
        undefined,
        beforeSend,
      );

      expect(fetch).toHaveBeenCalledTimes(2);
      expect(vi.mocked(KeyCloakService.ensureFreshToken).mock.calls).toEqual([[30], [0]]);
      const [first, retry] = fetch.mock.calls.map(([url, init]) => ({ url, ...init }));
      expect(first.url).toBe(retry.url);
      expect(first.headers.Authorization).toBe("Bearer first-token");
      expect(retry.headers.Authorization).toBe("Bearer retry-token");
      expect(first.method).toBe("POST");
      expect(retry.method).toBe("POST");
      expect(retry.body).toBe(first.body);
      const parts = (retry.body as FormData).getAll("files") as File[];
      expect(parts.map((part) => part.name)).toEqual(["a.pdf", "b.pdf"]);
      expect(await Promise.all(parts.map((part) => part.text()))).toEqual(["first", "second"]);
      expect(retry.body.get("metadata_json")).toBe(JSON.stringify(metadata));
      expect(tasks).toEqual([{ taskId: "task-a", documentUid: "doc-a", filename: "a.pdf" }]);
      expect(discovered).toHaveBeenCalledExactlyOnceWith(tasks[0]);
      expect(resolved).toHaveBeenCalledExactlyOnceWith("b.pdf");
      expect(failed).not.toHaveBeenCalled();
      expect(beforeSend).toHaveBeenCalledTimes(1);
    },
  );

  it("stops after the retry is still unauthorized and preserves its explanation", async () => {
    const fetch = vi
      .fn()
      .mockImplementation(async () => new Response(JSON.stringify({ detail: "Invalid audience" }), { status: 401 }));
    vi.stubGlobal("fetch", fetch);

    await expect(streamUploadOrProcessDocument([new File(["x"], "a.pdf")], "process")).rejects.toThrow(
      "Upload failed: 401 . Invalid audience",
    );

    expect(fetch).toHaveBeenCalledTimes(2);
    expect(vi.mocked(KeyCloakService.ensureFreshToken).mock.calls).toEqual([[30], [0]]);
  });

  it("does not resend when forced renewal fails", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail: "Session expired" }), { status: 401 }));
    vi.stubGlobal("fetch", fetch);
    vi.mocked(KeyCloakService.ensureFreshToken).mockResolvedValueOnce(true).mockResolvedValueOnce(false);

    await expect(streamUploadOrProcessDocument([new File(["x"], "a.pdf")], "process")).rejects.toThrow(
      "Session expired",
    );

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(vi.mocked(KeyCloakService.ensureFreshToken).mock.calls).toEqual([[30], [0]]);
  });

  it.each([400, 403, 429, 503])("does not renew or replay an HTTP %i refusal", async (status) => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Upload refused" }), { status }));
    vi.stubGlobal("fetch", fetch);

    await expect(streamUploadOrProcessDocument([new File(["x"], "a.pdf")], "process")).rejects.toThrow(
      "Upload refused",
    );

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(KeyCloakService.ensureFreshToken).toHaveBeenCalledExactlyOnceWith(30);
  });

  it("does not replay a request when the network fails", async () => {
    const fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetch);

    await expect(streamUploadOrProcessDocument([new File(["x"], "a.pdf")], "process")).rejects.toThrow(
      "Failed to fetch",
    );

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(KeyCloakService.ensureFreshToken).toHaveBeenCalledExactlyOnceWith(30);
  });

  it("does not replay an accepted import whose stream later breaks", async () => {
    const discovered = vi.fn();
    let reads = 0;
    const body = new ReadableStream<Uint8Array>({
      pull(controller) {
        if (reads++ === 0) {
          controller.enqueue(new TextEncoder().encode(JSON.stringify({ filename: "a.pdf", task_id: "task-a" }) + "\n"));
        } else {
          controller.error(new Error("Stream interrupted"));
        }
      },
    });
    const fetch = vi.fn().mockResolvedValue(new Response(body));
    vi.stubGlobal("fetch", fetch);

    await expect(streamUploadOrProcessDocument([new File(["x"], "a.pdf")], "process", {}, discovered)).rejects.toThrow(
      "Stream interrupted",
    );

    expect(discovered).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(KeyCloakService.ensureFreshToken).toHaveBeenCalledExactlyOnceWith(30);
  });

  it("does not replay an accepted stream reporting a per-file 401 processing error", async () => {
    stubFetch([JSON.stringify({ filename: "a.pdf", status: "failed", error: "Processor received HTTP 401" })]);

    await expect(streamUploadOrProcessDocument([new File(["x"], "a.pdf")], "process")).rejects.toThrow(
      "Processor received HTTP 401",
    );

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(KeyCloakService.ensureFreshToken).toHaveBeenCalledExactlyOnceWith(30);
  });

  it.each(["upload", "process"] as const)(
    "keeps a %s batch cancellable while its token is being renewed",
    async (mode) => {
      const store = configureStore({ reducer: { tasks: taskSlice.reducer } });
      const onError = vi.fn();
      const fetch = vi
        .fn()
        .mockResolvedValue(
          ndjsonResponse([JSON.stringify({ filename: "b.pdf", step: "finished", status: "finished" })]),
        );
      vi.stubGlobal("fetch", fetch);
      let finishRefresh!: (fresh: boolean) => void;
      vi.mocked(KeyCloakService.ensureFreshToken).mockReturnValueOnce(
        new Promise<boolean>((resolve) => {
          finishRefresh = resolve;
        }),
      );

      const running = runImport(
        [
          {
            requestMetadata: { tags: ["folder"] },
            files: [new File(["a"], "a.pdf"), new File(["b"], "b.pdf")],
          },
        ],
        { dispatch: store.dispatch, uploadMode: mode, teamId: "team", onError },
      );
      const entries = Object.values(store.getState().tasks.byId);
      const cancelledId = entries.find((entry) => entry.target?.label === "a.pdf")!.taskId;
      const remainingId = entries.find((entry) => entry.target?.label === "b.pdf")!.taskId;

      expect(fetch).not.toHaveBeenCalled();
      expect(canCancelImport(cancelledId)).toBe(true);
      expect(cancelImport(cancelledId, store.dispatch)).toBe(true);
      expect(canCancelImport(remainingId)).toBe(true);
      fetch.mockImplementationOnce(async () => {
        expect(canCancelImport(remainingId)).toBe(false);
        return ndjsonResponse([JSON.stringify({ filename: "b.pdf", step: "finished", status: "finished" })]);
      });
      finishRefresh(true);
      await running;

      expect(fetch).toHaveBeenCalledTimes(1);
      const body = fetch.mock.calls[0][1].body as FormData;
      expect((body.getAll("files") as File[]).map((file) => file.name)).toEqual(["b.pdf"]);
      expect(store.getState().tasks.byId[cancelledId]).toBeUndefined();
      expect(store.getState().tasks.byId[remainingId].state).toBe("succeeded");
      expect(onError).not.toHaveBeenCalled();
    },
  );

  it("sends nothing when every file is cancelled during token renewal", async () => {
    const store = configureStore({ reducer: { tasks: taskSlice.reducer } });
    const onError = vi.fn();
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    let finishRefresh!: (fresh: boolean) => void;
    vi.mocked(KeyCloakService.ensureFreshToken).mockReturnValueOnce(
      new Promise<boolean>((resolve) => {
        finishRefresh = resolve;
      }),
    );

    const running = runImport(
      [
        {
          requestMetadata: {},
          files: [new File(["a"], "a.pdf")],
        },
      ],
      { dispatch: store.dispatch, uploadMode: "process", teamId: "team", onError },
    );
    const entryId = Object.values(store.getState().tasks.byId)[0].taskId;
    expect(cancelImport(entryId, store.dispatch)).toBe(true);
    finishRefresh(true);
    await running;

    expect(fetch).not.toHaveBeenCalled();
    expect(store.getState().tasks.byId).toEqual({});
    expect(onError).not.toHaveBeenCalled();
  });
});
